"""
test_telegram.py — Script per testare l'invio di un alert fake su Telegram.
Esegui dalla cartella data_park: python poller/test_telegram.py
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Carica .env dalla root del progetto
load_dotenv(Path(__file__).parent.parent / ".env")

from alerts import send_telegram_message

# Messaggio di test che simula un alert reale
message = (
    "🎢 <b>CODA BASSA!</b> (TEST)\n\n"
    "<b>Crush's Coaster</b>\n"
    "⏱ Attesa attuale: <b>15 min</b>\n"
    "📊 Media storica (10:00): 65 min\n"
    "💰 Risparmio: ~50 min\n"
    "📍 Disney Adventure World\n\n"
    "🕐 10:30 — QUESTO È UN TEST"
)

result = send_telegram_message(message)

if result:
    print("✅ Messaggio inviato con successo! Controlla Telegram.")
else:
    print("❌ Invio fallito. Controlla TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nel .env")
