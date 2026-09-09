"""
Gráficos interativos modernos usando Plotly para visualização de métricas de candidaturas.
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import List, Dict, Any


def plot_daily_applications(daily_data: List[Dict[str, Any]]) -> go.Figure:
    """Gera gráfico de área/linha para o histórico de candidaturas por dia."""
    if not daily_data:
        # Dados padrão vazios para não quebrar a tela
        df = pd.DataFrame({"Data": [pd.Timestamp.today().strftime("%Y-%m-%d")], "Candidaturas": [0]})
    else:
        df = pd.DataFrame(daily_data)

    fig = px.area(
        df,
        x="applied_date" if "applied_date" in df.columns else df.columns[0],
        y="count" if "count" in df.columns else df.columns[1],
        title="📈 Histórico Diário de Candidaturas",
        markers=True,
        color_discrete_sequence=["#0A66C2"]
    )

    fig.update_layout(
        xaxis_title="Data",
        yaxis_title="Vagas Processadas",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=12, color="#475569"),
        margin=dict(l=20, r=20, t=50, b=20),
        hovermode="x unified"
    )
    fig.update_traces(
        line=dict(width=3, color="#0A66C2"),
        fillcolor="rgba(10, 102, 194, 0.15)"
    )
    return fig


def plot_status_distribution(stats: Dict[str, Any]) -> go.Figure:
    """Gera gráfico de donut com a distribuição dos status."""
    labels = ["Aplicadas (Real)", "Simulação (Dry-Run)", "Puladas", "Falhas"]
    values = [
        stats.get("applied", 0),
        stats.get("dry_run", 0),
        stats.get("skipped", 0),
        stats.get("failed", 0),
    ]

    colors = ["#10b981", "#f59e0b", "#94a3b8", "#ef4444"]

    # Se não houver dados, mostra 1 placeholder
    if sum(values) == 0:
        labels = ["Sem dados"]
        values = [1]
        colors = ["#cbd5e1"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="percent+label",
        hoverinfo="label+value+percent"
    )])

    fig.update_layout(
        title="📊 Distribuição por Status",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=12, color="#475569"),
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False
    )
    return fig


def plot_top_companies(companies_data: List[Dict[str, Any]]) -> go.Figure:
    """Gera gráfico horizontal de barras com as empresas mais frequentes."""
    if not companies_data:
        df = pd.DataFrame({"Empresa": ["Nenhuma"], "Vagas": [0]})
    else:
        df = pd.DataFrame(companies_data).head(8)

    fig = px.bar(
        df,
        x="count" if "count" in df.columns else df.columns[1],
        y="company" if "company" in df.columns else df.columns[0],
        orientation="h",
        title="🏢 Top Empresas Processadas",
        color_discrete_sequence=["#38bdf8"]
    )

    fig.update_layout(
        xaxis_title="Total",
        yaxis_title="",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=12, color="#475569"),
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(autorange="reversed")
    )
    return fig
