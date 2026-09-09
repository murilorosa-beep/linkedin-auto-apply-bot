"""
Aplicação Web Moderna em Streamlit para o Robô de Candidaturas Internacionais do LinkedIn.
Permite gerenciar buscas, perfil, configurações, logs ao vivo e relatórios interativos.
"""

import sys
import os
import time
import threading
from pathlib import Path
import pandas as pd
import streamlit as st

# Garantir encoding UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configuração da página do Streamlit
st.set_page_config(
    page_title="LinkedIn Auto-Apply AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

from utils.logger import setup_streamlit_logger, get_recent_logs, clear_logs
from utils.config_manager import load_config, save_config, set_dry_run, set_api_key, apply_preset
from utils.profile_manager import load_profile, save_profile, save_uploaded_resume, has_resume, get_resume_path
from utils.session_manager import is_session_dir_initialized, launch_manual_login_process
from components.metrics import render_metric_css, metric_card
from components.charts import plot_daily_applications, plot_status_distribution, plot_top_companies
from components.tables import render_applications_table
from components.forms import render_search_config_form, render_profile_edit_form
from core.tracker import ApplicationTracker
from core.engine import ApplicationEngine

# Inicializar logger do Streamlit
setup_streamlit_logger()

# Injetar CSS de tema e cartões
render_metric_css()

st.markdown("""
<style>
/* Estilo geral */
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}
/* Estilo para status no sidebar */
.status-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 8px;
}
.status-real { background-color: #fee2e2; color: #dc2626; border: 1px solid #f87171; }
.status-dry { background-color: #fef3c7; color: #d97706; border: 1px solid #fbbf24; }
.status-online { background-color: #dcfce7; color: #15803d; border: 1px solid #86efac; }
.status-offline { background-color: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }

/* Log terminal viewer */
.log-terminal {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: 'Courier New', Courier, monospace;
    font-size: 12px;
    padding: 14px;
    border-radius: 10px;
    height: 380px;
    overflow-y: auto;
    border: 1px solid #334155;
    white-space: pre-wrap;
}
.log-info { color: #38bdf8; }
.log-warning { color: #fbbf24; }
.log-error { color: #f87171; }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# Gerenciamento de Estado da Sessão (Thread de Background do Robô)
# ==============================================================================
if "bot_thread" not in st.session_state:
    st.session_state.bot_thread = None
if "bot_stop_event" not in st.session_state:
    st.session_state.bot_stop_event = None
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False

# Sincronizar status caso a thread termine por conta própria
if st.session_state.bot_thread is not None:
    if not st.session_state.bot_thread.is_alive():
        st.session_state.bot_running = False
        st.session_state.bot_thread = None


def start_bot_background():
    """Inicia o robô em uma thread de segundo plano."""
    if st.session_state.get("bot_running", False):
        return

    st.session_state.bot_stop_event = threading.Event()
    st.session_state.bot_running = True

    def _worker(stop_evt):
        try:
            engine = ApplicationEngine()
            engine.run(stop_event=stop_evt)
        except Exception as e:
            import logging
            logging.getLogger("AutoApplyBot").error(f"Erro na thread do robô: {e}")
        finally:
            st.session_state.bot_running = False

    thread = threading.Thread(target=_worker, args=(st.session_state.bot_stop_event,), daemon=True)
    st.session_state.bot_thread = thread
    thread.start()


def stop_bot_background():
    """Solicita a interrupção suave do robô."""
    if st.session_state.bot_stop_event:
        st.session_state.bot_stop_event.set()
    st.session_state.bot_running = False


# ==============================================================================
# Inicialização do Agendador em Segundo Plano (Smart Scheduler)
# ==============================================================================
from utils.scheduler import SmartScheduler
from utils.telegram_notifier import TelegramNotifier

def _trigger_scheduled_run():
    if not st.session_state.get("bot_running", False):
        start_bot_background()

smart_scheduler = SmartScheduler(run_callback=_trigger_scheduled_run)
_cfg_boot = load_config()
if _cfg_boot.get("scheduler", {}).get("enabled", False) and not smart_scheduler.is_running():
    smart_scheduler.start()
elif not _cfg_boot.get("scheduler", {}).get("enabled", False) and smart_scheduler.is_running():
    smart_scheduler.stop()


# ==============================================================================
# Barra Lateral (Sidebar)
# ==============================================================================
with st.sidebar:
    st.markdown("## ⚡ AutoApply AI")
    st.caption("Candidaturas Internacionais LinkedIn")
    st.markdown("---")

    page = st.radio(
        "Navegação:",
        [
            "📊 Dashboard",
            "🔍 Buscar Vagas",
            "🤝 Recrutadores & Outreach",
            "👤 Perfil do Candidato",
            "⚙️ Configurações",
            "📈 Relatórios & Histórico"
        ],
        index=0
    )

    st.markdown("---")
    st.markdown("### 🚦 Status do Sistema")

    cfg = load_config()
    is_dry = cfg.get("bot", {}).get("dry_run", True)

    if is_dry:
        st.markdown('<span class="status-pill status-dry">MODO SIMULAÇÃO (DRY-RUN)</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-pill status-real">MODO REAL (ENVIANDO)</span>', unsafe_allow_html=True)

    tracker = ApplicationTracker()
    stats = tracker.get_stats()
    max_daily = cfg.get("limits", {}).get("max_applications_per_day", 50)
    today_count = stats.get("today_applied", 0)

    st.caption(f"Candidaturas Hoje: **{today_count} / {max_daily}**")
    st.progress(min(today_count / max_daily, 1.0))

    def _on_sidebar_limit_change():
        new_val = st.session_state.get("sb_limit_slider")
        if new_val is not None:
            c = load_config()
            c["limits"]["max_applications_per_day"] = int(new_val)
            save_config(c)

    st.slider(
        "⚡ Meta Diária (Salva auto):",
        min_value=5,
        max_value=100,
        value=int(max_daily),
        step=5,
        key="sb_limit_slider",
        on_change=_on_sidebar_limit_change,
        help="Ao mover o slider, a meta é salva imediatamente sem precisar clicar em nada!"
    )

    active_locs = cfg.get("search", {}).get("locations", ["United States", "Spain"])
    st.caption(f"🌍 Foco: **{' & '.join(active_locs)}**")

    # Alternador Rápido de Presets na Sidebar (1 Clique)
    st.markdown("### 🎯 Foco de Mercado")
    active_preset = cfg.get("search", {}).get("preset", "portugal_spain")
    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        if st.button("🇵🇹 PT & 🇪🇸 ES", type="primary" if active_preset == "portugal_spain" else "secondary", use_container_width=True, help="Portugal e Espanha (Prioridade Europa)"):
            apply_preset("portugal_spain")
            st.toast("Modo Portugal & Espanha Ativado!", icon="🇵🇹")
            st.rerun()
    with col_sb2:
        if st.button("🇪🇸 Espanha", type="primary" if active_preset == "spain" else "secondary", use_container_width=True, help="Espanha - Foco exclusivo no mercado espanhol"):
            apply_preset("spain")
            st.toast("Modo Espanha Ativado!", icon="🇪🇸")
            st.rerun()

    col_sb3, col_sb4 = st.columns(2)
    with col_sb3:
        if st.button("🌍 EUA+ES", type="primary" if active_preset == "international" else "secondary", use_container_width=True, help="EUA e Espanha - Todas as modalidades"):
            apply_preset("international")
            st.toast("Modo Internacional Ativado!", icon="🌍")
            st.rerun()
    with col_sb4:
        if st.button("🇧🇷 Brasil", type="primary" if active_preset == "brazil" else "secondary", use_container_width=True, help="Brasil - Home Office & Híbrido"):
            apply_preset("brazil")
            st.toast("Modo Brasil Ativado (Home & Híbrido)!", icon="🇧🇷")
            st.rerun()

    # Indicador de sessão
    session_ok = is_session_dir_initialized()
    if session_ok:
        st.markdown('<span class="status-pill status-online">● Sessão LinkedIn Salva</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-pill status-offline">○ Não Autenticado</span>', unsafe_allow_html=True)
        if st.button("🔑 Fazer Login 1x", use_container_width=True):
            launch_manual_login_process()
            st.toast("Janela de login aberta! Complete a autenticação.", icon="ℹ️")

    tg_status = cfg.get("telegram", {}).get("enabled", False)
    if tg_status:
        st.markdown('<span class="status-pill status-online">🔔 Telegram Ativo</span>', unsafe_allow_html=True)

    sched_status = cfg.get("scheduler", {}).get("enabled", False)
    if sched_status:
        st.caption(f"⏰ Agendador: **{smart_scheduler.get_next_run()}**")

    st.markdown("---")

    # Controles de Início / Parada
    if st.session_state.bot_running:
        st.error("● Robô em Execução...")
        if st.button("⏹ PARAR ROBÔ", type="primary", use_container_width=True):
            stop_bot_background()
            st.warning("Solicitada parada do robô...")
            time.sleep(1)
            st.rerun()
    else:
        if st.button("▶ INICIAR CANDIDATURAS", type="primary", use_container_width=True):
            start_bot_background()
            st.success("Robô iniciado em segundo plano!")
            time.sleep(1)
            st.rerun()


# ==============================================================================
# PÁGINA 1: DASHBOARD
# ==============================================================================
if page == "📊 Dashboard":
    st.title("📊 Dashboard de Candidaturas & Métricas")
    st.caption("Visão geral do desempenho do robô, aprovações e compatibilidade semântica")

    stats = tracker.get_stats()

    # Linha de Métricas
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card(
            title="Hoje",
            value=f"{stats.get('today_applied', 0)} / {max_daily}",
            delta="Cota Diária",
            icon="📅",
            bg_color="#f0fdf4",
            text_color="#15803d"
        )
    with c2:
        metric_card(
            title="Total Aplicadas",
            value=str(stats.get("applied", 0) + stats.get("dry_run", 0)),
            delta="Histórico Total",
            icon="🚀",
            bg_color="#eff6ff",
            text_color="#1d4ed8"
        )
    with c3:
        metric_card(
            title="Recrutadores",
            value=str(stats.get("recruiters_count", 0)),
            delta="Hiring Team",
            icon="🤝",
            bg_color="#fdf4ff",
            text_color="#a21caf"
        )
    with c4:
        metric_card(
            title="Match Médio",
            value=f"{stats.get('avg_match_score', 0)}%",
            delta="Compatibilidade",
            icon="🎯",
            bg_color="#fef3c7",
            text_color="#d97706"
        )
    with c5:
        metric_card(
            title="Vagas Puladas",
            value=str(stats.get("skipped", 0)),
            delta="Filtros/Match",
            icon="⏭️",
            bg_color="#f1f5f9",
            text_color="#64748b"
        )

    st.markdown("---")

    # Gráficos em 2 colunas
    col_g1, col_g2 = st.columns([3, 2])
    with col_g1:
        # Histórico diário
        with tracker._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT applied_date, COUNT(*) as count 
                FROM applications 
                WHERE status IN ('APPLIED', 'DRY_RUN')
                GROUP BY applied_date 
                ORDER BY applied_date ASC 
                LIMIT 14
            """)
            daily_rows = [dict(r) for r in cursor.fetchall()]
        st.plotly_chart(plot_daily_applications(daily_rows), use_container_width=True)

    with col_g2:
        st.plotly_chart(plot_status_distribution(stats), use_container_width=True)

    # Tabela das últimas 10 candidaturas
    st.subheader("🕒 Últimas Candidaturas Registradas")
    recent_jobs = tracker.get_recent_applications(limit=10)
    render_applications_table(recent_jobs)


# ==============================================================================
# PÁGINA 2: BUSCAR VAGAS (LIVE RUNNER)
# ==============================================================================
elif page == "🔍 Buscar Vagas":
    st.title("🔍 Busca & Execução de Candidaturas ao Vivo")
    st.caption("Acompanhe o robô em tempo real navegando e preenchendo formulários")

    cfg_run = load_config()
    current_preset = cfg_run.get("search", {}).get("preset", "international")
    current_locs = cfg_run.get("search", {}).get("locations", ["United States", "Spain"])
    wt_types = cfg_run.get("search", {}).get("workplace_types", ["remote", "hybrid", "on_site"])

    wt_desc = "Todas as modalidades"
    if set(wt_types) == {"remote", "hybrid"}:
        wt_desc = "🏠 Home Office & 🏢 Híbrido"
    elif set(wt_types) == {"remote"}:
        wt_desc = "🏠 100% Remoto"
    elif set(wt_types) == {"hybrid"}:
        wt_desc = "🏢 Híbrido"

    if current_preset == "spain":
        st.info(f"🇪🇸 **Modo Espanha Ativo:** Vagas em **{', '.join(current_locs)}** ({wt_desc} e Easy Apply)")
    elif current_preset == "international":
        st.info(f"🌍 **Modo Internacional Ativo:** Vagas em **{', '.join(current_locs)}** ({wt_desc} e Easy Apply)")
    elif current_preset == "brazil":
        st.info(f"🇧🇷 **Modo Brasil Ativo:** Vagas em **{', '.join(current_locs)}** ({wt_desc} e Easy Apply)")
    else:
        st.info(f"⚙️ **Modo Personalizado Ativo:** Vagas em **{', '.join(current_locs)}** ({wt_desc})")

    # Botões de Ação de 1 Clique
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        is_es = (current_preset == "spain")
        btn_es_label = "🇪🇸 Modo Espanha" + ("  ● ATIVO" if is_es else "")
        if st.button(btn_es_label, type="primary" if is_es else "secondary", use_container_width=True, key="quick_btn_es"):
            apply_preset("spain")
            st.toast("Modo Espanha Ativado!", icon="🇪🇸")
            st.rerun()
    with col_p2:
        is_int = (current_preset == "international")
        btn_int_label = "🌍 EUA + Espanha" + ("  ● ATIVO" if is_int else "")
        if st.button(btn_int_label, type="primary" if is_int else "secondary", use_container_width=True, key="quick_btn_int"):
            apply_preset("international")
            st.toast("Modo Internacional Ativado!", icon="🌍")
            st.rerun()
    with col_p3:
        is_br = (current_preset == "brazil")
        btn_br_label = "🇧🇷 Modo Brasil" + ("  ● ATIVO" if is_br else "")
        if st.button(btn_br_label, type="primary" if is_br else "secondary", use_container_width=True, key="quick_btn_br"):
            apply_preset("brazil")
            st.toast("Modo Brasil Ativado (Home Office & Híbrido)!", icon="🇧🇷")
            st.rerun()

    with st.expander("⚙️ Ajustar Cargos, Localizações & Presets Manualmente", expanded=False):
        search_updates = render_search_config_form(cfg_run)
        if st.button("💾 Salvar Parâmetros de Busca", key="save_search_cfg"):
            cfg_run["search"]["preset"] = search_updates.get("preset", current_preset)
            cfg_run["search"]["keywords"] = search_updates["keywords"]
            cfg_run["search"]["locations"] = search_updates["locations"]
            cfg_run["search"]["workplace_types"] = search_updates.get("workplace_types", ["remote", "hybrid", "on_site"])
            cfg_run["search"]["remote_only"] = search_updates["remote_only"]
            cfg_run["search"]["easy_apply_only"] = search_updates["easy_apply_only"]
            cfg_run["search"]["date_posted"] = search_updates["date_posted"]
            cfg_run["limits"]["max_applications_per_day"] = search_updates["max_applications_per_day"]
            if "filters" not in cfg_run:
                cfg_run["filters"] = {}
            cfg_run["filters"]["early_applicant_only"] = search_updates.get("early_applicant_only", False)
            cfg_run["filters"]["exclude_senior"] = search_updates.get("exclude_senior", True)
            save_config(cfg_run)
            st.toast("Parâmetros de busca salvos com sucesso!", icon="🎯")
            st.success("Configuração de busca atualizada!")
            st.rerun()

    # Controles no topo
    col_play, col_status = st.columns([2, 5])
    with col_play:
        if st.session_state.bot_running:
            if st.button("⏹ PARAR EXECUÇÃO", type="primary", use_container_width=True):
                stop_bot_background()
                st.warning("Parando motor...")
                time.sleep(1)
                st.rerun()
        else:
            if st.button("▶ INICIAR AGORA", type="primary", use_container_width=True):
                start_bot_background()
                st.success("Execução iniciada!")
                time.sleep(1)
                st.rerun()

    with col_status:
        if st.session_state.bot_running:
            st.info("🟢 Motor ativo: O robô está varrendo o LinkedIn e aplicando em segundo plano.")
        else:
            st.write("⚪ Motor inativo: Clique no botão ao lado para começar.")

    st.markdown("---")

    # Terminal de logs ao vivo
    st.subheader("🖥️ Terminal de Logs ao Vivo (Streaming)")
    logs = get_recent_logs(limit=60)

    log_html = '<div class="log-terminal">'
    if not logs:
        log_html += '<span style="color:#64748b;">Nenhum log registrado ainda. Inicie o robô para visualizar as ações em tempo real.</span>\n'
    else:
        for entry in logs:
            lvl = entry["level"]
            cls = "log-info"
            if lvl == "WARNING": cls = "log-warning"
            elif lvl == "ERROR": cls = "log-error"
            log_html += f'<span style="color:#64748b;">[{entry["timestamp"]}]</span> <span class="{cls}">[{lvl}]</span> {entry["message"]}\n'
    log_html += '</div>'

    st.markdown(log_html, unsafe_allow_html=True)

    col_l1, col_l2 = st.columns([1, 4])
    with col_l1:
        if st.button("🗑️ Limpar Terminal"):
            clear_logs()
            st.rerun()

    # Se estiver rodando, faz auto-refresh da página a cada 2.5 segundos
    if st.session_state.bot_running:
        time.sleep(2.5)
        st.rerun()


# ==============================================================================
# PÁGINA: RECRUTADORES & OUTREACH
# ==============================================================================
elif page == "🤝 Recrutadores & Outreach":
    st.title("🤝 Gestão de Recrutadores & Outreach")
    st.caption("Conecte-se diretamente com os recrutadores das vagas aplicadas com notas cirúrgicas personalizadas (até 200 caracteres)")

    rec_stats = tracker.get_recruiter_stats()
    r1, r2, r3, r4 = st.columns(4)
    with r1:
        metric_card("Total Mapeados", str(rec_stats.get("total", 0)), delta="Equipes identificadas", icon="👥", bg_color="#e0f2fe", text_color="#0284c7")
    with r2:
        metric_card("Pendentes", str(rec_stats.get("pending", 0)), delta="Aguardando contato", icon="⏳", bg_color="#fef3c7", text_color="#d97706")
    with r3:
        metric_card("Contatados", str(rec_stats.get("sent", 0)), delta="Convite enviado", icon="✅", bg_color="#dcfce7", text_color="#15803d")
    with r4:
        metric_card("Notas Copiadas", str(rec_stats.get("copied", 0)), delta="Prontas no clipboard", icon="📋", bg_color="#f3e8ff", text_color="#7e22ce")

    st.markdown("---")

    col_filter, col_export = st.columns([3, 1])
    with col_filter:
        status_choice = st.selectbox("Filtrar por Status de Abordagem:", ["Todos", "PENDING", "COPIED", "SENT"], index=0)

    query_status = None if status_choice == "Todos" else status_choice
    recruiters = tracker.get_recruiters(status=query_status, limit=100)

    with col_export:
        if recruiters:
            df_rec = pd.DataFrame(recruiters)
            csv_data = df_rec.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar CSV",
                data=csv_data,
                file_name="recrutadores_linkedin.csv",
                mime="text/csv",
                use_container_width=True
            )

    if not recruiters:
        st.info("Nenhum recrutador encontrado para o filtro selecionado. Quando o robô processar vagas que divulgam a equipe de contratação ('Meet the hiring team'), eles aparecerão aqui automaticamente com a mensagem personalizada pronta!")
    else:
        for rec in recruiters:
            rec_id = rec["id"]
            name = rec["recruiter_name"]
            r_title = rec["recruiter_title"] or "Hiring Team"
            company = rec["company"] or "Empresa"
            job_title = rec["job_title"] or "Vaga"
            profile_url = rec["recruiter_profile_url"]
            note = rec["outreach_note"]
            status = rec["status"]

            badge_color = "#d97706" if status == "PENDING" else ("#15803d" if status == "SENT" else "#7e22ce")
            status_label = "⏳ Pendente" if status == "PENDING" else ("✅ Enviado" if status == "SENT" else "📋 Copiado")

            with st.container():
                st.markdown(f"""
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h4 style="margin: 0; color: #0f172a; font-size: 16px;">👤 {name}</h4>
                            <span style="color: #64748b; font-size: 13px;">{r_title} • <strong>{company}</strong> (Vaga: {job_title})</span>
                        </div>
                        <span style="background-color: {badge_color}20; color: {badge_color}; border: 1px solid {badge_color}40; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">
                            {status_label}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                c_note, c_actions = st.columns([3, 1])
                with c_note:
                    st.caption("Nota de Convite de Conexão (até 200 caracteres):")
                    st.code(note, language="text")

                    # Direct Pitch Executivo de 3 Parágrafos
                    with st.expander("✨ Direct Pitch Executivo (E-mail / InMail de 3 Parágrafos)", expanded=False):
                        pitch_text = rec.get("executive_pitch")
                        if not pitch_text:
                            from core.recruiter_finder import RecruiterFinder
                            rf_temp = RecruiterFinder(None, load_profile())
                            pitch_text = rf_temp.build_executive_pitch(name, job_title, company)
                        st.caption("Mensagem estratégica completa para enviar por e-mail corporativo ou mensagem direta:")
                        st.code(pitch_text, language="text")
                with c_actions:
                    if profile_url:
                        st.link_button("🔗 Abrir no LinkedIn", profile_url, use_container_width=True)
                    if status != "SENT":
                        if st.button("🚀 Auto-Connect", key=f"autoconnect_{rec_id}", use_container_width=True, help="Envia convite com a nota de até 200 caracteres pelo Playwright"):
                            if st.session_state.get("bot_running", False):
                                st.warning("O robô principal está rodando. Pause-o temporariamente para enviar convites avulsos.")
                            else:
                                with st.spinner(f"Enviando convite para {name}..."):
                                    from core.recruiter_finder import send_connection_invite_standalone
                                    ok, reason = send_connection_invite_standalone(profile_url, (note or "")[:200].strip(), cfg)
                                    if ok:
                                        tracker.update_recruiter_status(rec_id, "SENT")
                                        st.toast(f"Convite enviado para {name}!", icon="🤝")
                                        st.rerun()
                                    else:
                                        st.error(f"Não foi possível conectar: {reason}")
                        if st.button("✅ Marcar Enviado", key=f"sent_{rec_id}", use_container_width=True):
                            tracker.update_recruiter_status(rec_id, "SENT")
                            st.rerun()
                    else:
                        if st.button("🔄 Voltar Pendente", key=f"pend_{rec_id}", use_container_width=True):
                            tracker.update_recruiter_status(rec_id, "PENDING")
                            st.rerun()
                st.markdown("<hr style='margin: 8px 0 16px 0; border: none; border-top: 1px dashed #cbd5e1;' />", unsafe_allow_html=True)


# ==============================================================================
# PÁGINA 3: PERFIL DO CANDIDATO
# ==============================================================================
elif page == "👤 Perfil do Candidato":
    st.title("👤 Perfil do Candidato & Currículo")
    st.caption("Edite suas respostas padrão, competências e anexe seu currículo em inglês")

    profile_data = load_profile()

    with st.expander("📄 Gerenciamento de Currículos em PDF (Internacional & Nacional)", expanded=True):
        tab_en, tab_pt = st.tabs(["🌍 Currículo Internacional (Inglês - EUA/Espanha)", "🇧🇷 Currículo Nacional (Português - Brasil)"])

        with tab_en:
            col_en1, col_en2 = st.columns([3, 2])
            with col_en1:
                uploaded_en = st.file_uploader("Subir Currículo em Inglês (PDF):", type=["pdf"], key="upload_cv_en")
                if uploaded_en is not None:
                    if save_uploaded_resume(uploaded_en.read(), lang="en"):
                        st.success("Currículo Internacional (resume_en.pdf) salvo com sucesso!", icon="✅")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar currículo em inglês.")

            with col_en2:
                from utils.profile_manager import get_cv_stats
                cv_stats_en = get_cv_stats("en")
                st.write("**Status do Currículo Internacional:**")
                if cv_stats_en["exists"]:
                    st.success(f"✔ **Ativo:** {cv_stats_en['word_count']} palavras extraídas.")
                    st.caption("Usado automaticamente para candidaturas internacionais nos EUA, Espanha e Europa.")
                else:
                    st.warning("⚠️ Nenhum currículo internacional PDF encontrado. Faça o upload ao lado.")

            if cv_stats_en["exists"]:
                with st.expander("👁️ Ver texto extraído do CV em Inglês (consultado pela IA):"):
                    st.text_area("Texto do CV (EN):", value=cv_stats_en["full_text"], height=140, disabled=True, key="view_cv_en")

        with tab_pt:
            col_pt1, col_pt2 = st.columns([3, 2])
            with col_pt1:
                uploaded_pt = st.file_uploader("Subir Currículo em Português (PDF):", type=["pdf"], key="upload_cv_pt")
                if uploaded_pt is not None:
                    if save_uploaded_resume(uploaded_pt.read(), lang="pt"):
                        st.success("Currículo Nacional (resume_pt.pdf) salvo com sucesso!", icon="✅")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar currículo em português.")

            with col_pt2:
                cv_stats_pt = get_cv_stats("pt")
                st.write("**Status do Currículo Nacional:**")
                if cv_stats_pt["exists"]:
                    st.success(f"✔ **Ativo:** {cv_stats_pt['word_count']} palavras extraídas.")
                    st.caption("Usado automaticamente para candidaturas a vagas brasileiras (Home Office & Híbridas).")
                else:
                    st.info("ℹ️ Nenhum currículo em português enviado ainda. Se vazio, o robô usará o currículo internacional como fallback.")

            if cv_stats_pt["exists"]:
                with st.expander("👁️ Ver texto extraído do CV em Português (consultado pela IA):"):
                    st.text_area("Texto do CV (PT):", value=cv_stats_pt["full_text"], height=140, disabled=True, key="view_cv_pt")

    st.markdown("---")
    with st.expander("🧠 Simulador & Otimizador de Palavras-Chave ATS (Filtro Americano)", expanded=False):
        st.caption("Descubra instantaneamente se o seu currículo passa nos filtros de ATS dos EUA (Workday, Greenhouse, Lever) e obtenha bullet points prontos.")
        ats_col1, ats_col2 = st.columns([2, 1])
        with ats_col1:
            ats_job_title = st.text_input("Cargo da Vaga Alvo:", value="Senior Azure Cloud & Infrastructure Engineer", key="ats_title_input")
            ats_job_desc = st.text_area(
                "Cole a descrição da vaga (Job Description):",
                value="We are looking for an Azure Cloud Engineer experienced in Terraform, Kubernetes, Linux systems administration, Docker, CI/CD pipelines with GitHub Actions, and network security (Zero Trust, Firewalls).",
                height=130,
                key="ats_desc_input"
            )
        with ats_col2:
            st.write("**Executar Diagnóstico ATS:**")
            if st.button("🔍 Analisar Compatibilidade ATS", type="primary", use_container_width=True):
                from core.ats_optimizer import ATSOptimizer
                from utils.profile_manager import get_cv_stats
                cv_text = get_cv_stats("en")["full_text"]
                optimizer = ATSOptimizer(profile_data, resume_text=cv_text)
                st.session_state["last_ats_result"] = optimizer.analyze_job(ats_job_title, ats_job_desc)

        if "last_ats_result" in st.session_state:
            res_ats = st.session_state["last_ats_result"]
            score_ats = res_ats["ats_match_percentage"]
            score_color = "#15803d" if score_ats >= 70 else ("#d97706" if score_ats >= 50 else "#dc2626")

            st.markdown(f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; margin-top: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4 style="margin: 0; color: #0f172a;">📊 Pontuação de Passagem ATS:</h4>
                    <span style="font-size: 22px; font-weight: bold; color: {score_color};">{score_ats}%</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            c_k1, c_k2 = st.columns(2)
            with c_k1:
                st.markdown("**✅ Palavras-Chave Encontradas no seu Perfil:**")
                if res_ats["matched_keywords"]:
                    matched_html = " ".join([f"<span style='background-color: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 6px; font-size: 12px; margin: 2px; display: inline-block;'>✔ {k}</span>" for k in res_ats["matched_keywords"]])
                    st.markdown(matched_html, unsafe_allow_html=True)
                else:
                    st.caption("Nenhuma correspondência direta encontrada.")

            with c_k2:
                st.markdown("**⚠️ Lacunas / Palavras Faltantes na Vaga:**")
                if res_ats["missing_keywords"]:
                    missing_html = " ".join([f"<span style='background-color: #fee2e2; color: #dc2626; padding: 3px 8px; border-radius: 6px; font-size: 12px; margin: 2px; display: inline-block;'>✖ {k}</span>" for k in res_ats["missing_keywords"]])
                    st.markdown(missing_html, unsafe_allow_html=True)
                else:
                    st.success("Seu currículo cobre 100% dos termos técnicos rastreados!")

            st.markdown("**💡 Recomendações Estratégicas:**")
            for rec in res_ats["key_recommendations"]:
                st.info(f"👉 {rec}")

            st.markdown("**📝 Bullet Points Otimizados em Inglês (Prontos para incluir no seu CV/Resumo):**")
            for bullet in res_ats["tailored_experience_bullets"]:
                st.code(f"• {bullet}", language="text")

    st.markdown("---")
    with st.form("profile_form"):
        updated_profile = render_profile_edit_form(profile_data)
        submitted = st.form_submit_button("💾 Salvar Alterações no Perfil", type="primary")
        if submitted:
            save_profile(updated_profile)
            st.toast("Perfil salvo com sucesso no profile.yaml!", icon="🎉")
            st.success("Dados do perfil atualizados!")


# ==============================================================================
# PÁGINA 4: CONFIGURAÇÕES
# ==============================================================================
elif page == "⚙️ Configurações":
    st.title("⚙️ Configurações do Robô & Inteligência Artificial")
    st.caption("Ajustes de segurança anti-bloqueio, modo de execução e provedores de IA")

    cfg = load_config()
    filters_cfg = cfg.get("filters", {})
    tg_cfg = cfg.get("telegram", {})
    sched_cfg = cfg.get("scheduler", {})

    st.subheader("🛡️ Modo de Execução & Segurança")
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        current_dry = cfg.get("bot", {}).get("dry_run", True)
        dry_run = st.toggle("Modo Simulação (Dry-Run)", value=current_dry, help="Se ativado, o robô preenche as etapas mas NÃO submete o envio final.")
        if dry_run != current_dry:
            set_dry_run(dry_run)
            st.toast(f"Modo alterado para {'SIMULAÇÃO' if dry_run else 'REAL'}!")
            st.rerun()

    with c_m2:
        headless = st.toggle("Navegador Oculto (Headless)", value=cfg.get("bot", {}).get("headless", False), help="Recomendado manter desligado para menor risco de detecção")

    st.subheader("📊 Limites Diários & Ritmo de Candidatura")
    lim_col1, lim_col2 = st.columns(2)
    with lim_col1:
        def _on_settings_limit_change():
            val = st.session_state.get("settings_max_daily_slider")
            if val is not None:
                c = load_config()
                c["limits"]["max_applications_per_day"] = int(val)
                save_config(c)

        max_daily_cfg = st.slider(
            "Limite Máximo de Candidaturas por Dia:",
            min_value=5,
            max_value=100,
            value=int(cfg.get("limits", {}).get("max_applications_per_day", 50)),
            step=5,
            key="settings_max_daily_slider",
            on_change=_on_settings_limit_change,
            help="Salvo automaticamente ao mover o slider!"
        )
    with lim_col2:
        max_pages_cfg = st.slider(
            "Páginas do LinkedIn por Termo de Busca:",
            min_value=1,
            max_value=10,
            value=int(cfg.get("limits", {}).get("max_pages_per_search", 5)),
            step=1,
            help="Quantas páginas de busca varrer para cada palavra-chave."
        )

    st.subheader("⏱️ Delays e Intervalos Humanos")
    d1, d2 = st.columns(2)
    with d1:
        min_del = st.slider("Pausa Mínima entre Ações (segundos):", 2, 20, value=int(cfg.get("limits", {}).get("min_delay_seconds", 5)))
    with d2:
        max_del = st.slider("Pausa Máxima entre Ações (segundos):", 10, 45, value=int(cfg.get("limits", {}).get("max_delay_seconds", 15)))

    st.subheader("🎯 Triagem Semântica & Abordagem")
    t1, t2, t3 = st.columns(3)
    with t1:
        min_match = st.slider("Corte Mínimo de Match (%):", 20, 80, value=int(cfg.get("limits", {}).get("min_match_score", 40)), help="Vagas com score abaixo deste valor serão puladas para economizar sua cota diária.")
    with t2:
        cover_letter_enabled = st.toggle("Cartas de Apresentação Dinâmicas", value=cfg.get("bot", {}).get("generate_cover_letter", True), help="Gera cartas contextuais automaticamente.")
    with t3:
        outreach_enabled = st.toggle("Mapear Recrutadores", value=cfg.get("bot", {}).get("recruiter_outreach", True), help="Detecta recrutadores da vaga para abordagem direta.")

    st.markdown("---")
    # 🚫 Blacklist de Empresas e Filtros Anti-Spam
    st.subheader("🚫 Blacklist de Empresas & Filtros Anti-Spam")
    st.caption("Evite consultorias massivas de body-shop (ex: BairesDev, Turing, Crossover) e cargos fora do seu objetivo.")

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        default_company_bl = "\n".join(filters_cfg.get("company_blacklist", [
            "BairesDev", "Turing", "Crossover", "Canonical", "Revature", "Dice", "CyberCoders", "Motion Recruitment"
        ]))
        company_bl_str = st.text_area(
            "Empresas Bloqueadas (uma por linha):",
            value=default_company_bl,
            height=120,
            help="O robô pulará instantaneamente qualquer vaga publicada por essas empresas."
        )
        company_bl_list = [c.strip() for c in company_bl_str.split("\n") if c.strip()]

    with b_col2:
        default_title_bl = "\n".join(filters_cfg.get("title_blacklist", [
            "Staff", "Director", "VP", "Vice President", "Head of", "Principal",
            "Software Engineer", "Software Developer", "Desenvolvedor", "Programador",
            "Desarrollador", "Full Stack", "Frontend", "Backend", "Web Developer",
            "Java Developer", "Python Developer", ".NET Developer", "Data Engineer", "QA Engineer"
        ]))
        title_bl_str = st.text_area(
            "Termos Bloqueados no Título (uma por linha):",
            value=default_title_bl,
            height=120,
            help="O robô pulará vagas cujo título contenha qualquer uma dessas palavras."
        )
        title_bl_list = [t.strip() for t in title_bl_str.split("\n") if t.strip()]

    f_col0, f_col1, f_col2 = st.columns([2, 2, 2])
    with f_col0:
        exclude_senior_toggle = st.toggle(
            "🎯 Foco Pleno / Mid-Level (Pular Sênior/Lead)",
            value=filters_cfg.get("exclude_senior", True),
            help="Descarta automaticamente vagas com 'Senior', 'Sr', 'Lead' ou 'Principal' no título para focar sua cota diária em posições Pleno/Mid-Level (calibrado para até 5 anos de experiência)."
        )
    with f_col1:
        early_app_toggle = st.toggle(
            "🥇 Ativar Filtro Early Applicant Obrigatório",
            value=filters_cfg.get("early_applicant_only", False),
            help="Apenas aplica em vagas com selo de Early Applicant ou com número baixo de concorrentes."
        )
    with f_col2:
        max_applicants_slider = st.slider(
            "Limite Máximo de Candidatos por Vaga:",
            min_value=15,
            max_value=200,
            value=int(filters_cfg.get("max_applicants_threshold", 100)),
            step=5,
            help="Vagas com número de candidatos superior a esse valor serão puladas para priorizar onde sua visibilidade é máxima."
        )

    st.markdown("---")
    # 🌎 Aceleração Internacional & Radar de Vistos
    st.subheader("🌎 Aceleração Internacional & Radar de Vistos (EUA & Europa)")
    st.caption("Filtros estratégicos para você focar onde há contratação real de brasileiros sem visto prévio.")

    int_col1, int_col2 = st.columns(2)
    with int_col1:
        only_latam_toggle = st.toggle(
            "🌎 Priorizar Vagas LatAm / Global Friendly & B2B",
            value=filters_cfg.get("only_latam_friendly", False),
            help="Pula automaticamente vagas restritas exclusivamente a residentes com cidadania americana (W-2 only / US Clearance) para poupar sua cota diária."
        )
    with int_col2:
        visa_sponsorship_toggle = st.toggle(
            "✈️ Radar Estrito: Apenas Vagas com Patrocínio de Visto / Relocação",
            value=filters_cfg.get("visa_sponsorship_only", False),
            help="Se ativado, aplica APENAS em vagas que mencionam explicitamente suporte a visto (H-1B, L-1, Visado) ou pacote de realocação internacional."
        )

    st.markdown("---")
    # 🔔 Notificações no Telegram
    st.subheader("🔔 Notificações em Tempo Real no Telegram")
    st.caption("Receba alertas no seu celular a cada candidatura aplicada e recrutador mapeado.")

    tg_col1, tg_col2, tg_col3 = st.columns([2, 3, 2])
    with tg_col1:
        telegram_active = st.toggle("Ativar Notificações no Telegram", value=tg_cfg.get("enabled", False))
    with tg_col2:
        tg_token_val = st.text_input("Token do Bot (do @BotFather):", value=tg_cfg.get("bot_token", ""), type="password", help="Exemplo: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        tg_chat_val = st.text_input("Chat ID (do @userinfobot):", value=str(tg_cfg.get("chat_id", "")), help="Seu ID numérico pessoal no Telegram (ex: 987654321)")
    with tg_col3:
        st.write("**Testar Conexão:**")
        if st.button("🔔 Enviar Mensagem de Teste", use_container_width=True):
            with st.spinner("Enviando teste ao Telegram..."):
                t_notifier = TelegramNotifier()
                ok, msg = t_notifier.test_connection(token=tg_token_val, chat_id=tg_chat_val)
                if ok:
                    st.success("Notificação de teste enviada com sucesso! Verifique seu Telegram.", icon="✅")
                else:
                    st.error(f"Erro: {msg}", icon="❌")

    with st.expander("ℹ️ Como criar seu Bot do Telegram em 1 minuto (100% Gratuito):"):
        st.markdown("""
        1. Abra o Telegram e pesquise por **@BotFather**.
        2. Envie o comando `/newbot` e escolha um nome e um username para o seu bot (ex: `MuriloVagasBot`).
        3. Copie o **HTTP API Token** gerado e cole no campo acima.
        4. No Telegram, pesquise por **@userinfobot** e dê `/start` para descobrir seu **Id** numérico.
        5. Inicie uma conversa com seu novo bot clicando nele e enviando `/start`.
        6. Cole seu Chat ID no campo acima e clique em **Enviar Mensagem de Teste**!
        """)

    st.markdown("---")
    # ⏰ Smart Scheduler & Auto-Connect
    st.subheader("⏰ Agendador Inteligente de Pico & Auto-Connect")
    st.caption("Deixe o robô rodar nos melhores horários e conectar com os recrutadores das vagas aplicadas.")

    s_col1, s_col2 = st.columns(2)
    with s_col1:
        sched_active = st.toggle("Ativar Agendamento Automático em Horários de Pico", value=sched_cfg.get("enabled", False))
        times_str = st.text_input(
            "Horários de Pico (separados por vírgula):",
            value=", ".join(sched_cfg.get("times", ["09:30", "15:00"])),
            help="Horários no formato HH:MM (ex: 09:30, 15:00)"
        )
        parsed_times = [t.strip() for t in times_str.split(",") if t.strip()]

        if sched_active:
            st.info(f"⏰ **Próxima Execução Programada:** {smart_scheduler.get_next_run()}")
        else:
            st.caption("⚪ Agendador desativado.")

    with s_col2:
        auto_connect = st.toggle(
            "🤝 Auto-Connect com Recrutadores",
            value=cfg.get("bot", {}).get("auto_connect_recruiters", False),
            help="Ao identificar um recrutador durante a candidatura, envia automaticamente um convite com nota personalizada de até 200 caracteres."
        )
        if auto_connect:
            st.success("✔ **Auto-Connect Ativo:** Recrutadores receberão convites com nota cirúrgica após a candidatura.")
        else:
            st.caption("ℹ️ Desativado: Você pode revisar e enviar manualmente pela aba 'Recrutadores & Outreach'.")

    st.markdown("---")
    st.subheader("🤖 Configuração do Provedor de IA")
    ai_cfg = cfg.get("ai", {})
    provider_opts = ["rules_only", "gemini", "openai", "ollama"]
    provider = st.selectbox(
        "Provedor de Inteligência Artificial:",
        options=provider_opts,
        index=provider_opts.index(ai_cfg.get("provider", "rules_only")),
        format_func=lambda x: {
            "rules_only": "Apenas Regras do Perfil (100% Grátis, sem chaves)",
            "gemini": "Google Gemini (Recomendado - Rápido e Gratuito via AI Studio)",
            "openai": "OpenAI (GPT-4o mini via API)",
            "ollama": "Ollama Local (100% Gratuito no PC)"
        }.get(x, x)
    )

    if provider == "gemini":
        st.info("💡 **Dica:** Você pode gerar uma chave gratuita do Gemini em menos de 1 minuto em: [Google AI Studio](https://aistudio.google.com/app/apikey)")
        gemini_key = st.text_input("GEMINI_API_KEY:", type="password", value=os.getenv("GEMINI_API_KEY", ""))
        if st.button("Salvar Chave Gemini"):
            set_api_key("GEMINI_API_KEY", gemini_key)
            st.success("Chave Gemini salva no .env!")

    elif provider == "openai":
        openai_key = st.text_input("OPENAI_API_KEY:", type="password", value=os.getenv("OPENAI_API_KEY", ""))
        if st.button("Salvar Chave OpenAI"):
            set_api_key("OPENAI_API_KEY", openai_key)
            st.success("Chave OpenAI salva no .env!")

    if st.button("💾 Salvar Ajustes Gerais"):
        cfg["bot"]["headless"] = headless
        cfg["bot"]["auto_connect_recruiters"] = auto_connect
        cfg["bot"]["generate_cover_letter"] = cover_letter_enabled
        cfg["bot"]["recruiter_outreach"] = outreach_enabled

        cfg["limits"]["max_applications_per_day"] = max_daily_cfg
        cfg["limits"]["max_pages_per_search"] = max_pages_cfg
        cfg["limits"]["min_delay_seconds"] = min_del
        cfg["limits"]["max_delay_seconds"] = max_del
        cfg["limits"]["min_match_score"] = min_match

        if "filters" not in cfg:
            cfg["filters"] = {}
        cfg["filters"]["company_blacklist"] = company_bl_list
        cfg["filters"]["title_blacklist"] = title_bl_list
        cfg["filters"]["exclude_senior"] = exclude_senior_toggle
        cfg["filters"]["early_applicant_only"] = early_app_toggle
        cfg["filters"]["max_applicants_threshold"] = max_applicants_slider
        cfg["filters"]["only_latam_friendly"] = only_latam_toggle
        cfg["filters"]["visa_sponsorship_only"] = visa_sponsorship_toggle

        if "telegram" not in cfg:
            cfg["telegram"] = {}
        cfg["telegram"]["enabled"] = telegram_active
        cfg["telegram"]["bot_token"] = tg_token_val.strip()
        cfg["telegram"]["chat_id"] = tg_chat_val.strip()

        if "scheduler" not in cfg:
            cfg["scheduler"] = {}
        cfg["scheduler"]["enabled"] = sched_active
        cfg["scheduler"]["times"] = parsed_times

        cfg["ai"]["provider"] = provider

        save_config(cfg)

        # Atualizar estado do scheduler em execução
        if sched_active and not smart_scheduler.is_running():
            smart_scheduler.start()
        elif not sched_active and smart_scheduler.is_running():
            smart_scheduler.stop()

        st.toast("Configurações salvas com sucesso!", icon="💾")
        st.success("Configurações salvas com sucesso!")
        st.rerun()

    st.markdown("---")
    st.subheader("✉️ Testar Carta de Apresentação Dinâmica")
    c_cl1, c_cl2 = st.columns(2)
    with c_cl1:
        test_company = st.text_input("Nome da Empresa:", value="Contoso Cloud Systems")
    with c_cl2:
        test_job_title = st.text_input("Cargo da Vaga:", value="Senior Azure Infrastructure Engineer")

    if st.button("Gerar Carta de Apresentação de Teste"):
        from core.cover_letter import CoverLetterGenerator
        cl_gen = CoverLetterGenerator(load_profile(), cfg)
        letter_test = cl_gen.generate_cover_letter(test_job_title, test_company, language="en")
        st.markdown("**Carta gerada sob medida para a vaga:**")
        st.code(letter_test, language="text")

    st.markdown("---")
    st.subheader("🧪 Testar Resposta da IA com base no seu Currículo")
    test_q = st.text_input("Digite uma pergunta de exemplo:", value="Can you describe your experience with cloud deployments and backend architecture?")
    if st.button("Gerar Resposta de Teste"):
        from core.ai_solver import QuestionSolver
        solver = QuestionSolver()
        with st.spinner("Consultando seu currículo e gerando resposta..."):
            ans = solver.answer_question(test_q, "textarea", [])
            st.markdown(f"**Resposta que o robô usará no formulário:**")
            st.success(ans)


# ==============================================================================
# PÁGINA 5: RELATÓRIOS & HISTÓRICO
# ==============================================================================
elif page == "📈 Relatórios & Histórico":
    st.title("📈 Relatórios Detalhados de Candidaturas")
    st.caption("Filtre, pesquise e exporte o histórico de todas as vagas processadas")

    all_jobs = tracker.get_recent_applications(limit=300)

    if not all_jobs:
        st.info("Nenhuma candidatura registrada ainda.")
    else:
        df_all = pd.DataFrame(all_jobs)

        # Filtros
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.multiselect("Filtrar por Status:", options=list(df_all["status"].unique()), default=list(df_all["status"].unique()))
        with col_f2:
            search_query = st.text_input("Pesquisar por Cargo ou Empresa:")

        df_filtered = df_all[df_all["status"].isin(status_filter)]
        if search_query:
            mask = df_filtered["title"].str.contains(search_query, case=False, na=False) | df_filtered["company"].str.contains(search_query, case=False, na=False)
            df_filtered = df_filtered[mask]

        st.metric("Total de Vagas Encontradas", len(df_filtered))
        render_applications_table(df_filtered.to_dict(orient="records"))

        # Gráfico das empresas mais frequentes
        st.markdown("---")
        with tracker._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT company, COUNT(*) as count FROM applications WHERE company != '' GROUP BY company ORDER BY count DESC LIMIT 8")
            companies_data = [dict(r) for r in cursor.fetchall()]
        if companies_data:
            st.plotly_chart(plot_top_companies(companies_data), use_container_width=True)
