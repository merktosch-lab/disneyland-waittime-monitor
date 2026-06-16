"""
charts.py — Funzioni per la creazione dei grafici Plotly della dashboard.
Ogni funzione riceve un DataFrame e restituisce un oggetto Figure di Plotly.
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Nomi dei giorni della settimana in italiano
GIORNI_SETTIMANA = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì",
    "Venerdì", "Sabato", "Domenica"
]


def bar_chart_by_hour(df: pd.DataFrame, title: str) -> go.Figure:
    """
    Grafico a barre: media tempi di attesa per ora del giorno.
    
    Args:
        df: DataFrame con colonne 'hour_of_day' e 'avg_wait'
        title: Titolo del grafico
    
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _empty_figure("Nessun dato disponibile")
    
    fig = px.bar(
        df,
        x="hour_of_day",
        y="avg_wait",
        title=title,
        labels={
            "hour_of_day": "Ora del giorno",
            "avg_wait": "Attesa media (minuti)"
        },
        color="avg_wait",
        color_continuous_scale="RdYlGn_r"  # Rosso=alta coda, Verde=bassa coda
    )
    
    fig.update_layout(
        xaxis=dict(dtick=1, range=[-0.5, 23.5]),
        showlegend=False
    )
    
    return fig


def bar_chart_by_day(df: pd.DataFrame, title: str) -> go.Figure:
    """
    Grafico a barre: media tempi di attesa per giorno della settimana.
    
    Args:
        df: DataFrame con colonne 'day_of_week' e 'avg_wait'
        title: Titolo del grafico
    
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _empty_figure("Nessun dato disponibile")
    
    # Mappiamo i numeri ai nomi dei giorni
    df = df.copy()
    df["giorno"] = df["day_of_week"].map(lambda x: GIORNI_SETTIMANA[int(x)] if pd.notna(x) else "")
    
    fig = px.bar(
        df,
        x="giorno",
        y="avg_wait",
        title=title,
        labels={
            "giorno": "Giorno della settimana",
            "avg_wait": "Attesa media (minuti)"
        },
        color="avg_wait",
        color_continuous_scale="RdYlGn_r"
    )
    
    fig.update_layout(showlegend=False)
    
    return fig


def heatmap_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """
    Heatmap: giorno della settimana × ora del giorno.
    Colore dal verde (bassa coda) al rosso (alta coda).
    
    Args:
        df: DataFrame con colonne 'day_of_week', 'hour_of_day', 'avg_wait'
        title: Titolo del grafico
    
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _empty_figure("Nessun dato disponibile per la heatmap")
    
    # Creiamo una matrice pivot: righe=giorni, colonne=ore
    pivot = df.pivot_table(
        index="day_of_week",
        columns="hour_of_day",
        values="avg_wait",
        fill_value=0
    )
    
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[f"{h}:00" for h in pivot.columns],
        y=[GIORNI_SETTIMANA[int(i)] for i in pivot.index],
        colorscale="RdYlGn_r",
        colorbar=dict(title="Minuti"),
        hoverongaps=False,
        hovertemplate="Giorno: %{y}<br>Ora: %{x}<br>Attesa: %{z} min<extra></extra>"
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Ora del giorno",
        yaxis_title="Giorno della settimana"
    )
    
    return fig


def trend_line_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """
    Line chart: andamento medio giornaliero nel tempo.
    
    Args:
        df: DataFrame con colonne 'day' e 'avg_wait'
        title: Titolo del grafico
    
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _empty_figure("Nessun dato disponibile per il trend")
    
    fig = px.line(
        df,
        x="day",
        y="avg_wait",
        title=title,
        labels={
            "day": "Data",
            "avg_wait": "Attesa media (minuti)"
        },
        markers=True
    )
    
    fig.update_layout(
        xaxis=dict(tickformat="%d/%m/%Y")
    )
    
    return fig


def comparison_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """
    Line chart sovrapposto: confronto di più attrazioni per ora del giorno.
    
    Args:
        df: DataFrame con colonne 'attraction_name', 'hour_of_day', 'avg_wait'
        title: Titolo del grafico
    
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _empty_figure("Nessun dato disponibile per il confronto")
    
    fig = px.line(
        df,
        x="hour_of_day",
        y="avg_wait",
        color="attraction_name",
        title=title,
        labels={
            "hour_of_day": "Ora del giorno",
            "avg_wait": "Attesa media (minuti)",
            "attraction_name": "Attrazione"
        },
        markers=True
    )
    
    fig.update_layout(
        xaxis=dict(dtick=1),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.3,
            xanchor="center",
            x=0.5
        )
    )
    
    return fig


def _empty_figure(message: str) -> go.Figure:
    """
    Crea una figura vuota con un messaggio informativo.
    Usata quando non ci sono dati sufficienti.
    """
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="gray")
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False)
    )
    return fig
