"""
planner.py — Generatore del piano giornaliero ottimale.
Calcola l'ordine migliore per visitare le attrazioni selezionate,
assegnando ogni attrazione alla fascia oraria con la coda media più bassa.

Algoritmo:
1. Per ogni attrazione, recupera la media wait per ogni ora
2. Usa un approccio greedy: assegna ogni slot orario all'attrazione
   che ha il maggior beneficio (differenza tra media generale e media in quello slot)
3. Evita conflitti: ogni attrazione viene assegnata a un solo slot
"""

import pandas as pd


def generate_daily_plan(conn, attraction_ids: list, park_hours: tuple = (9, 22),
                        day_filter=None, date_range=None) -> pd.DataFrame:
    """
    Genera il piano giornaliero ottimale per le attrazioni selezionate.
    
    Args:
        conn: Connessione psycopg2
        attraction_ids: Lista di attraction_id da pianificare
        park_hours: Tupla (ora_apertura, ora_chiusura)
        day_filter: (opzionale) giorno della settimana 0-6
        date_range: (opzionale) tupla (data_inizio, data_fine)
    
    Returns:
        DataFrame con colonne: hour, attraction_name, avg_wait, saving
        ordinato per ora. 'saving' è quanti minuti risparmi rispetto alla media generale.
    """
    if not attraction_ids:
        return pd.DataFrame()
    
    start_hour, end_hour = park_hours
    available_hours = list(range(start_hour, end_hour + 1))
    
    # Recupera i dati medi per ora per ogni attrazione
    placeholders = ",".join(["%s"] * len(attraction_ids))
    query = f"""
        SELECT attraction_id, attraction_name, hour_of_day, 
               ROUND(AVG(wait_minutes)) as avg_wait
        FROM wait_times
        WHERE attraction_id IN ({placeholders})
          AND status = 'OPERATING'
          AND wait_minutes IS NOT NULL
    """
    params = list(attraction_ids)
    
    if day_filter is not None:
        query += " AND day_of_week = %s"
        params.append(day_filter)
    
    if date_range is not None:
        query += " AND sampled_at >= %s AND sampled_at <= %s"
        params.extend(date_range)
    
    query += " GROUP BY attraction_id, attraction_name, hour_of_day;"
    
    df = pd.read_sql(query, conn, params=params)
    
    if df.empty:
        return pd.DataFrame()
    
    # Calcola la media generale per ogni attrazione (per calcolare il risparmio)
    avg_general = df.groupby(["attraction_id", "attraction_name"])["avg_wait"].mean().reset_index()
    avg_general.columns = ["attraction_id", "attraction_name", "avg_general"]
    
    # Crea una matrice: righe=attrazioni, colonne=ore, valori=avg_wait
    pivot = df.pivot_table(
        index=["attraction_id", "attraction_name"],
        columns="hour_of_day",
        values="avg_wait"
    ).reset_index()
    
    # Algoritmo greedy: assegna ogni attrazione all'ora migliore senza conflitti
    assigned = {}  # hour → (attraction_id, attraction_name, avg_wait)
    used_attractions = set()
    
    # Per ogni attrazione, calcola lo "score" per ogni ora
    # Score = quanto è basso il wait time rispetto alla media di quell'attrazione
    scores = []
    for _, row in pivot.iterrows():
        attr_id = row["attraction_id"]
        attr_name = row["attraction_name"]
        general_avg = avg_general[avg_general["attraction_id"] == attr_id]["avg_general"].values[0]
        
        for hour in available_hours:
            if hour in pivot.columns:
                wait = row.get(hour)
                if pd.notna(wait):
                    saving = general_avg - wait
                    scores.append({
                        "attraction_id": attr_id,
                        "attraction_name": attr_name,
                        "hour": int(hour),
                        "avg_wait": int(wait),
                        "saving": round(saving, 1),
                        "avg_general": round(general_avg, 1)
                    })
    
    if not scores:
        return pd.DataFrame()
    
    scores_df = pd.DataFrame(scores)
    # Ordina per saving decrescente (maggior risparmio prima)
    scores_df = scores_df.sort_values("saving", ascending=False)
    
    # Assegnazione greedy: ogni attrazione al suo miglior slot disponibile
    plan = []
    used_hours = set()
    used_attractions = set()
    
    for _, row in scores_df.iterrows():
        attr_id = row["attraction_id"]
        hour = row["hour"]
        
        if attr_id in used_attractions or hour in used_hours:
            continue
        
        plan.append({
            "hour": hour,
            "attraction_name": row["attraction_name"],
            "avg_wait": row["avg_wait"],
            "avg_general": row["avg_general"],
            "saving": row["saving"]
        })
        
        used_hours.add(hour)
        used_attractions.add(attr_id)
    
    if not plan:
        return pd.DataFrame()
    
    plan_df = pd.DataFrame(plan).sort_values("hour").reset_index(drop=True)
    return plan_df


def get_plan_summary(plan_df: pd.DataFrame) -> dict:
    """
    Calcola il riepilogo del piano: tempo totale stimato in coda,
    tempo risparmiato rispetto a un ordine casuale.
    """
    if plan_df.empty:
        return {"total_wait": 0, "total_saving": 0, "num_attractions": 0}
    
    return {
        "total_wait": int(plan_df["avg_wait"].sum()),
        "total_saving": int(plan_df["saving"].sum()),
        "num_attractions": len(plan_df)
    }
