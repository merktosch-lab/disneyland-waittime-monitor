# 🏰 Disneyland Paris — Wait Time Monitor

Sistema di monitoraggio dei tempi di attesa delle attrazioni di Disneyland Paris.  
Raccoglie dati ogni 30 minuti e fornisce una dashboard per analisi statistiche.

## Architettura

```
┌────────────────────────────────────────────────────┐
│  Railway (Cloud)                                    │
│                                                     │
│  Poller ──────────▶ PostgreSQL                      │
│  (ogni 30 min)       (wait_times)                   │
│       │                    │                        │
│       ▼                    │                        │
│  themeparks.wiki API       │                        │
└────────────────────────────┼────────────────────────┘
                             │ SELECT (read-only)
                             ▼
                   Dashboard (Locale)
                   Streamlit + Plotly
```

## Struttura progetto

```
data_park/
├── poller/
│   ├── poller.py           # Loop principale
│   ├── fetcher.py          # Client API themeparks.wiki
│   ├── db.py               # Connessione e query PostgreSQL
│   └── attractions.json    # Attrazioni monitorate (configurabile)
├── dashboard/
│   ├── app.py              # Entry point Streamlit
│   ├── charts.py           # Grafici Plotly
│   └── queries.py          # Query SQL per aggregazioni
├── .env.example            # Template variabili d'ambiente
├── requirements.txt        # Dipendenze Python
├── Procfile                # Per deploy su Railway
└── README.md
```

## Setup

### 1. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 2. Configura il database

Crea un file `.env` nella root del progetto:

```
DATABASE_URL=postgresql://user:password@host:port/dbname
```

### 3. Deploy del Poller su Railway

1. Push del progetto su GitHub
2. Crea un nuovo progetto su Railway → connetti il repository
3. Aggiungi il plugin PostgreSQL → Railway imposta `DATABASE_URL` automaticamente
4. Aggiungi variabile d'ambiente: `TZ=Europe/Paris`
5. Railway avvierà il worker dal Procfile

### 4. Avvia la Dashboard in locale

```bash
streamlit run dashboard/app.py
```

## Attrazioni monitorate

Puoi modificare `poller/attractions.json` per aggiungere o rimuovere attrazioni.  
Il file è strutturato per parco (Disneyland Park e Disney Adventure World).  
Le 15 attrazioni di default includono le principali di entrambi i parchi.

## Note

- Il poller gira H24 e non ha interfaccia visiva
- La dashboard è solo in lettura — non modifica mai il database
- I tempi sono sempre calcolati nel timezone Europe/Paris
- In caso di errori API o DB, il poller logga e continua senza crashare
