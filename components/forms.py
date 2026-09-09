"""
Componentes de formulários para configuração de busca, perfil do candidato e ajustes do bot.
"""

import streamlit as st
from typing import Dict, Any, Tuple
from utils.config_manager import apply_preset


def render_search_config_form(current_config: Dict[str, Any]) -> Dict[str, Any]:
    """Renderiza o formulário de filtros e parâmetros de busca com suporte a presets Internacional e Brasil."""
    search_cfg = current_config.get("search", {})
    limits_cfg = current_config.get("limits", {})
    current_preset = search_cfg.get("preset", "international")

    st.subheader("🎯 Configuração & Presets de Busca")

    # Botões de Preset de 1 Clique
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    
    preset_keywords_pt_es = [
        "Cloud Engineer", "Engenheiro Cloud", "DevOps Engineer", "Engenheiro DevOps",
        "Azure Administrator", "Administrador de Sistemas", "Infrastructure Engineer",
        "Engenheiro de Infraestrutura", "Cloud Security Engineer", "Linux Systems Engineer",
        "Engenheiro de Redes", "Systems Administrator", "Ingeniero Cloud",
        "Ingeniero DevOps", "Técnico de Sistemas"
    ]
    preset_keywords_es = [
        "Ingeniero Cloud", "Administrador de Sistemas", "Ingeniero DevOps",
        "Ingeniero de Ciberseguridad", "Azure Administrator", "Cloud Engineer",
        "Infrastructure Engineer", "Cloud Security Engineer", "Linux Systems Engineer",
        "Administrador de Redes", "Técnico de Sistemas"
    ]
    preset_keywords_int = [
        "Azure Cloud Engineer", "Cloud Engineer", "Infrastructure Engineer",
        "Cloud Security Engineer", "Linux Systems Engineer", "Azure Administrator",
        "DevOps Engineer", "Ingeniero Cloud", "Ingeniero DevOps",
        "Administrador de Sistemas", "Ingeniero de Ciberseguridad"
    ]
    preset_keywords_br = [
        "Engenheiro de Cloud", "Analista de Infraestrutura", "Engenheiro DevOps",
        "Especialista Azure", "Administrador de Redes", "Analista de Segurança da Informação",
        "Analista de Suporte e Infraestrutura", "Analista de Redes", "Engenheiro de Redes"
    ]

    selected_preset = current_preset
    with col_p1:
        if st.button("🇵🇹 PT & 🇪🇸 ES (Europa)", use_container_width=True, type="primary" if current_preset == "portugal_spain" else "secondary", key="form_btn_pt_es"):
            apply_preset("portugal_spain")
            st.session_state["form_keywords"] = "\n".join(preset_keywords_pt_es)
            st.session_state["form_locations"] = ["Portugal", "Spain", "European Union"]
            st.session_state["form_workplace"] = "all"
            st.rerun()

    with col_p2:
        if st.button("🇪🇸 Apenas Espanha", use_container_width=True, type="primary" if current_preset == "spain" else "secondary", key="form_btn_es"):
            apply_preset("spain")
            st.session_state["form_keywords"] = "\n".join(preset_keywords_es)
            st.session_state["form_locations"] = ["Spain"]
            st.session_state["form_workplace"] = "all"
            st.rerun()

    with col_p3:
        if st.button("🌍 EUA + ES", use_container_width=True, type="primary" if current_preset == "international" else "secondary", key="form_btn_int"):
            apply_preset("international")
            st.session_state["form_keywords"] = "\n".join(preset_keywords_int)
            st.session_state["form_locations"] = ["United States", "Spain"]
            st.session_state["form_workplace"] = "all"
            st.rerun()

    with col_p4:
        if st.button("🇧🇷 Brasil", use_container_width=True, type="primary" if current_preset == "brazil" else "secondary", key="form_btn_br"):
            apply_preset("brazil")
            st.session_state["form_keywords"] = "\n".join(preset_keywords_br)
            st.session_state["form_locations"] = ["Brazil", "São Paulo, Brazil", "Campinas, São Paulo, Brazil"]
            st.session_state["form_workplace"] = "remote_hybrid"
            st.rerun()

    if selected_preset == "portugal_spain":
        st.info("🇵🇹 **Modo Portugal & Espanha (Europa) Ativo:** Prioridade máxima em Portugal, seguido por Espanha e União Europeia. Termos em português, espanhol e inglês.")
    elif selected_preset == "spain":
        st.info("🇪🇸 **Modo Espanha Ativo:** Foco exclusivo no mercado espanhol com termos em espanhol e inglês (Ingeniero Cloud, Administrador de Sistemas, Azure, DevOps).")
    elif selected_preset == "international":
        st.info("🌍 **Modo Internacional Ativo:** Busca aberta a qualquer modalidade (Remoto, Híbrido ou Presencial/Relocação) nos EUA e Espanha.")
    elif selected_preset == "brazil":
        st.info("🇧🇷 **Modo Brasil Ativo:** Foco estrito em vagas **Home Office (100% Remotas) e Híbridas** com termos em português.")
    else:
        st.caption("⚙️ **Modo Personalizado:** Você tem controle manual total de cada filtro.")

    st.markdown("---")

    # Valores iniciais baseados na sessão ou config
    default_kw_str = st.session_state.get("form_keywords", "\n".join(search_cfg.get("keywords", preset_keywords_int)))
    default_locs = st.session_state.get("form_locations", search_cfg.get("locations", ["United States", "Spain"]))

    col1, col2 = st.columns(2)
    with col1:
        keywords_str = st.text_area(
            "Cargos / Palavras-chave (uma por linha):",
            value=default_kw_str,
            height=130,
            help="Cargos desejados alinhados ao seu perfil e ao mercado selecionado"
        )
        keywords = [k.strip() for k in keywords_str.split("\n") if k.strip()]

    with col2:
        locations_opts = [
            "United States", "Spain", "Brazil", "São Paulo, Brazil", "Campinas, São Paulo, Brazil",
            "European Union", "Worldwide", "Latin America", "Canada", "Remote"
        ]
        # Garantir que as localizações atuais estejam na lista de opções
        for loc in default_locs:
            if loc not in locations_opts:
                locations_opts.append(loc)

        locations = st.multiselect(
            "Localizações Alvo:",
            options=locations_opts,
            default=default_locs,
            help="Países ou cidades para busca de vagas"
        )

    st.markdown("---")
    col3, col4, col5 = st.columns(3)

    with col3:
        # Seletor de Modalidades de Trabalho
        workplace_opts = {
            "all": "🌐 Todas (Remoto, Híbrido, Presencial)",
            "remote_hybrid": "🏠+🏢 Home Office & Híbrido",
            "remote": "🏠 Apenas Home Office (100% Remoto)",
            "hybrid": "🏢 Apenas Híbrido"
        }
        current_wt = search_cfg.get("workplace_types", ["remote", "hybrid", "on_site"])
        default_wt_key = "all"
        if set(current_wt) == {"remote", "hybrid"}:
            default_wt_key = "remote_hybrid"
        elif set(current_wt) == {"remote"}:
            default_wt_key = "remote"
        elif set(current_wt) == {"hybrid"}:
            default_wt_key = "hybrid"

        if "form_workplace" in st.session_state:
            default_wt_key = st.session_state["form_workplace"]

        selected_wt_key = st.selectbox(
            "Modalidade de Trabalho:",
            options=list(workplace_opts.keys()),
            format_func=lambda x: workplace_opts.get(x, x),
            index=list(workplace_opts.keys()).index(default_wt_key) if default_wt_key in workplace_opts else 0,
            help="No mercado internacional recomenda-se 'Todas as Modalidades'; no Brasil, 'Home Office & Híbrido'."
        )

        easy_apply_only = st.toggle("Apenas Easy Apply (Candidatura Simplificada)", value=search_cfg.get("easy_apply_only", True))

    filters_cfg = current_config.get("filters", {})

    with col4:
        date_opts = {"past_24h": "Últimas 24 horas", "past_week": "Última semana", "past_month": "Último mês"}
        current_date = search_cfg.get("date_posted", "past_week")
        date_posted = st.selectbox(
            "Data de Publicação:",
            options=list(date_opts.keys()),
            format_func=lambda x: date_opts.get(x, x),
            index=list(date_opts.keys()).index(current_date) if current_date in date_opts else 1
        )
        exclude_senior = st.toggle(
            "🎯 Foco Pleno / Mid-Level",
            value=filters_cfg.get("exclude_senior", True),
            help="Pula automaticamente vagas com 'Senior', 'Sr', 'Lead' ou 'Principal' no título, focando em vagas Pleno/Mid-Level (calibrado para até 5 anos de experiência)."
        )
        early_applicant_only = st.toggle(
            "🥇 Filtro Early Applicant",
            value=filters_cfg.get("early_applicant_only", False),
            help="Aplica apenas em vagas com menos de 100 candidatos ou selo de 'Early Applicant' para chegar na frente dos concorrentes!"
        )

    with col5:
        def _on_form_limit_change():
            val = st.session_state.get("form_max_daily_slider")
            if val is not None:
                from utils.config_manager import load_config as _lc, save_config as _sc
                c = _lc()
                c["limits"]["max_applications_per_day"] = int(val)
                _sc(c)

        max_daily = st.slider(
            "Limite Diário de Candidaturas:",
            min_value=5,
            max_value=100,
            value=int(limits_cfg.get("max_applications_per_day", 50)),
            step=5,
            key="form_max_daily_slider",
            on_change=_on_form_limit_change,
            help="Salvo automaticamente ao mover o slider!"
        )

    # Converter chave de modalidade para a lista de workplace_types
    if selected_wt_key == "all":
        workplace_types_list = ["remote", "hybrid", "on_site"]
    elif selected_wt_key == "remote_hybrid":
        workplace_types_list = ["remote", "hybrid"]
    elif selected_wt_key == "remote":
        workplace_types_list = ["remote"]
    else:
        workplace_types_list = ["hybrid"]

    return {
        "preset": selected_preset,
        "keywords": keywords,
        "locations": locations,
        "workplace_types": workplace_types_list,
        "remote_only": selected_wt_key == "remote",
        "easy_apply_only": easy_apply_only,
        "early_applicant_only": early_applicant_only,
        "exclude_senior": exclude_senior,
        "date_posted": date_posted,
        "max_applications_per_day": max_daily
    }


def render_profile_edit_form(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Renderiza os formulários de edição dos dados pessoais, respostas nacionais/internacionais e competências."""
    personal = profile.get("personal", {})
    links = profile.get("links", {})
    work_auth = profile.get("work_authorization", {})
    skills = profile.get("skills_experience_years", {})
    summary = profile.get("professional_summary", "")

    st.subheader("👤 Dados Pessoais & Contato")
    c1, c2, c3 = st.columns(3)
    with c1:
        first_name = st.text_input("Primeiro Nome:", value=personal.get("first_name", "Murilo"))
        email = st.text_input("E-mail:", value=personal.get("email", "murilo.gmartins@outlook.com"))
    with c2:
        last_name = st.text_input("Sobrenome:", value=personal.get("last_name", "Martins"))
        phone_code = st.text_input("DDI do País:", value=personal.get("phone_country_code", "+55"))
    with c3:
        phone_num = st.text_input("Telefone (com DDD):", value=personal.get("phone_national", "11996697230"))
        city = st.text_input("Cidade / Estado:", value=f"{personal.get('city', 'Jundiaí')} - {personal.get('state', 'São Paulo')}")

    st.subheader("🔗 Links & Portfólio")
    l1, l2, l3, l4 = st.columns(4)
    with l1:
        linkedin = st.text_input("LinkedIn URL:", value=links.get("linkedin", "https://www.linkedin.com/in/murilo-martins-0b9938186"))
    with l2:
        github = st.text_input("GitHub URL:", value=links.get("github", "https://github.com/murilorosa-beep"))
    with l3:
        portfolio = st.text_input("Projeto #1 (NetVision):", value=links.get("portfolio", "https://github.com/murilorosa-beep/netvision"))
    with l4:
        portfolio_dr = st.text_input("Projeto #2 (Multi-Cloud DR):", value=links.get("portfolio_dr", "https://github.com/murilorosa-beep/secure-multicloud-backup-dr"))

    st.subheader("🇧🇷 Respostas para Vagas no Brasil (Home Office & Híbrido)")
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        salary_brl_monthly = st.text_input("Pretensão Mensal R$ (máx):", value=str(work_auth.get("desired_salary_brl_monthly", "5000")), help="Calibrada para no máximo R$ 5.000/mês para excelente aprovação")
    with b2:
        salary_brl_annual = st.text_input("Pretensão Anual R$:", value=str(work_auth.get("desired_salary_brl_annual", "60000")))
    with b3:
        contract_type = st.selectbox("Regime de Contratação:", ["CLT ou PJ (Flexível)", "Apenas CLT", "Apenas PJ"], index=0)
    with b4:
        hybrid_sp = st.selectbox("Disponibilidade Híbrida (SP/Campinas/Jundiaí):", ["Sim", "Não"], index=0)

    st.subheader("🌍 Respostas Internacionais (EUA & Espanha)")
    w1, w2, w3, w4 = st.columns(4)
    with w1:
        auth_us = st.selectbox("Autorização de trabalho nos EUA?", ["Yes", "No"], index=0 if work_auth.get("authorized_in_us", "Yes") == "Yes" else 1)
        auth_spain = st.selectbox("Autorização na Espanha / UE?", ["Yes", "No"], index=0 if work_auth.get("authorized_in_spain", "Yes") == "Yes" else 1)
    with w2:
        sponsorship = st.selectbox("Necessita de visto (Sponsorship)?", ["No", "Yes"], index=0 if work_auth.get("requires_sponsorship", "No") == "No" else 1)
        contractor = st.selectbox("Aceita B2B / Autónomo Espanha?", ["Yes", "No"], index=0)
    with w3:
        english = st.selectbox("Nível de Inglês:", ["Fluent", "Native", "Professional", "Intermediate"], index=0)
        spanish = st.selectbox("Nível de Espanhol:", ["Professional", "Fluent", "Native", "Intermediate"], index=0)
    with w4:
        salary_usd = st.text_input("Pretensão Anual USD ($):", value=str(work_auth.get("desired_salary_usd_annual", "75000")))
        salary_eur = st.text_input("Pretensão Anual EUR (€):", value=str(work_auth.get("desired_salary_eur_annual", "45000")))

    st.subheader("💻 Anos de Experiência por Tecnologia")
    st.caption("Usado pelo robô para preencher perguntas como: 'How many years of experience do you have with Azure?' ou 'Quantos anos de experiência com Linux?'")

    tech_cols = st.columns(4)
    common_techs = [
        "azure", "linux", "networking", "cybersecurity",
        "fortigate", "wazuh", "python", "docker",
        "windows_server", "active_directory", "sql", "proxmox"
    ]
    updated_skills = dict(skills)

    for idx, tech in enumerate(common_techs):
        col = tech_cols[idx % 4]
        val = int(skills.get(tech, 4 if tech in ["azure", "linux", "networking", "cybersecurity"] else 3))
        display_name = tech.replace("_", " ").title()
        updated_skills[tech] = col.number_input(f"{display_name} (anos):", min_value=0, max_value=30, value=val, key=f"tech_{tech}")

    st.subheader("📝 Resumo Profissional (para IA)")
    prof_summary = st.text_area(
        "Mini-bio profissional para a IA usar em perguntas abertas:",
        value=summary,
        height=100
    )

    return {
        "personal": {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "headline": personal.get("headline", "Cloud & Infrastructure Engineer"),
            "email": email,
            "phone_country_code": phone_code,
            "phone_national": phone_num,
            "phone_formatted": f"{phone_code} {phone_num[:2]} {phone_num[2:]}" if len(phone_num) > 9 else personal.get("phone_formatted", "+55 11 99669-7230"),
            "country": personal.get("country", "Brazil"),
            "city": personal.get("city", "Jundiaí"),
            "state": personal.get("state", "São Paulo"),
            "postal_code": personal.get("postal_code", "13200-000"),
            "address": personal.get("address", "Jundiaí, São Paulo, Brazil")
        },
        "links": {
            "linkedin": linkedin,
            "github": github,
            "portfolio": portfolio,
            "portfolio_dr": portfolio_dr
        },
        "work_authorization": {
            "authorized_in_us": auth_us,
            "authorized_in_spain": auth_spain,
            "authorized_in_eu": auth_spain,
            "authorized_in_brazil": "Yes",
            "requires_sponsorship": sponsorship,
            "open_to_contractor_b2b": contractor,
            "open_to_autonomo_spain": contractor,
            "has_nie_dni": work_auth.get("has_nie_dni", "No"),
            "nie_dni_status": work_auth.get("nie_dni_status", "En trámite / Contrato B2B Internacional"),
            "english_proficiency": english,
            "spanish_proficiency": spanish,
            "portuguese_proficiency": "Native",
            "notice_period_weeks": work_auth.get("notice_period_weeks", "Immediate"),
            "incorporacion_es": "Inmediata",
            "desired_salary_usd_annual": salary_usd,
            "desired_hourly_usd": work_auth.get("desired_hourly_usd", "40"),
            "desired_salary_eur_annual": salary_eur,
            "desired_hourly_eur": work_auth.get("desired_hourly_eur", "30"),
            "desired_salary_brl_monthly": salary_brl_monthly,
            "desired_salary_brl_annual": salary_brl_annual,
            "desired_hourly_brl": work_auth.get("desired_hourly_brl", "32"),
            "preferred_contract_type": contract_type,
            "comfortable_with_hybrid": "Yes" if hybrid_sp == "Sim" else "No",
            "has_cnpj": "Yes",
            "comfortable_with_remote": "Yes",
            "willing_to_relocate": "No"
        },
        "skills_experience_years": updated_skills,
        "professional_summary": prof_summary
    }
