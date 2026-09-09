"""
Componentes de cartões métricos (Metric Cards) estilizados em HTML/CSS para o Streamlit.
"""

import streamlit as st


def render_metric_css():
    """Injeta estilos CSS personalizados para os cartões métricos."""
    st.markdown("""
    <style>
    .metric-card-container {
        display: flex;
        align-items: center;
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 18px 22px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03), 0 1px 3px rgba(0, 0, 0, 0.05);
        margin-bottom: 15px;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card-container:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06), 0 2px 6px rgba(0, 0, 0, 0.06);
    }
    .metric-icon-box {
        width: 50px;
        height: 50px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        margin-right: 18px;
        flex-shrink: 0;
    }
    .metric-info {
        display: flex;
        flex-direction: column;
    }
    .metric-label {
        font-size: 13px;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 800;
        color: #1e293b;
        line-height: 1.1;
    }
    .metric-delta {
        font-size: 12px;
        font-weight: 600;
        margin-top: 4px;
        display: inline-flex;
        align-items: center;
    }
    .delta-positive { color: #10b981; }
    .delta-neutral { color: #64748b; }
    .delta-alert { color: #f59e0b; }
    </style>
    """, unsafe_allow_html=True)


def metric_card(title: str, value: str, delta: str = "", icon: str = "📊", bg_color: str = "#e0f2fe", text_color: str = "#0284c7"):
    """Renderiza um cartão métrico moderno no layout."""
    delta_html = ""
    if delta:
        delta_html = f'<div class="metric-delta delta-positive">{delta}</div>'

    html = f"""
    <div class="metric-card-container">
        <div class="metric-icon-box" style="background-color: {bg_color}; color: {text_color};">
            {icon}
        </div>
        <div class="metric-info">
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
