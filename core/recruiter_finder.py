"""
Módulo de detecção e abordagem de recrutadores (Hiring Team) na página da vaga do LinkedIn.
Localiza os dados do recrutador e gera notas de conexão hiperpersonalizadas de até 200 caracteres.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple
from playwright.sync_api import Page, Locator

logger = logging.getLogger("AutoApplyBot")


class RecruiterFinder:
    note_quota_exhausted: bool = False

    def __init__(self, page: Optional[Page] = None, profile: Optional[Dict[str, Any]] = None):
        self.page = page
        if profile is None:
            from utils.config_manager import load_profile
            try:
                profile = load_profile()
            except Exception:
                profile = {}
        self.profile = profile or {}
        personal = self.profile.get("personal", {})
        self.candidate_name = personal.get("full_name", "Murilo Martins")

    def extract_recruiter_info(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Inspeciona a página da vaga em busca do recrutador ou equipe de contratação.
        Retorna dicionário com dados do recrutador ou None caso a vaga não divulgue.
        """
        try:
            # Seletores clássicos e modernos da seção "Meet the hiring team"
            container_selectors = [
                ".hirer-card",
                ".jobs-poster",
                "div:has-text('Meet the hiring team')",
                "div:has-text('Conheça a equipe de contratação')",
                "div:has-text('Conoce al equipo de contratación')",
                "div[data-test-hirer-card]"
            ]

            card = None
            for sel in container_selectors:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    card = loc
                    break

            if not card:
                # Tentar encontrar link direto para o perfil do anunciante
                poster_link = self.page.locator(
                    "a[data-tracking-control-name*='job_poster' i], "
                    "a[href*='/in/'][class*='poster'], "
                    ".jobs-poster__name"
                ).first
                if poster_link.count() > 0 and poster_link.is_visible():
                    name = poster_link.inner_text().strip()
                    href = poster_link.get_attribute("href") or ""
                    clean_url = href.split("?")[0] if href else ""
                    if name and "/in/" in clean_url:
                        note = self.build_connection_note(name, job.get("title", ""), job.get("company", ""), job.get("location", ""))
                        return {
                            "job_id": str(job.get("job_id", "")),
                            "name": name,
                            "title": "Recruiter / Hiring Team",
                            "profile_url": clean_url,
                            "company": job.get("company", ""),
                            "job_title": job.get("title", ""),
                            "outreach_note": note
                        }
                return None

            # Extração da URL do perfil do LinkedIn
            profile_link_elem = card.locator("a[href*='/in/']").first
            href = profile_link_elem.get_attribute("href") if profile_link_elem.count() > 0 else ""
            clean_url = href.split("?")[0] if href else ""

            # Extração de Nome
            name_elem = card.locator(
                "span.jobs-poster__name, a[href*='/in/'] strong, .hirer-card__hirer-information strong, h3"
            ).first
            name = name_elem.inner_text().strip() if name_elem.count() > 0 else ""

            # Validação anti-ruído: se o nome for genérico (ex: banner do modal), usar slug da URL
            invalid_terms = [
                "candidatura", "enviada", "compromisso", "equipe", "contratação",
                "contratacion", "hiring", "team", "meet", "status", "sucesso", "alert"
            ]
            if not name or any(t in name.lower() for t in invalid_terms) or len(name.split()) > 4:
                slug_name = self._extract_name_from_slug(clean_url)
                if slug_name:
                    name = slug_name

            # Extração de Título do Recrutador
            title_elem = card.locator(
                ".hirer-card__hirer-job-title, .jobs-poster__job-title, p.t-12"
            ).first
            title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Hiring Manager"

            if not name or not clean_url:
                return None

            # Gerar nota cirúrgica de até 200 caracteres
            note = self.build_connection_note(name, job.get("title", ""), job.get("company", ""), job.get("location", ""))
            # Gerar pitch executivo de 3 parágrafos para abordagem direta
            pitch = self.build_executive_pitch(name, job.get("title", ""), job.get("company", ""), job.get("location", ""))

            recruiter_data = {
                "job_id": str(job.get("job_id", "")),
                "name": name,
                "title": title,
                "profile_url": clean_url,
                "company": job.get("company", ""),
                "job_title": job.get("title", ""),
                "outreach_note": note,
                "executive_pitch": pitch
            }
            logger.info(f"Recrutador mapeado na vaga {job.get('job_id')}: {name} ({title})")
            return recruiter_data

        except Exception as e:
            logger.debug(f"Nenhum recrutador extraído na vaga: {e}")
            return None

    def _extract_name_from_slug(self, url: str) -> str:
        """Extrai um nome limpo e formatado a partir do slug da URL do perfil do LinkedIn."""
        match = re.search(r"/in/([a-zA-Z0-9\-_]+)", url)
        if match:
            slug = match.group(1).split("?")[0].strip("/")
            # Remover sufixos numéricos/hexadecimais comuns no LinkedIn (ex: -55b59910a)
            clean_slug = re.sub(r"-[a-f0-9]{6,}$", "", slug, flags=re.IGNORECASE)
            clean_slug = re.sub(r"-\d+$", "", clean_slug)
            parts = [p.capitalize() for p in clean_slug.split("-") if p and not p.isdigit() and len(p) > 1]
            if len(parts) >= 2:
                return " ".join(parts[:2])
            elif len(parts) == 1:
                return parts[0]
        return ""

    def build_connection_note(self, recruiter_name: str, job_title: str, company: str, location: str = "") -> str:
        """
        Gera uma nota de convite para conexão respeitando rigorosamente o limite de 200 caracteres do LinkedIn.
        Suporta Espanhol (Espanha), Português (Brasil) e Inglês (EUA / Internacional).
        """
        # Extrai o primeiro nome para uma abordagem humana e concisa
        first_name = recruiter_name.strip().split()[0] if recruiter_name else "there"
        if len(first_name) > 15:
            first_name = first_name[:13] + ".."
        clean_company = company.strip() if company else "your team"
        clean_title = job_title.strip() if job_title else "Cloud Engineer"

        # Abrevia títulos e empresas longos para nunca ultrapassar o teto
        if len(clean_title) > 28:
            clean_title = clean_title[:25] + "..."
        if len(clean_company) > 25:
            clean_company = clean_company[:22] + "..."

        loc_lower = location.lower() if location else ""
        title_lower = clean_title.lower()

        is_explicit_portugal = any(
            w in loc_lower for w in ["portugal", "lisboa", "lisbon", "porto", "braga", "coimbra", "aveiro", "faro", "setúbal", "setubal", "funchal", "leiria"]
        )

        is_explicit_spain = (
            not is_explicit_portugal
            and (
                any(w in loc_lower for w in ["spain", "españa", "madrid", "barcelona", "valencia", "sevilla", "málaga"])
                or any(w in title_lower for w in ["ingeniero", "ciberseguridad", "seguridad", "desarrollador", "administrador de sistemas"])
            )
        )

        is_explicit_brazil = (
            not is_explicit_portugal
            and not is_explicit_spain
            and (
                any(w in loc_lower for w in ["brazil", "brasil", "são paulo", "sao paulo", ", sp", " sp ", "campinas", "jundiaí", "jundiai", "rio de janeiro", "curitiba", "belo horizonte"])
                or any(w in title_lower for w in ["engenheiro", "analista", "estágio", "especialista", "segurança da informação"])
            )
        )

        if is_explicit_portugal:
            note = f"Olá {first_name}, candidatei-me a {clean_title} na {clean_company}. Foco em Cloud & Infra (AZ-104, Azure, Linux). Prazer em conectar!"
            if len(note) > 195:
                note = f"Olá {first_name}, candidatei-me a {clean_title}. Foco em Cloud & Infra (AZ-104, Azure, Linux). Prazer em conectar!"
            if len(note) > 195:
                note = f"Olá {first_name}, candidatei-me à vaga Cloud/Infra (AZ-104, Azure, Linux). Prazer em conectar!"
        elif is_explicit_spain:
            note = f"Hola {first_name}, me postulé a {clean_title} en {clean_company}. Cloud & Infra (AZ-104, Azure, Linux). ¡Un placer conectar!"
            if len(note) > 195:
                note = f"Hola {first_name}, me postulé a {clean_title}. Cloud & Infra (AZ-104, Azure, Linux). ¡Un placer conectar!"
            if len(note) > 195:
                note = f"Hola {first_name}, apliqué a su vacante Cloud/Infra (AZ-104, Azure, Linux). ¡Un placer conectar!"
        elif is_explicit_brazil:
            note = f"Olá {first_name}, apliquei para {clean_title} na {clean_company}. Foco em Cloud & Infra (AZ-104, Azure, Linux). Prazer em conectar!"
            if len(note) > 195:
                note = f"Olá {first_name}, apliquei para {clean_title}. Foco em Cloud & Infra (AZ-104, Azure, Linux). Prazer em conectar!"
            if len(note) > 195:
                note = f"Olá {first_name}, me candidatei à vaga Cloud/Infra (AZ-104, Azure, Linux). Prazer em conectar!"
        else:
            note = f"Hi {first_name}, I applied for {clean_title} at {clean_company}. Cloud/Infra Engineer (AZ-104, Azure & Linux). Would love to connect!"
            if len(note) > 195:
                note = f"Hi {first_name}, applied for {clean_title}. Cloud/Infra Engineer (AZ-104, Azure, Linux). Would love to connect!"
            if len(note) > 195:
                note = f"Hi {first_name}, applied for your Cloud/Infra role (AZ-104, Azure & Linux). Would love to connect!"

        return note.strip()[:200]

    def build_executive_pitch(self, recruiter_name: str, job_title: str, company: str, location: str = "") -> str:
        """
        Gera um pitch executivo de alto impacto de 3 parágrafos para abordagem direta ao Tech Lead / Recrutador.
        Adequado para E-mail frio, mensagem direta ou InMail.
        Disponível em Português (Portugal/Brasil), Espanhol (Espanha) ou Inglês (EUA/Global).
        """
        first_name = recruiter_name.strip().split()[0] if recruiter_name else "there"
        clean_company = company.strip() if company else "your team"
        clean_title = job_title.strip() if job_title else "Cloud Engineer"

        loc_lower = location.lower() if location else ""
        is_portugal = any(w in loc_lower for w in ["portugal", "lisboa", "lisbon", "porto", "braga", "coimbra"])
        is_spanish = any(w in loc_lower for w in ["spain", "españa", "madrid", "barcelona", "valencia"]) or any(w in clean_title.lower() for w in ["ingeniero", "sistemas", "redes"])

        if is_portugal:
            pitch = (
                f"Assunto: Candidatura: {clean_title} — Murilo Martins (Engenheiro Cloud Azure AZ-104)\n\n"
                f"Olá {first_name},\n\n"
                f"Apresento a minha candidatura à posição de {clean_title} na {clean_company}. "
                f"Acompanho com grande interesse a evolução técnica da equipa e a infraestrutura tecnológica desenvolvida.\n\n"
                f"Possuo mais de 4 anos de experiência prática na conceção, administração e segurança de ambientes Microsoft Azure e Linux. "
                f"Detenho a certificação oficial Microsoft Certified: Azure Administrator Associate (AZ-104), experiência consolidada em redes, "
                f"firewalls Fortinet (FSSO), SIEM (Wazuh) e automação de rotinas em Python e Bash. Estou disponível para início imediato sob contrato internacional "
                f"B2B (prestação de serviços com emissão de fatura) ou regime de vistos / relocalização.\n\n"
                f"Teria todo o gosto em realizar uma breve conversa de 15 minutos para partilhar como a minha experiência pode acrescentar valor imediato à equipa da {clean_company}.\n\n"
                f"Com os melhores cumprimentos,\n\n"
                f"Murilo Martins\n"
                f"Engenheiro de Cloud e Infraestrutura\n"
                f"LinkedIn: https://www.linkedin.com/in/murilo-martins-0b9938186 | GitHub: https://github.com/murilorosa-beep"
            )
        elif is_spanish:
            pitch = (
                f"Asunto: Candidatura: {clean_title} — Murilo Martins (Ingeniero Cloud Azure AZ-104)\n\n"
                f"Hola {first_name},\n\n"
                f"Le escribo para presentarme tras haberme postulado a la posición de {clean_title} en {clean_company}. "
                f"Sigo de cerca los proyectos tecnológicos del equipo y me entusiasma la oportunidad de colaborar en su infraestructura.\n\n"
                f"Cuento con más de 4 años de experiencia práctica en diseño, administración y seguridad de infraestructuras en Microsoft Azure y Linux. "
                f"Cuento con la certificación oficial Azure Administrator Associate (AZ-104), sólida trayectoria en redes empresariales, cortafuegos Fortinet "
                f"y automatización de despliegues (Python, Bash). Cuento con disponibilidad inmediata para iniciar bajo modelo de contrato internacional (B2B / Autónomo) "
                f"o mediante visado / relocalización.\n\n"
                f"Me encantaría tener una breve charla de 15 minutos para comentar cómo mi experiencia técnica puede aportar valor inmediato al equipo de {clean_company}.\n\n"
                f"Un cordial saludo,\n\n"
                f"Murilo Martins\n"
                f"Ingeniero de Cloud e Infraestructura\n"
                f"LinkedIn: https://www.linkedin.com/in/murilo-martins-0b9938186 | GitHub: https://github.com/murilorosa-beep"
            )
        else:
            pitch = (
                f"Subject: Application: {clean_title} — Murilo Martins (AZ-104 Certified Cloud & Infrastructure Engineer)\n\n"
                f"Hi {first_name},\n\n"
                f"I recently submitted my application for the {clean_title} position at {clean_company} and wanted to reach out directly "
                f"to express my enthusiasm for what your engineering team is building.\n\n"
                f"With over 4 years of hands-on experience specializing in Microsoft Azure, Linux systems administration, network security, and infrastructure automation, "
                f"I help teams build resilient, scalable, and secure cloud environments. My background includes holding the Microsoft Certified: Azure Administrator Associate (AZ-104) "
                f"credential, deploying zero-trust security postures (Firewalls, SIEM/Wazuh), and automating operational routines via Python and Shell scripting. "
                f"I am immediately available to start remotely under international B2B contractor terms (W-8BEN / Deel) or via visa sponsorship / relocation.\n\n"
                f"I would welcome the opportunity to connect for a brief 15-minute introductory conversation to discuss how my skill set aligns with your current technical priorities at {clean_company}.\n\n"
                f"Best regards,\n\n"
                f"Murilo Martins\n"
                f"Cloud & Infrastructure Engineer\n"
                f"LinkedIn: https://www.linkedin.com/in/murilo-martins-0b9938186 | GitHub: https://github.com/murilorosa-beep"
            )

        return pitch

    def send_connection_invite(self, recruiter_profile_url: str, note: str) -> Tuple[bool, str]:
        """
        Navega até o perfil do recrutador e envia um convite de conexão com nota personalizada (Playwright).
        Retorna (sucesso, mensagem).
        """
        import time
        if not recruiter_profile_url or "/in/" not in recruiter_profile_url:
            return False, "URL de perfil do LinkedIn inválida."

        try:
            logger.info(f"Navegando para perfil do recrutador: {recruiter_profile_url}")
            self.page.goto(recruiter_profile_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(2.5)

            # Verificar se já é conexão de 1º grau ou pendente
            page_text = self.page.inner_text("body").lower()
            if "pending" in page_text or "pendente" in page_text:
                return True, "Convite de conexão já estava pendente."
            if "1st" in page_text or "1º" in page_text:
                return True, "Você já está conectado com este recrutador."

            # 1. Tentar encontrar botão Conectar no top-card principal
            connect_btn = None
            top_card = self.page.locator(".pv-top-card-v2-ctas, .pvs-profile-actions, main section").first

            direct_connect_selectors = [
                "button:has-text('Connect')",
                "button:has-text('Conectar')",
                "button[aria-label*='Connect' i]",
                "button[aria-label*='Conectar' i]"
            ]
            for sel in direct_connect_selectors:
                loc = top_card.locator(sel).first if top_card.count() > 0 else self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    connect_btn = loc
                    break

            # 2. Se não encontrou direto (ex: perfil com 'Seguir' ou 'Mensagem'), abrir o menu 'Mais' / 'More'
            if not connect_btn:
                more_selectors = [
                    "button:has-text('Mais')",
                    "button:has-text('More')",
                    "button[aria-label*='Mais ações' i]",
                    "button[aria-label*='More actions' i]"
                ]
                more_btn = None
                for m_sel in more_selectors:
                    loc = top_card.locator(m_sel).first if top_card.count() > 0 else self.page.locator(m_sel).first
                    if loc.count() > 0 and loc.is_visible():
                        more_btn = loc
                        break

                if more_btn:
                    more_btn.click(force=True)
                    time.sleep(1.2)

                    dropdown_connect = self.page.locator(
                        "div[role='menu'] span:has-text('Conectar'), div[role='menu'] span:has-text('Connect'), "
                        "div[role='menu'] div:has-text('Conectar'), div[role='menu'] div:has-text('Connect'), "
                        "div[role='menu'] button:has-text('Conectar'), div[role='menu'] button:has-text('Connect')"
                    ).first
                    if dropdown_connect.count() > 0 and dropdown_connect.is_visible():
                        connect_btn = dropdown_connect

            if not connect_btn:
                return False, "Botão 'Conectar' não disponível no perfil (pode ser restrito a InMail ou Seguir)."

            # Clicar no botão Conectar com force=True para contornar a barra fixa do LinkedIn
            connect_btn.click(force=True)
            time.sleep(2.0)

            # 3. Localizar o modal VISÍVEL de convite
            dialog = self.page.locator("div[role='dialog']:visible, .artdeco-modal:visible").first
            try:
                dialog.wait_for(state="visible", timeout=4000)
            except Exception:
                pass

            if dialog.count() == 0 or not dialog.is_visible():
                return False, "Modal de convite não foi exibido."

            # Verificar se há pergunta intermediária 'Como você conhece esta pessoa?'
            other_option = dialog.locator(
                "button:has-text('Outro'), button:has-text('Other'), button:has-text('Otro'), "
                "span:has-text('Outro'), span:has-text('Other'), label:has-text('Outro')"
            ).first
            if other_option.count() > 0 and other_option.is_visible():
                try:
                    other_option.click(force=True)
                    time.sleep(0.8)
                    connect_advance = dialog.locator(
                        "button.artdeco-button--primary, button:has-text('Conectar'), button:has-text('Connect')"
                    ).first
                    if connect_advance.count() > 0 and connect_advance.is_visible():
                        connect_advance.click(force=True)
                        time.sleep(1.5)
                        dialog = self.page.locator("div[role='dialog']:visible, .artdeco-modal:visible").first
                except Exception:
                    pass

            # 4. Envio do convite: Com nota personalizada ou Padrão (Sem nota)
            note_filled = False
            upsell_detected = False

            # Se a cota mensal gratuita de notas ainda não foi detectada como esgotada
            if not RecruiterFinder.note_quota_exhausted:
                add_note_btn = dialog.locator(
                    "button:has-text('Adicionar nota'), button:has-text('Add a note'), button:has-text('Añadir una nota'), button:has-text('Añadir nota'), "
                    "button[aria-label*='Adicionar nota' i], button[aria-label*='Add a note' i], button[aria-label*='Añadir' i]"
                ).first

                if add_note_btn.count() > 0 and add_note_btn.is_visible():
                    try:
                        add_note_btn.click(force=True)
                        time.sleep(1.2)

                        # Verificar se abriu o textarea ou se o LinkedIn exibiu o paywall de notas gratuitas esgotadas
                        current_dialog = self.page.locator("div[role='dialog']:visible, .artdeco-modal:visible").first
                        textarea = current_dialog.locator("textarea#custom-message, textarea[name='message'], textarea").first
                        current_text = current_dialog.inner_text().lower()

                        is_premium_upsell = (textarea.count() == 0 or not textarea.is_visible()) and any(w in current_text for w in [
                            "não tem notas personalizadas gratuitas", "no tienes notas personalizadas gratuitas",
                            "out of free personalized notes", "personalizados você quiser com premium",
                            "personalizadas você quiser com premium", "assine o premium", "try premium"
                        ])

                        if is_premium_upsell:
                            logger.info("Cota de notas personalizadas gratuitas do LinkedIn esgotada nesta conta. Alternando para convite padrão sem nota.")
                            RecruiterFinder.note_quota_exhausted = True
                            upsell_detected = True

                            # Fechar modal de upsell do Premium
                            dismiss_btn = current_dialog.locator(
                                "button.artdeco-modal__dismiss, button[aria-label*='Dismiss' i], button[aria-label*='Fechar' i], button[aria-label*='Close' i]"
                            ).first
                            if dismiss_btn.count() > 0:
                                dismiss_btn.click(force=True)
                                time.sleep(1.2)

                            # Re-abrir o fluxo de conexão limpo para enviar sem nota
                            if not (connect_btn and connect_btn.count() > 0 and connect_btn.is_visible()):
                                top_card = self.page.locator(".pv-top-card-v2-ctas, .pvs-profile-actions, main section").first
                                for sel in direct_connect_selectors:
                                    loc = top_card.locator(sel).first if top_card.count() > 0 else self.page.locator(sel).first
                                    if loc.count() > 0 and loc.is_visible():
                                        connect_btn = loc
                                        break
                                if not connect_btn or not connect_btn.is_visible():
                                    more_btn = top_card.locator("button:has-text('Mais'), button:has-text('More')").first
                                    if more_btn.count() > 0 and more_btn.is_visible():
                                        more_btn.click(force=True)
                                        time.sleep(1.0)
                                        connect_btn = self.page.locator(
                                            "div[role='menu'] span:has-text('Conectar'), div[role='menu'] span:has-text('Connect'), "
                                            "div[role='menu'] div:has-text('Conectar'), div[role='menu'] div:has-text('Connect')"
                                        ).first

                            if connect_btn and connect_btn.count() > 0 and connect_btn.is_visible():
                                connect_btn.click(force=True)
                                time.sleep(1.5)
                                dialog = self.page.locator("div[role='dialog']:visible, .artdeco-modal:visible").first
                        elif textarea.count() > 0 and textarea.is_visible():
                            clean_note = note.strip()[:200]
                            textarea.click(force=True)
                            textarea.fill(clean_note)
                            textarea.dispatch_event("input")
                            time.sleep(1.0)
                            note_filled = True
                            dialog = current_dialog
                            logger.info(f"Nota personalizada preenchida com sucesso ({len(clean_note)} caracteres).")
                    except Exception as note_e:
                        logger.debug(f"Não foi possível anexar nota: {note_e}")

            # 5. Localizar e clicar no botão Enviar ESCOPADAMENTE NO MODAL ATIVO
            send_btn = dialog.locator(
                "button:has-text('Enviar sem nota'):visible, button:has-text('Send without a note'):visible, "
                "button:has-text('Enviar sin nota'):visible, button.artdeco-button--primary:visible, "
                "button:has-text('Enviar'):visible, button:has-text('Send'):visible, "
                "button:has-text('Send now'):visible, button:has-text('Enviar ahora'):visible, "
                "button[aria-label*='Enviar' i]:visible, button[aria-label*='Send' i]:visible"
            ).first

            if send_btn.count() > 0 and send_btn.is_visible():
                send_btn.click(force=True)
                time.sleep(2.5)
                if note_filled:
                    msg_status = "com nota personalizada"
                elif upsell_detected or RecruiterFinder.note_quota_exhausted:
                    msg_status = "padrão sem nota (cota mensal gratuita de notas do LinkedIn esgotada)"
                else:
                    msg_status = "padrão (sem nota)"
                logger.info(f"Convite de conexão ({msg_status}) enviado com sucesso para {recruiter_profile_url}!")
                return True, f"Convite de conexão ({msg_status}) enviado com sucesso!"

            return False, "Botão 'Enviar' do convite não encontrado no modal."

        except Exception as e:
            logger.warning(f"Erro ao enviar convite para recrutador: {e}")
            return False, f"Erro ao enviar convite: {str(e)}"


def send_connection_invite_standalone(profile_url: str, note: str, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Abre uma sessão temporária do Playwright com perfil seguro,
    envia o convite de conexão com nota personalizada e encerra o navegador.
    """
    from core.browser import BrowserManager
    from utils.config_manager import load_config, load_profile

    cfg = config or load_config()
    prof = load_profile()
    session_dir = cfg.get("bot", {}).get("session_dir", ".session")
    headless = cfg.get("bot", {}).get("headless", False)

    bm = BrowserManager(session_dir=session_dir, headless=headless)
    try:
        page = bm.start()
        rf = RecruiterFinder(page, prof)
        success, msg = rf.send_connection_invite(profile_url, note)
        return success, msg
    except Exception as e:
        return False, f"Falha ao enviar convite: {str(e)}"
    finally:
        try:
            bm.close()
        except Exception:
            pass

