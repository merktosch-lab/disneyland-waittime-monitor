"""
telegram_bot.py — Bot Telegram integrato nel poller.
Gira in un thread separato, risponde ai comandi:
- /now → code attuali di tutte le attrazioni (ultimo campionamento)
- /best → scegli un'attrazione e ricevi i top 5 orari migliori

Usa python-telegram-bot v20+ (async).
Gira in un thread separato per non bloccare il poller.
"""

import os
import logging
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from db import get_connection

logger = logging.getLogger("telegram_bot")

# Nomi giorni in italiano
GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]

# Set globale degli ID disabilitati (caricato all'avvio)
_disabled_ids = set()


def load_disabled_ids():
    """Carica gli ID con enabled=false dal file disabled.json."""
    global _disabled_ids
    import json
    from pathlib import Path
    
    disabled_file = Path(__file__).parent / "parks" / "disabled.json"
    if disabled_file.exists():
        try:
            with open(disabled_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            _disabled_ids = {
                e["id"] for e in data.get("entities", []) 
                if not e.get("enabled", True)
            }
        except Exception:
            pass


async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /now — Mostra le code attuali (ultimo campionamento per ogni attrazione).
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (attraction_name)
                    attraction_id, attraction_name, wait_minutes, single_rider_minutes, 
                    status, park, sampled_at
                FROM wait_times
                WHERE entity_type = 'ATTRACTION'
                ORDER BY attraction_name, sampled_at DESC;
            """)
            rows = cur.fetchall()
        
        if not rows:
            await update.message.reply_text("📭 Nessun dato disponibile ancora.")
            return
        
        # Raggruppa per parco, escludi disabilitati
        parks = {}
        for attr_id, name, wait, sr, status, park, sampled in rows:
            if attr_id in _disabled_ids:
                continue
            if park not in parks:
                parks[park] = []
            parks[park].append((name, wait, sr, status))
        
        lines = ["🎢 <b>Code attuali</b>\n"]
        for park_name, attractions in sorted(parks.items()):
            lines.append(f"\n<b>📍 {park_name}</b>")
            for name, wait, sr, status in sorted(attractions, key=lambda x: x[1] or 999):
                if status != "OPERATING":
                    lines.append(f"  🔴 {name} — {status}")
                elif wait is not None:
                    sr_text = f" (SR: {sr}′)" if sr else ""
                    lines.append(f"  {'🟢' if wait <= 20 else '🟡' if wait <= 45 else '🔴'} {name} — <b>{wait}′</b>{sr_text}")
                else:
                    lines.append(f"  ⚪ {name} — N/D")
        
        # Timestamp ultimo dato
        latest = max(r[6] for r in rows if r[0] not in _disabled_ids)
        lines.append(f"\n🕐 Ultimo aggiornamento: {latest.strftime('%H:%M')}")
        
        message = "\n".join(lines)
        # Telegram ha limite 4096 caratteri
        if len(message) > 4000:
            message = message[:4000] + "\n..."
        
        await update.message.reply_text(message, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Errore in /now: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def cmd_best(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /best — Mostra prima la scelta del parco, poi le attrazioni di quel parco.
    Esclude le entity disabilitate.
    """
    keyboard = [
        [InlineKeyboardButton("🏰 Disneyland Park", callback_data="park:Disneyland Park")],
        [InlineKeyboardButton("🌍 Disney Adventure World", callback_data="park:Disney Adventure World")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎢 Scegli un parco:",
        reply_markup=reply_markup
    )


async def callback_park(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback quando l'utente sceglie un parco.
    Mostra le attrazioni di quel parco (solo enabled, solo ATTRACTION).
    """
    query = update.callback_query
    await query.answer()
    
    park_name = query.data.replace("park:", "")
    
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT attraction_id, attraction_name
                FROM wait_times
                WHERE entity_type = 'ATTRACTION' 
                  AND park = %s
                  AND status = 'OPERATING'
                ORDER BY attraction_name;
            """, (park_name,))
            rows = cur.fetchall()
        
        if not rows:
            await query.edit_message_text(f"📭 Nessun dato per {park_name}.")
            return
        
        # Filtra le entity disabilitate
        enabled_rows = [(aid, aname) for aid, aname in rows if aid not in _disabled_ids]
        
        if not enabled_rows:
            await query.edit_message_text(f"📭 Nessuna attrazione abilitata per {park_name}.")
            return
        
        # Bottoni attrazioni (1 per riga, nome completo)
        keyboard = []
        for attr_id, attr_name in enabled_rows:
            short_name = attr_name[:35] if len(attr_name) > 35 else attr_name
            keyboard.append([InlineKeyboardButton(short_name, callback_data=f"best:{attr_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🎢 <b>{park_name}</b> — Scegli un'attrazione:",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    
    except Exception as e:
        logger.error(f"Errore in callback_park: {e}")
        await query.edit_message_text(f"❌ Errore: {e}")


async def callback_best(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback quando l'utente preme un bottone dopo /best.
    Mostra i top 5 orari con coda più bassa per quell'attrazione.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("best:"):
        return
    
    attraction_id = data.replace("best:", "")
    
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Nome attrazione
            cur.execute("""
                SELECT DISTINCT attraction_name 
                FROM wait_times WHERE attraction_id = %s LIMIT 1;
            """, (attraction_id,))
            name_row = cur.fetchone()
            attr_name = name_row[0] if name_row else "Sconosciuto"
            
            # Top 5 orari con coda più bassa
            cur.execute("""
                SELECT hour_of_day, ROUND(AVG(wait_minutes)) as avg_wait,
                       COUNT(*) as samples
                FROM wait_times
                WHERE attraction_id = %s 
                  AND status = 'OPERATING'
                  AND wait_minutes IS NOT NULL
                GROUP BY hour_of_day
                HAVING COUNT(*) >= 3
                ORDER BY avg_wait ASC
                LIMIT 5;
            """, (attraction_id,))
            rows = cur.fetchall()
            
            # Media generale
            cur.execute("""
                SELECT ROUND(AVG(wait_minutes)) 
                FROM wait_times
                WHERE attraction_id = %s 
                  AND status = 'OPERATING'
                  AND wait_minutes IS NOT NULL;
            """, (attraction_id,))
            avg_row = cur.fetchone()
            avg_general = int(avg_row[0]) if avg_row and avg_row[0] else 0
        
        if not rows:
            await query.edit_message_text(
                f"⚠️ Dati insufficienti per <b>{attr_name}</b>. Attendi più campionamenti.",
                parse_mode="HTML"
            )
            return
        
        lines = [f"🌟 <b>Migliori orari — {attr_name}</b>"]
        lines.append(f"📊 Media generale: {avg_general} min\n")
        
        for i, (hour, avg_wait, samples) in enumerate(rows, 1):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
            saving = avg_general - int(avg_wait)
            lines.append(
                f"{medal} <b>{int(hour)}:00</b> — {int(avg_wait)} min "
                f"(risparmi {saving} min, {samples} camp.)"
            )
        
        lines.append(f"\n💡 Vai in queste fasce per la coda più breve!")
        
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Errore in callback_best: {e}")
        await query.edit_message_text(f"❌ Errore: {e}")


def start_bot():
    """
    Avvia il bot Telegram in un thread separato.
    Se TELEGRAM_BOT_TOKEN non è configurato, non fa nulla.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN non configurato — bot Telegram disattivato")
        return
    
    # Carica la lista entity disabilitate
    load_disabled_ids()
    
    def run_bot():
        """Funzione che gira nel thread del bot."""
        try:
            app = Application.builder().token(token).build()
            
            # Registra i comandi
            app.add_handler(CommandHandler("now", cmd_now))
            app.add_handler(CommandHandler("best", cmd_best))
            app.add_handler(CallbackQueryHandler(callback_park, pattern="^park:"))
            app.add_handler(CallbackQueryHandler(callback_best, pattern="^best:"))
            
            logger.info("Bot Telegram avviato — comandi: /now, /best")
            app.run_polling(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"Errore nel bot Telegram: {e}", exc_info=True)
    
    # Avvia in un thread daemon (si ferma quando il processo principale muore)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
