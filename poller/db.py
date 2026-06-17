"""
db.py — Layer di accesso al database PostgreSQL
Gestisce connessione, creazione schema e inserimento dati.
Ottimizzato: usa una singola connessione per ciclo invece di una per insert.
"""

import os
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2 import OperationalError

# Configurazione logger
logger = logging.getLogger(__name__)

# Timezone di riferimento per il calcolo di giorno/ora
PARIS_TZ = ZoneInfo("Europe/Paris")

# Parametri retry connessione
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # secondi

# Connessione globale riutilizzabile
_connection = None


def get_connection():
    """
    Ottiene una connessione al database PostgreSQL.
    Riutilizza la connessione esistente se ancora attiva.
    
    Returns:
        Connessione psycopg2 attiva.
    """
    global _connection
    
    # Se abbiamo già una connessione attiva, riutilizziamola
    if _connection is not None:
        try:
            # Test rapido: la connessione è ancora viva?
            _connection.cursor().execute("SELECT 1")
            return _connection
        except Exception:
            # Connessione morta, la ricreiamo
            _connection = None
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("Variabile d'ambiente DATABASE_URL non impostata")
    
    # Railway potrebbe fornire URL con prefisso 'postgres://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    backoff = INITIAL_BACKOFF
    last_error = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _connection = psycopg2.connect(database_url)
            _connection.autocommit = True
            # Imposta timezone sessione a Europe/Paris per vedere orari locali
            with _connection.cursor() as cur:
                cur.execute("SET timezone = 'Europe/Paris';")
            logger.info(f"Connessione al database stabilita (tentativo {attempt})")
            return _connection
        except OperationalError as e:
            last_error = e
            logger.warning(
                f"Tentativo {attempt}/{MAX_RETRIES} fallito: {e}. "
                f"Retry fra {backoff}s..."
            )
            time.sleep(backoff)
            backoff *= 2
    
    logger.error(f"Impossibile connettersi al database dopo {MAX_RETRIES} tentativi")
    raise last_error


def close_connection():
    """Chiude la connessione globale (da chiamare a fine ciclo se necessario)."""
    global _connection
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None


def ensure_schema():
    """
    Crea le tabelle e gli indici se non esistono già.
    - wait_times: tempi di attesa delle ATTRACTION
    - show_schedules: orari degli SHOW
    - show_changes: cambiamenti rilevati negli orari
    Operazione idempotente.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        # Imposta timezone della sessione a Europe/Paris
        cur.execute("SET timezone = 'Europe/Paris';")
        
        # Tabella principale per le ATTRACTION
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wait_times (
                id              SERIAL PRIMARY KEY,
                attraction_id   VARCHAR(100) NOT NULL,
                attraction_name VARCHAR(200) NOT NULL,
                entity_type     VARCHAR(50),
                park            VARCHAR(100) NOT NULL,
                external_id     VARCHAR(50),
                wait_minutes    INTEGER,
                single_rider_minutes INTEGER,
                premier_access_price INTEGER,
                premier_access_currency VARCHAR(10),
                premier_access_state VARCHAR(50),
                premier_access_return_start TIMESTAMPTZ,
                premier_access_return_end TIMESTAMPTZ,
                status          VARCHAR(50),
                sampled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                day_of_week     SMALLINT,
                hour_of_day     SMALLINT
            );
        """)
        
        # Tabella per gli SHOW
        cur.execute("""
            CREATE TABLE IF NOT EXISTS show_schedules (
                id              SERIAL PRIMARY KEY,
                show_id         VARCHAR(100) NOT NULL,
                show_name       VARCHAR(200) NOT NULL,
                park            VARCHAR(100) NOT NULL,
                external_id     VARCHAR(50),
                status          VARCHAR(50),
                performance_date DATE NOT NULL,
                performance_time TIME NOT NULL,
                sampled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        
        # Tabella per i CAMBIAMENTI orari show
        cur.execute("""
            CREATE TABLE IF NOT EXISTS show_changes (
                id              SERIAL PRIMARY KEY,
                show_id         VARCHAR(100) NOT NULL,
                show_name       VARCHAR(200) NOT NULL,
                park            VARCHAR(100) NOT NULL,
                change_type     VARCHAR(50) NOT NULL,
                old_times       TEXT,
                new_times       TEXT,
                detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        
        # Indici wait_times
        cur.execute("CREATE INDEX IF NOT EXISTS idx_attraction_id ON wait_times(attraction_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sampled_at ON wait_times(sampled_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_day_hour ON wait_times(day_of_week, hour_of_day);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entity_type ON wait_times(entity_type);")
        
        # Indici show_schedules
        cur.execute("CREATE INDEX IF NOT EXISTS idx_show_id ON show_schedules(show_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_show_date ON show_schedules(performance_date);")
        
        # Indice show_changes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_show_changes_detected ON show_changes(detected_at);")
    
    logger.info("Schema database verificato/creato con successo")
    
    # Migration: aggiunge colonne mancanti (per DB già esistenti)
    with conn.cursor() as cur:
        migrations = [
            "ALTER TABLE wait_times ADD COLUMN IF NOT EXISTS premier_access_state VARCHAR(50);",
            "ALTER TABLE wait_times ADD COLUMN IF NOT EXISTS premier_access_return_start TIMESTAMPTZ;",
            "ALTER TABLE wait_times ADD COLUMN IF NOT EXISTS premier_access_return_end TIMESTAMPTZ;",
        ]
        for sql in migrations:
            try:
                cur.execute(sql)
            except Exception:
                pass  # Colonna già esiste o DB non supporta IF NOT EXISTS


def insert_wait_time(record: dict):
    """
    Inserisce un singolo record di tempo di attesa nel database.
    Calcola day_of_week e hour_of_day usando il timezone Europe/Paris.
    """
    conn = get_connection()
    now_paris = datetime.now(PARIS_TZ)
    day_of_week = now_paris.weekday()
    hour_of_day = now_paris.hour
    
    # Parsing degli orari return Premier Access (ISO → datetime)
    pa_return_start = None
    pa_return_end = None
    if record.get("premier_access_return_start"):
        try:
            pa_return_start = datetime.fromisoformat(record["premier_access_return_start"])
        except (ValueError, TypeError):
            pass
    if record.get("premier_access_return_end"):
        try:
            pa_return_end = datetime.fromisoformat(record["premier_access_return_end"])
        except (ValueError, TypeError):
            pass
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO wait_times 
                (attraction_id, attraction_name, entity_type, park, external_id,
                 wait_minutes, single_rider_minutes, premier_access_price, 
                 premier_access_currency, premier_access_state,
                 premier_access_return_start, premier_access_return_end,
                 status, sampled_at, day_of_week, hour_of_day)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            record["attraction_id"],
            record["attraction_name"],
            record.get("entity_type"),
            record["park"],
            record.get("external_id"),
            record.get("wait_minutes"),
            record.get("single_rider_minutes"),
            record.get("premier_access_price"),
            record.get("premier_access_currency"),
            record.get("premier_access_state"),
            pa_return_start,
            pa_return_end,
            record.get("status"),
            now_paris,
            day_of_week,
            hour_of_day
        ))
    
    logger.debug(
        f"Inserito: {record['attraction_name']} — "
        f"{record.get('wait_minutes', 'N/A')} min ({record.get('status')})"
    )


def insert_show_schedule(record: dict):
    """
    Inserisce gli orari di uno show nel database.
    Rileva cambiamenti rispetto agli orari precedenti per la stessa data.
    """
    conn = get_connection()
    show_id = record["show_id"]
    show_name = record["show_name"]
    park = record["park"]
    external_id = record.get("external_id")
    status = record.get("status")
    showtimes = record.get("showtimes", [])
    
    if not showtimes:
        return
    
    now_paris = datetime.now(PARIS_TZ)
    
    # Raggruppiamo gli showtimes per data
    schedules_by_date = {}
    for st in showtimes:
        start_str = st.get("startTime")
        if not start_str:
            continue
        try:
            dt = datetime.fromisoformat(start_str)
            perf_date = dt.date()
            perf_time = dt.time()
            
            if perf_date not in schedules_by_date:
                schedules_by_date[perf_date] = []
            schedules_by_date[perf_date].append(perf_time)
        except (ValueError, TypeError):
            continue
    
    with conn.cursor() as cur:
        for perf_date, times in schedules_by_date.items():
            times.sort()
            new_times_str = ",".join(t.strftime("%H:%M") for t in times)
            
            # Controlliamo orari esistenti per questo show+data
            cur.execute("""
                SELECT DISTINCT performance_time 
                FROM show_schedules 
                WHERE show_id = %s AND performance_date = %s
                ORDER BY performance_time;
            """, (show_id, perf_date))
            
            existing_times = [row[0] for row in cur.fetchall()]
            old_times_str = ",".join(t.strftime("%H:%M") for t in existing_times)
            
            # Se cambiati, registra il cambiamento
            if existing_times and old_times_str != new_times_str:
                cur.execute("""
                    INSERT INTO show_changes 
                        (show_id, show_name, park, change_type, old_times, new_times, detected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (show_id, show_name, park, "SCHEDULE_CHANGED",
                      old_times_str, new_times_str, now_paris))
                
                logger.info(
                    f"Cambiamento orari: '{show_name}' ({perf_date}): "
                    f"{old_times_str} → {new_times_str}"
                )
                
                # Elimina vecchi orari per questa data
                cur.execute("""
                    DELETE FROM show_schedules 
                    WHERE show_id = %s AND performance_date = %s;
                """, (show_id, perf_date))
            
            # Inserisci nuovi orari (solo se non esistono o sono cambiati)
            if not existing_times or old_times_str != new_times_str:
                for perf_time in times:
                    cur.execute("""
                        INSERT INTO show_schedules 
                            (show_id, show_name, park, external_id, status,
                             performance_date, performance_time, sampled_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (show_id, show_name, park, external_id, status,
                          perf_date, perf_time, now_paris))
    
    logger.debug(f"Show '{show_name}': orari processati")
