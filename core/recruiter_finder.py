"""
Módulo de detecção e abordagem de recrutadores (Hiring Team) na página da vaga do LinkedIn.
Localiza os dados do recrutador e gera notas de conexão hiperpersonalizadas de até 300 caracteres.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple
from playwright.sync_api import Page, Locator

logger = logging.getLogger("AutoApplyBot")


class RecruiterFinder:
    def __init__(self, page: Page, profile: Dict[str, Any]):
        self.page = page
        self.profile = profile
        personal = profile.get("personal", {})
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

            # Gerar nota cirúrgica de até 300 caracteres
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
        Gera uma nota de convite para conexão respeitando rigorosamente o limite de 300 caracteres do LinkedIn.
        Suporta Espanhol (para vagas da Espanha) e Inglês (para vagas dos EUA e internacionais).
        """
        # Extrai o primeiro nome para uma abordagem mais calorosa e humana
        first_name = recruiter_name.strip().split()[0] if recruiter_name else "there"
        clean_company = company.strip() if company else "your team"
        clean_title = job_title.strip() if job_title else "Cloud Engineer"

        # Abrevia títulos longos para garantir o limite de 300 caracteres
        if len(clean_title) > 35:
            clean_title = clean_title[:32] + "..."

        loc_lower = location.lower() if location else ""
        title_lower = clean_title.lower()

        is_explicit_spain = (
            any(w in loc_lower for w in ["spain", "españa", "madrid", "barcelona", "valencia", "sevilla", "málaga"])
            or any(w in title_lower for w in ["ingeniero", "ciberseguridad", "seguridad", "desarrollador", "administrador de sistemas"])
        )

        is_explicit_brazil = (
            not is_explicit_spain
            and (
                any(w in loc_lower for w in ["brazil", "brasil", "são paulo", "sao paulo", ", sp", " sp ", "campinas", "jundiaí", "jundiai", "rio de janeiro", "curitiba", "belo horizonte"])
                or any(w in title_lower for w in ["engenheiro", "analista", "estágio", "especialista", "segurança da informação"])
            )
        )

        if is_explicit_spain:
            note = (
                f"Hola {first_name}, acabo de postularme a {clean_title} en {clean_company}. "
                f"Con 4+ años en Cloud e Infraestructura (AZ-104, Azure, Linux), "
                f"mi perfil encaja con sus objetivos. ¡Será un placer conectar!"
            )
            if len(note) > 300:
                note = (
                    f"Hola {first_name}, me postulé a {clean_title} en {clean_company}. "
                    f"Cloud/Infra Engineer (AZ-104, Azure, Linux). ¡Un placer conectar!"
                )
        elif is_explicit_brazil:
            note = (
                f"Olá {first_name}, me candidatei à vaga de {clean_title} na {clean_company}. "
                f"Com 4+ anos em Cloud e Infraestrutura (certificação AZ-104, Azure, Linux), "
                f"tenho forte interesse em contribuir com a equipe. Será um prazer conectar!"
            )
            if len(note) > 300:
                note = (
                    f"Olá {first_name}, apliquei para {clean_title} na {clean_company}. "
                    f"Cloud & Infra Engineer (AZ-104, Azure, Linux). Muito prazer em conectar!"
                )
        else:
            note = (
                f"Hi {first_name}, I just applied for the {clean_title} role at {clean_company}. "
                f"With 4+ years in Cloud/Infrastructure (AZ-104 certified, Azure & Linux), "
                f"my background aligns strongly with your team's goals. Would love to connect!"
            )
            if len(note) > 300:
                note = (
                    f"Hi {first_name}, applied for {clean_title} at {clean_company}. "
                    f"Cloud/Infra Engineer (AZ-104, Azure, Linux). Would love to connect!"
                )

        return note[:300]

    def build_executive_pitch(self, recruiter_name: str, job_title: str, company: str, location: str = "") -> str:
        """
        Gera um pitch executivo de alto impacto de 3 parágrafos para abordagem direta ao Tech Lead / Recrutador.
        Adequado para E-mail frio, mensagem direta ou InMail.
        Disponível em Inglês (EUA/Global) ou Espanhol (Espanha).
        """
        first_name = recruiter_name.strip().split()[0] if recruiter_name else "there"
        clean_company = company.strip() if company else "your team"
        clean_title = job_title.strip() if job_title else "Cloud Engineer"

        loc_lower = location.lower() if location else ""
        is_spanish = any(w in loc_lower for w in ["spain", "españa", "madrid", "barcelona", "valencia"]) or any(w in clean_title.lower() for w in ["ingeniero", "sistemas", "redes"])

        if is_spanish:
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

            # 1. Tentar encontrar botão Conectar no card principal
            connect_btn = None
            connect_selectors = [
                "button:has-text('Connect')",
                "button:has-text('Conectar')",
                "button[aria-label*='Connect' i]",
                "button[aria-label*='Conectar' i]",
                ".pvs-profile-actions button:has-text('Connect')",
                ".pvs-profile-actions button:has-text('Conectar')"
            ]
            for sel in connect_selectors:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    connect_btn = loc
                    break

            # 2. Se não encontrou direto, pode estar dentro do menu "More" / "Mais"
            if not connect_btn:
                more_selectors = [
                    ".pvs-profile-actions button:has-text('More')",
                    ".pvs-profile-actions button:has-text('Mais')",
                    "button[aria-label*='More actions' i]",
                    "button[aria-label*='Mais ações' i]"
                ]
                for m_sel in more_selectors:
                    m_loc = self.page.locator(m_sel).first
                    if m_loc.count() > 0 and m_loc.is_visible():
                        m_loc.click()
                        time.sleep(1.0)
                        dropdown_connect = self.page.locator(
                            "div[role='menu'] div:has-text('Connect'), div[role='menu'] div:has-text('Conectar'), div[role='menu'] button:has-text('Connect'), div[role='menu'] button:has-text('Conectar')"
                        ).first
                        if dropdown_connect.count() > 0 and dropdown_connect.is_visible():
                            connect_btn = dropdown_connect
                            break

            if not connect_btn:
                return False, "Botão 'Conectar' não disponível no perfil (pode ser restrito a InMail ou Seguir)."

            connect_btn.click()
            time.sleep(1.5)

            # 3. Verificar modal de convite ("Add a note" / "Adicionar nota")
            # Contas gratuitas do LinkedIn possuem uma cota mensal de notas personalizadas (até 300 caracteres).
            # Se a cota estiver disponível, preenchemos a nota. Se não, enviamos o convite de conexão padrão gratuitamente.
            add_note_btn = self.page.locator(
                "button:has-text('Add a note'), button:has-text('Adicionar nota'), button[aria-label*='Add a note' i], button[aria-label*='Adicionar nota' i]"
            ).first
            note_filled = False
            if add_note_btn.count() > 0 and add_note_btn.is_visible():
                try:
                    add_note_btn.click()
                    time.sleep(1.0)

                    # Campo textarea para a mensagem personalizada
                    textarea = self.page.locator("textarea[name='message'], #custom-message, textarea").first
                    if textarea.count() > 0 and textarea.is_visible():
                        clean_note = note[:300]
                        textarea.fill(clean_note)
                        time.sleep(1.0)
                        note_filled = True
                        logger.info(f"Nota personalizada preenchida com sucesso ({len(clean_note)} caracteres).")
                except Exception as note_e:
                    logger.debug(f"Não foi possível anexar nota (fallback para convite sem nota): {note_e}")

            # 4. Enviar convite (suporta botão 'Send with note', 'Send without a note', 'Send now', 'Enviar')
            send_btn = self.page.locator(
                "button:has-text('Send'), button:has-text('Enviar'), button:has-text('Send without a note'), button:has-text('Enviar sem nota'), button:has-text('Send now'), button[aria-label*='Send' i], button[aria-label*='Enviar' i]"
            ).last
            if send_btn.count() > 0 and send_btn.is_visible():
                send_btn.click()
                time.sleep(2.0)
                msg_status = "com nota personalizada" if note_filled else "padrão (gratuito, sem InMail)"
                logger.info(f"Convite de conexão ({msg_status}) enviado com sucesso para {recruiter_profile_url}!")
                return True, f"Convite de conexão ({msg_status}) enviado com sucesso!"

            return False, "Botão 'Enviar' do convite não encontrado."

        except Exception as e:
            logger.warning(f"Erro ao enviar convite para recrutador: {e}")
            return False, f"Erro ao enviar convite: {str(e)}"


def send_connection_invite_standalone(profile_url: str, note: str, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Abre uma sessão temporária do Playwright com perfil seguro,
    envia o convite de conexão com nota personalizada e encerra o navegador.
    """
    from core.browser import BrowserManager
    from utils.config_manager import load_config

    cfg = config or load_config()
    session_dir = cfg.get("bot", {}).get("session_dir", ".session")
    headless = cfg.get("bot", {}).get("headless", False)

    bm = BrowserManager(session_dir=session_dir, headless=headless)
    try:
        page = bm.start()
        rf = RecruiterFinder(page)
        success, msg = rf.send_connection_invite(profile_url, note)
        return success, msg
    except Exception as e:
        return False, f"Falha ao enviar convite: {str(e)}"
    finally:
        try:
            bm.stop()
        except Exception:
            pass

