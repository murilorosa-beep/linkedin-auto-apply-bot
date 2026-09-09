"""
Componentes de tabelas interativas com badges coloridos e exportação de dados.
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any


def render_applications_table(applications: List[Dict[str, Any]]):
    """Renderiza a tabela de candidaturas com estilização de status e links clicáveis."""
    if not applications:
        st.info("Nenhuma candidatura registrada ainda no banco de dados.")
        return

    df = pd.DataFrame(applications)

    # Renomear colunas para exibição amigável
    col_map = {
        "title": "Cargo",
        "company": "Empresa",
        "location": "Localização",
        "match_score": "Match",
        "status": "Status",
        "applied_at": "Data / Hora",
        "notes": "Observações",
        "url": "Link"
    }

    display_cols = [c for c in ["title", "company", "location", "match_score", "status", "applied_at", "notes", "url"] if c in df.columns]
    df_display = df[display_cols].rename(columns=col_map)

    # Formatar badges de status
    def format_status(val):
        val_upper = str(val).upper()
        if "APPLIED" in val_upper:
            return "🟢 Aplicada"
        elif "DRY_RUN" in val_upper:
            return "🟡 Simulação (Dry-Run)"
        elif "SKIPPED" in val_upper:
            return "⚪ Pulada"
        elif "FAILED" in val_upper:
            return "🔴 Falha"
        return val

    if "Status" in df_display.columns:
        df_display["Status"] = df_display["Status"].apply(format_status)

    if "Match" in df_display.columns:
        df_display["Match"] = df_display["Match"].apply(lambda v: f"{int(v)}%" if pd.notnull(v) and int(v) > 0 else "-")

    if "Cargo" in df_display.columns:
        def format_title_row(idx):
            orig_row = df.iloc[idx]
            t = str(df_display.at[idx, "Cargo"])
            badges = []
            if orig_row.get("has_visa_sponsorship", 0) in (1, True, "1"):
                badges.append("✈️ Visto")
            if orig_row.get("is_latam_friendly", 0) in (1, True, "1"):
                badges.append("🌎 LatAm")
            if badges:
                return f"[{' | '.join(badges)}] {t}"
            return t

        for i in range(len(df_display)):
            df_display.at[i, "Cargo"] = format_title_row(i)

    if "Localização" in df_display.columns:
        def format_location(loc):
            s = str(loc)
            s_low = s.lower()
            if any(h in s_low for h in ["híbrido", "hibrido", "hybrid"]):
                return f"🏢 {s}"
            elif any(r in s_low for r in ["remoto", "remote", "home office"]):
                return f"🏠 {s}"
            elif any(b in s_low for b in ["brazil", "brasil", "são paulo", "sp", "jundiaí", "campinas"]):
                return f"🇧🇷 {s}"
            return s
        df_display["Localização"] = df_display["Localização"].apply(format_location)

    # Exibir com link configurado
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "Link": st.column_config.LinkColumn(
                "Link da Vaga",
                help="Clique para abrir a vaga no LinkedIn",
                validate="^https://.*linkedin\\.com.*",
                max_chars=40
            ) if "Link" in df_display.columns else None
        },
        hide_index=True
    )

    # Botão de exportação
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Exportar Dados para CSV",
        data=csv,
        file_name="candidaturas_linkedin.csv",
        mime="text/csv",
        help="Baixar todo o histórico em arquivo CSV"
    )
