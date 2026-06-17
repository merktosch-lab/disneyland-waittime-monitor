"""
queries.py — Query SQL per le aggregazioni statistiche della dashboard.
Tutte le funzioni restituiscono pandas DataFrame pronti per i grafici.
La dashboard è SOLO in lettura: nessuna operazione di scrittura.

Schema DB aggiornato:
- attraction_id, attraction_name, entity_type, park, external_id
- wait_minutes, single_rider_minutes, premier_access_price, premier_access_currency
- status, sampled_at, day_of_week, hour_of_day
"""

import pandas as pd


def get_overview_stats(conn) -> dict:
    """
    Recupera le statistiche generali di panoramica:
    - Totale campionamenti
    - Data primo e ultimo campionamento
    - Tabella riepilogativa per attrazione
    """
    # Totale campionamenti e date estreme
    query_totals = """
        SELECT 
            COUNT(*) as total_samples,
            MIN(sampled_at) as first_sample,
            MAX(sampled_at) as last_sample
        FROM wait_times;
    """
    df_totals = pd.read_sql(query_totals, conn)
    
    # Tabella riepilogativa per attrazione (solo ATTRACTION, escluse SHOW)
    query_summary = """
        SELECT 
            attraction_name,
            park,
            entity_type,
            COUNT(*) as num_samples,
            ROUND(AVG(wait_minutes)) as avg_wait,
            ROUND(AVG(single_rider_minutes)) as avg_single_rider,
            MAX(sampled_at) as last_sample
        FROM wait_times
        WHERE status = 'OPERATING'
        GROUP BY attraction_name, park, entity_type
        ORDER BY park, attraction_name;
    """
    df_summary = pd.read_sql(query_summary, conn)
    
    return {
        "total_samples": int(df_totals["total_samples"].iloc[0]) if not df_totals.empty else 0,
        "first_sample": df_totals["first_sample"].iloc[0] if not df_totals.empty else None,
        "last_sample": df_totals["last_sample"].iloc[0] if not df_totals.empty else None,
        "summary_df": df_summary
    }


def get_attraction_list(conn) -> pd.DataFrame:
    """
    Recupera la lista di tutte le ATTRACTION monitorate nel database.
    Esclude gli SHOW (gestiti separatamente).
    """
    query = """
        SELECT DISTINCT attraction_id, attraction_name, park, entity_type
        FROM wait_times
        WHERE entity_type = 'ATTRACTION'
        ORDER BY park, attraction_name;
    """
    return pd.read_sql(query, conn)


def get_sample_count(conn, attraction_id: str) -> int:
    """
    Conta i campionamenti per una specifica attrazione.
    Usato per il controllo 'dati insufficienti'.
    """
    query = """
        SELECT COUNT(*) as cnt
        FROM wait_times
        WHERE attraction_id = %s AND status = 'OPERATING';
    """
    df = pd.read_sql(query, conn, params=(attraction_id,))
    return int(df["cnt"].iloc[0]) if not df.empty else 0


def get_avg_by_hour(conn, attraction_id: str, day_filter=None, date_range=None) -> pd.DataFrame:
    """
    Media tempo di attesa per ora del giorno.
    Esclude status REFURBISHMENT e CLOSED.
    """
    query = """
        SELECT hour_of_day, ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = [attraction_id]
    
    if day_filter is not None:
        query += " AND day_of_week = %s"
        params.append(day_filter)
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY hour_of_day ORDER BY hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


def get_avg_by_day(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Media tempo di attesa per giorno della settimana.
    """
    query = """
        SELECT day_of_week, ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY day_of_week ORDER BY day_of_week;"
    
    return pd.read_sql(query, conn, params=params)


def get_heatmap_data(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Dati per la heatmap: giorno della settimana × ora del giorno.
    """
    query = """
        SELECT day_of_week, hour_of_day, ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY day_of_week, hour_of_day ORDER BY day_of_week, hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


def get_daily_trend(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Trend storico: media giornaliera nel tempo.
    """
    query = """
        SELECT DATE(sampled_at) as day, ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY DATE(sampled_at) ORDER BY day;"
    
    return pd.read_sql(query, conn, params=params)


def get_best_moments(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Top 3 fasce orarie con la coda media più bassa.
    """
    query = """
        SELECT hour_of_day, ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY hour_of_day ORDER BY avg_wait ASC LIMIT 3;"
    
    return pd.read_sql(query, conn, params=params)


def get_comparison_data(conn, attraction_ids: list, date_range=None) -> pd.DataFrame:
    """
    Dati per il confronto tra attrazioni: media per ora del giorno.
    """
    if not attraction_ids:
        return pd.DataFrame()
    
    placeholders = ",".join(["%s"] * len(attraction_ids))
    
    query = f"""
        SELECT attraction_name, hour_of_day, ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id IN ({placeholders})
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = list(attraction_ids)
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY attraction_name, hour_of_day ORDER BY attraction_name, hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


# === NUOVE QUERY: Single Rider e Premier Access ===


def get_single_rider_by_hour(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Media tempo Single Rider per ora del giorno.
    Solo per attrazioni che offrono Single Rider.
    """
    query = """
        SELECT hour_of_day, 
               ROUND(AVG(wait_minutes)) as avg_standby,
               ROUND(AVG(single_rider_minutes)) as avg_single_rider
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND single_rider_minutes IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY hour_of_day ORDER BY hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


def get_premier_access_stats(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Statistiche Premier Access: prezzo medio e disponibilità per ora.
    Il prezzo è in centesimi (es. 1300 = 13.00€).
    """
    query = """
        SELECT hour_of_day,
               ROUND(AVG(premier_access_price)) as avg_price,
               COUNT(premier_access_price) as times_available,
               COUNT(*) as total_samples
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY hour_of_day ORDER BY hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


def get_premier_access_availability(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Analisi disponibilità Premier Access nel tempo:
    - A che ora del giorno sono ancora AVAILABLE
    - A che ora diventano FINISHED (esauriti)
    - Fascia oraria media del return time offerto per ogni ora di campionamento
    
    Utile per capire: "se compro il PA alle 9, che fascia oraria mi danno?"
    """
    query = """
        SELECT 
            hour_of_day,
            premier_access_state,
            COUNT(*) as occurrences,
            ROUND(AVG(EXTRACT(HOUR FROM premier_access_return_start))) as avg_return_hour
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND premier_access_state IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY hour_of_day, premier_access_state ORDER BY hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


def get_premier_access_return_slots(conn, attraction_id: str, date_range=None) -> pd.DataFrame:
    """
    Mostra la fascia oraria del return time offerta per ogni ora di acquisto.
    Es: "Se compro alle 9:00, mi danno slot 14:00-15:00"
        "Se compro alle 12:00, mi danno slot 19:00-20:00"
    
    Fondamentale per pianificare quando prenotare.
    """
    query = """
        SELECT 
            hour_of_day as ora_acquisto,
            ROUND(AVG(EXTRACT(HOUR FROM premier_access_return_start))) as return_hour_media,
            MIN(EXTRACT(HOUR FROM premier_access_return_start)) as return_hour_min,
            MAX(EXTRACT(HOUR FROM premier_access_return_start)) as return_hour_max,
            ROUND(AVG(premier_access_price)) as prezzo_medio,
            COUNT(*) as campionamenti
        FROM wait_times
        WHERE attraction_id = %s 
          AND status = 'OPERATING'
          AND premier_access_state = 'AVAILABLE'
          AND premier_access_return_start IS NOT NULL
    """
    params = [attraction_id]
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY hour_of_day ORDER BY hour_of_day;"
    
    return pd.read_sql(query, conn, params=params)


def get_single_rider_comparison(conn, date_range=None) -> pd.DataFrame:
    """
    Confronto risparmio Single Rider vs Standby per tutte le attrazioni
    che offrono Single Rider.
    """
    query = """
        SELECT attraction_name,
               ROUND(AVG(wait_minutes)) as avg_standby,
               ROUND(AVG(single_rider_minutes)) as avg_single_rider,
               ROUND(AVG(wait_minutes) - AVG(single_rider_minutes)) as risparmio_medio
        FROM wait_times
        WHERE status = 'OPERATING'
          AND single_rider_minutes IS NOT NULL
          AND wait_minutes IS NOT NULL
    """
    params = []
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY attraction_name ORDER BY risparmio_medio DESC;"
    
    return pd.read_sql(query, conn, params=params)


def get_shows_schedule(conn) -> pd.DataFrame:
    """
    Recupera tutti gli orari degli show salvati, raggruppati per show e data.
    """
    query = """
        SELECT show_name, park, performance_date, performance_time, status
        FROM show_schedules
        ORDER BY show_name, performance_date, performance_time;
    """
    return pd.read_sql(query, conn)


def get_show_changes(conn, limit: int = 50) -> pd.DataFrame:
    """
    Recupera gli ultimi cambiamenti rilevati negli orari degli show.
    """
    query = """
        SELECT show_name, park, change_type, old_times, new_times, detected_at
        FROM show_changes
        ORDER BY detected_at DESC
        LIMIT %s;
    """
    return pd.read_sql(query, conn, params=(limit,))


def get_shows_list(conn) -> pd.DataFrame:
    """
    Lista di tutti gli show monitorati con l'ultimo stato.
    """
    query = """
        SELECT DISTINCT show_id, show_name, park
        FROM show_schedules
        ORDER BY park, show_name;
    """
    return pd.read_sql(query, conn)


def get_show_times_by_name(conn, show_name: str) -> pd.DataFrame:
    """
    Orari di uno specifico show raggruppati per data.
    """
    query = """
        SELECT performance_date, performance_time, status
        FROM show_schedules
        WHERE show_name = %s
        ORDER BY performance_date DESC, performance_time;
    """
    return pd.read_sql(query, conn, params=(show_name,))
