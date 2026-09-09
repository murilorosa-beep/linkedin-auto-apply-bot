"""
Módulo de preenchimento automatizado e seguro do modal Easy Apply do LinkedIn.
Suporta inputs de texto, numéricos (detecção de inputmode), textareas, selects nativos,
dropdowns customizados do LinkedIn, grupos de rádio, upload de currículo e checkboxes inteligentes.
"""

import os
import re
import logging
from typing import Dict, Any, Tuple, Optional
from playwright.sync_api import Page, Locator
from core.browser import BrowserManager
from core.ai_solver import QuestionSolver
from core.cover_letter import CoverLetterGenerator
from core.matcher import JobMatcher

logger = logging.getLogger("AutoApplyBot")


class EasyApplyHandler:
    def __init__(
        self,
        browser_mgr: BrowserManager,
        solver: QuestionSolver,
        config: Dict[str, Any],
        profile: Dict[str, Any]
    ):
        self.bm = browser_mgr
        self.page: Page = browser_mgr.page
        self.solver = solver
        self.config = config
        self.profile = profile
        self.dry_run = config.get("bot", {}).get("dry_run", True)
        self.resume_path = os.path.abspath(config.get("bot", {}).get("resume_path", "config/cv/resume.pdf"))
        self.cover_letter_gen = CoverLetterGenerator(profile, config)
        self.matcher = JobMatcher(profile, config)
        self.current_job = {}
        self.current_job_desc = ""

    def apply_to_job(self, job: Dict[str, Any]) -> Tuple[str, str]:
        """
        Navega para a vaga e executa todo o fluxo de preenchimento do Easy Apply.
        Retorna (status, notas): 'APPLIED', 'DRY_RUN', 'SKIPPED', 'FAILED'
        """
        self.current_job = job
        job_url = job.get("url", "")
        self.page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        self.bm.human_delay(2.5, 4.0)

        # Extrair descrição da vaga para enriquecer Cover Letter e Match
        try:
            desc_elem = self.page.locator(".jobs-description__content, #job-details, .jobs-box__htmlContent").first
            self.current_job_desc = desc_elem.inner_text().strip() if desc_elem.count() > 0 else ""
        except Exception:
            self.current_job_desc = ""

        # Validação Inteligente da Descrição da Vaga (Pre-Apply Gatekeeper)
        # Se a descrição contiver requisitos incompatíveis (ex: senioridade 8+ anos, dev puro) ou score < min_match_score, pula
        if self.current_job_desc:
            match_res = self.matcher.calculate_match(
                job.get("title", ""),
                self.current_job_desc,
                location=job.get("location", ""),
                workplace_type=job.get("workplace_type", ""),
                company=job.get("company", "")
            )
            min_cutoff = self.config.get("limits", {}).get("min_match_score", 50)
            if match_res["score"] < min_cutoff or match_res.get("recommendation") == "SKIP":
                skip_msg = match_res.get("summary", f"Score insuficiente na descrição ({match_res['score']}%)")
                logger.info(f"Vaga {job.get('job_id')} pulada após análise da descrição: {skip_msg}")
                return "SKIPPED", f"Triagem da Descrição: {skip_msg}"

        # 1. Localizar o botão de Candidatura Simplificada (Easy Apply)
        easy_apply_btn = self._find_easy_apply_button()
        if not easy_apply_btn:
            return "SKIPPED", "Botao Easy Apply nao encontrado ou candidatura externa"

        # 2. Clicar no botão com fallback resiliente
        try:
            easy_apply_btn.scroll_into_view_if_needed()
            easy_apply_btn.click(timeout=5000)
        except Exception:
            try:
                easy_apply_btn.click(force=True)
            except Exception as e:
                return "FAILED", f"Erro ao clicar no botao Easy Apply: {str(e)}"

        # 3. Esperar explicitamente o modal/dialog abrir e ficar visível
        modal_opened = False
        modal_selectors = [
            "dialog",
            "[role='dialog']",
            ".jobs-easy-apply-modal",
            "div.artdeco-modal",
            "div[data-test-modal]",
            ".artdeco-modal__content"
        ]
        for sel in modal_selectors:
            try:
                self.page.wait_for_selector(sel, state="visible", timeout=3000)
                modal_opened = True
                break
            except Exception:
                continue

        if not modal_opened:
            # Tentar um clique alternativo via Playwright force se o primeiro clique não abriu
            try:
                alt_btn = self.page.locator(
                    "button.jobs-apply-button, button:has-text('Candidatura simplificada'), button:has-text('Easy Apply'), "
                    "button:has-text('Solicitud sencilla'), button:has-text('Solicitar'), button[aria-label*='Candidatura simplificada' i], "
                    "button[aria-label*='Solicitar' i], button[aria-label*='Easy Apply' i]"
                ).first
                if alt_btn.count() > 0 and alt_btn.is_visible():
                    alt_btn.click(force=True)
                    for sel in modal_selectors:
                        try:
                            self.page.wait_for_selector(sel, state="visible", timeout=2000)
                            modal_opened = True
                            break
                        except Exception:
                            continue
            except Exception:
                pass

        if not modal_opened:
            return "FAILED", "Modal de candidatura nao foi exibido"

        modal = self.page.locator("dialog, [role='dialog'], .jobs-easy-apply-modal, div.artdeco-modal, div[data-test-modal]").first
        try:
            modal.wait_for(state="visible", timeout=4000)
        except Exception:
            return "FAILED", "Modal de candidatura nao ficou visivel a tempo"

        # 4. Loop através das etapas do formulário
        max_steps = 12
        for step in range(max_steps):
            self.bm.human_delay(1.5, 2.5)

            # Preencher campos da etapa atual
            self._fill_current_step(modal)

            # Verificar botões de ação disponíveis
            action = self._determine_next_action(modal)

            if action == "NEXT":
                if not self._click_next_and_validate(modal):
                    # Tentar corrigir erros de validação antes de desistir
                    self._recover_validation_errors(modal)
                    if not self._click_next_and_validate(modal):
                        self._discard_application(modal)
                        return "FAILED", "Campo obrigatorio desconhecido travou o formulario"
                continue

            elif action == "REVIEW":
                review_btn = modal.locator(
                    "button:has-text('Avaliar'), button:has-text('Revisar'), button:has-text('Review'), button[aria-label*='Review' i], footer button.artdeco-button--primary"
                ).last
                try:
                    review_btn.click(timeout=4000)
                except Exception:
                    try:
                        review_btn.click(force=True)
                    except Exception:
                        pass
                self.bm.human_delay(1.5, 2.5)

                # Validar se houve erro de validação bloqueando a revisão
                errors = modal.locator(".artdeco-inline-feedback--error, [data-test-form-element-error-messages]")
                if errors.count() > 0 and errors.first.is_visible():
                    logger.warning("Erros de validacao detectados na etapa de Avaliacao/Review. Tentando auto-recuperacao...")
                    self._recover_validation_errors(modal)
                    try:
                        review_btn.click(timeout=3000)
                    except Exception:
                        try:
                            review_btn.click(force=True)
                        except Exception:
                            pass
                    self.bm.human_delay(1.5, 2.5)
                continue

            elif action == "SUBMIT":
                # Etapa final: Enviar candidatura
                if self.dry_run:
                    self.bm.human_delay(3.0, 5.0)
                    self._discard_application(modal)
                    return "DRY_RUN", "Simulacao concluida com sucesso. Formulario validado sem submeter."
                else:
                    submit_btn = modal.locator(
                        "button:has-text('Enviar candidatura'), button:has-text('Submit application'), button[aria-label*='Submit application' i], button[aria-label*='Enviar candidatura' i], footer button.artdeco-button--primary"
                    ).last
                    try:
                        submit_btn.click(timeout=5000)
                    except Exception:
                        try:
                            submit_btn.click(force=True)
                        except Exception:
                            pass
                    self.bm.human_delay(3.0, 5.0)

                    self._close_success_dialog()
                    return "APPLIED", "Candidatura enviada com sucesso no LinkedIn!"

            elif action == "BLOCKED":
                self._discard_application(modal)
                return "FAILED", "Nao foi possivel avancar no formulario."

        self._discard_application(modal)
        return "FAILED", "Excedeu o numero maximo de etapas do formulario."

    def _find_easy_apply_button(self) -> Optional[Locator]:
        """Procura o botão de Easy Apply na página da vaga cobrindo inglês, português, espanhol, francês e alemão."""
        # Aguarda brevemente o container principal do botão carregar se ainda não estiver pronto
        try:
            self.page.wait_for_selector(
                "button.jobs-apply-button, div.jobs-apply-button--top-card, .jobs-s-apply button, button[data-job-id]",
                state="attached",
                timeout=3500
            )
        except Exception:
            pass

        # 1. Seletores específicos de classe do LinkedIn Easy Apply
        specific_selectors = [
            "button.jobs-apply-button",
            "div.jobs-apply-button--top-card button",
            ".jobs-s-apply button",
            "button[data-job-id]"
        ]
        for sel in specific_selectors:
            locs = self.page.locator(sel)
            for i in range(locs.count()):
                btn = locs.nth(i)
                if btn.is_visible():
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    txt = btn.inner_text().lower()
                    # Rejeitar apenas se for explicitamente redirecionamento para site externo
                    if any(ext in aria or ext in txt for ext in [
                        "sitio web de la empresa", "company website", "site da empresa", "external", "externo"
                    ]):
                        continue
                    # Se tiver a classe jobs-apply-button ou qualquer termo de candidatura (PT, EN, ES, FR, DE)
                    btn_class = (btn.get_attribute("class") or "").lower()
                    if "jobs-apply-button" in btn_class or any(t in txt or t in aria for t in [
                        "easy apply", "simplificada", "simplifiée", "sencilla", "einfach", "bewerben",
                        "solicitar", "solicitud", "postularse", "candidatar"
                    ]):
                        return btn

        # 2. Seletores semânticos por texto ou atributo aria abrangendo espanhol, inglês, português
        text_selectors = [
            "button:has-text('Easy Apply')",
            "button:has-text('Candidatura simplificada')",
            "button:has-text('Solicitud sencilla')",
            "button:has-text('Solicitar')",
            "button:has-text('Postularse')",
            "button:has-text('Candidature simplifiée')",
            "button:has-text('Einfach bewerben')",
            "button[aria-label*='Easy Apply' i]",
            "button[aria-label*='Candidatura simplificada' i]",
            "button[aria-label*='Solicitud sencilla' i]",
            "button[aria-label*='Solicitar' i]",
            "button[aria-label*='Postularse' i]"
        ]
        for sel in text_selectors:
            locs = self.page.locator(sel)
            for i in range(locs.count()):
                btn = locs.nth(i)
                if btn.is_visible():
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    txt = btn.inner_text().lower()
                    if any(ext in aria or ext in txt for ext in [
                        "sitio web de la empresa", "company website", "site da empresa", "external", "externo"
                    ]):
                        continue
                    return btn

        return None

    def _fill_current_step(self, modal: Locator):
        """Identifica e preenche todos os tipos de campos da etapa visível de forma modular."""
        self._process_contact_info(modal)
        self._process_resume_upload(modal)
        self._process_text_and_number_inputs(modal)
        self._process_textareas(modal)
        self._process_dropdowns(modal)
        self._process_radio_groups(modal)
        self._process_checkboxes(modal)

    def _process_contact_info(self, modal: Locator):
        """Preenche campos de contato (telefone, e-mail, nome, URL do LinkedIn) com os dados oficiais do candidato."""
        personal = self.profile.get("personal", {})
        links = self.profile.get("links", {})

        # 1. Telefone
        phone_input = modal.locator(
            "input[id*='phoneNumber'], input[type='tel'], input[name*='phone' i], input[id*='phone' i], "
            "input[aria-label*='phone' i], input[aria-label*='telefone' i], input[aria-label*='téléphone' i]"
        ).first
        if phone_input.count() > 0 and phone_input.is_visible():
            current_val = phone_input.input_value()
            if not current_val:
                phone_num = personal.get("phone_national", "11996697230")
                if phone_num:
                    phone_input.fill(phone_num)
                    logger.info(f"Telefone preenchido: {phone_num}")

        # 2. LinkedIn URL (Apenas em campos não-numéricos de contato)
        linkedin_input = modal.locator(
            "input[id*='linkedin' i], input[name*='linkedin' i], input[aria-label*='linkedin' i]"
        ).first
        if linkedin_input.count() > 0 and linkedin_input.is_visible():
            inp_type = (linkedin_input.get_attribute("type") or "").lower()
            inp_mode = (linkedin_input.get_attribute("inputmode") or "").lower()
            q_label = self._extract_field_label(modal, linkedin_input).lower()
            is_num = (
                inp_type == "number"
                or inp_mode == "numeric"
                or any(w in q_label for w in ["year", "ano", "how many", "quantos", "cuántos", "experiência", "experiencia"])
            )
            if not is_num:
                current_val = linkedin_input.input_value()
                if not current_val:
                    url = links.get("linkedin", "https://www.linkedin.com/in/murilo-martins-0b9938186")
                    linkedin_input.fill(url)
                    logger.info(f"LinkedIn URL preenchida: {url}")

    def _get_appropriate_resume_path(self) -> str:
        """Determina dinamicamente se deve usar o currículo em português ou inglês baseado na vaga."""
        job_loc = self.current_job.get("location", "").lower()
        job_title = self.current_job.get("title", "").lower()
        job_desc = self.current_job_desc.lower()

        is_brazil = (
            any(k in job_loc for k in ["brazil", "brasil", "são paulo", "sp", "campinas", "jundiaí", "rio de janeiro", "curitiba", "belo horizonte"])
            or any(k in job_title for k in ["analista", "engenheiro", "estágio", "especialista", "desenvolvedor", "estagiário", "técnico"])
            or any(k in job_desc for k in ["requisitos", "benefícios", "atividades", "experiência", "conhecimento em", "vaga"])
        )

        pt_path = os.path.abspath(self.config.get("bot", {}).get("resume_path_pt", "config/cv/resume_pt.pdf"))
        en_path = os.path.abspath(self.config.get("bot", {}).get("resume_path_en", "config/cv/resume_en.pdf"))
        legacy_path = os.path.abspath(self.config.get("bot", {}).get("resume_path", "config/cv/resume.pdf"))

        if is_brazil and os.path.exists(pt_path):
            logger.info(f"Vaga nacional detectada ({job_loc or job_title}). Selecionado currículo em Português: {os.path.basename(pt_path)}")
            return pt_path

        if os.path.exists(en_path):
            return en_path
        if os.path.exists(legacy_path):
            return legacy_path
        if os.path.exists(pt_path):
            return pt_path
        return legacy_path

    def _process_resume_upload(self, modal: Locator):
        """Garante o upload e seleção do currículo atualizado (dinâmico: PT para vagas no Brasil, EN para internacional)."""
        active_resume = self._get_appropriate_resume_path()
        if not os.path.exists(active_resume):
            logger.warning(f"Arquivo de curriculo nao encontrado em: {active_resume}")
            return

        try:
            page_text = modal.inner_text(timeout=3000).lower()
        except Exception:
            page_text = ""
        is_resume_step = any(w in page_text for w in [
            "resume", "currículo", "curriculo", "cv", "candidature", "lebenslauf"
        ])

        # 1. Se já existe o currículo na conta (o novo que o usuário deixou padrão)
        resume_items = modal.locator(
            "div.jobs-document-upload-redesign-card, "
            "div.jobs-resume-picker__resume-list-item, "
            "li.jobs-resume-picker__resume-list-item, "
            "div[data-test-document-card]"
        )
        if resume_items.count() > 0:
            first_item = resume_items.first
            try:
                radio = first_item.locator("input[type='radio']").first
                if radio.count() > 0:
                    if not radio.is_checked():
                        radio.check(force=True)
                        logger.info("Currículo novo selecionado na lista do LinkedIn.")
                else:
                    first_item.click()
                self.bm.human_delay(0.8, 1.4)
            except Exception as e:
                logger.warning(f"Erro ao selecionar currículo na lista: {e}")
        else:
            # 2. Se não houver currículo na lista da vaga, fazer upload do arquivo local
            file_input = modal.locator("input[type='file']").first
            if file_input.count() > 0 and os.path.exists(active_resume):
                try:
                    file_input.set_input_files(active_resume)
                    logger.info(f"Novo currículo ({os.path.basename(active_resume)}) anexado com sucesso!")
                    self.bm.human_delay(2.5, 4.0)
                except Exception as e:
                    logger.debug(f"Tentativa de upload de novo currículo: {e}")

        # 3. Fallback para qualquer grupo de radio buttons na etapa de currículo
        if is_resume_step:
            radios = modal.locator("input[type='radio']")
            if radios.count() > 0:
                has_checked = False
                for i in range(radios.count()):
                    if radios.nth(i).is_checked() or radios.nth(i).get_attribute("aria-checked") == "true":
                        has_checked = True
                        break
                if not has_checked:
                    try:
                        radios.first.check(force=True)
                        logger.info("Primeiro curriculo da lista marcado.")
                    except Exception:
                        pass

    def _process_text_and_number_inputs(self, modal: Locator):
        """Preenche inputs text e number, identificando LinkedIn URL, cidade, CEP, nomes e campos numéricos."""
        text_inputs = modal.locator("input[type='text']:not([disabled]), input[type='number']:not([disabled]), input:not([type]):not([disabled])")
        for i in range(text_inputs.count()):
            try:
                inp = text_inputs.nth(i)
                if not inp.is_visible() or inp.input_value():
                    continue

                q_text = self._extract_field_label(modal, inp)
                field_type = inp.get_attribute("type") or "text"
                inp_mode = (inp.get_attribute("inputmode") or "").lower()
                inp_id = (inp.get_attribute("id") or "").lower()
                inp_name = (inp.get_attribute("name") or "").lower()
                q_lower = q_text.lower()
                normalized_combo = f"{q_lower} {inp_id} {inp_name}"

                # 1. Identificar se o campo é NUMÉRICO (anos de experiência, salário, quantidade)
                # Prioridade máxima na detecção para JAMAIS preencher um campo numérico com links/URLs!
                is_numeric = (
                    field_type == "number"
                    or inp_mode == "numeric"
                    or "numeric" in inp_id
                    or any(w in normalized_combo for w in [
                        "year", "years", "how many", "anos", "quantos", "rate", "salary", "compensation", "experiência",
                        "años", "cuántos", "experiencia", "années", "combien", "jahre", "wie viele"
                    ])
                )

                if is_numeric:
                    answer = self.solver.answer_question(q_text, "number", [])
                    inp.fill(str(answer))
                    self.bm.human_delay(0.2, 0.5)
                    continue

                # 2. Caso especial: Link ou Perfil do LinkedIn (Apenas se a pergunta pedir especificamente perfil/URL)
                if any(term in q_lower for term in [
                    "perfil do linkedin", "link do linkedin", "url do linkedin",
                    "perfil de linkedin", "profil linkedin", "enlace de linkedin",
                    "linkedin url", "linkedin link", "linkedin profile"
                ]) or q_lower.strip().rstrip(":*").strip() in ["linkedin", "perfil do linkedin"]:
                    real_linkedin = self.profile.get("links", {}).get("linkedin", "https://www.linkedin.com/in/murilo-martins-0b9938186")
                    inp.fill(real_linkedin)
                    logger.info(f"Link do LinkedIn preenchido: {real_linkedin}")
                    self.bm.human_delay(0.2, 0.5)
                    continue

                # 3. Caso especial: Autocompletar de Cidade / Localização (EN, PT, ES, FR, DE)
                if any(term in normalized_combo for term in [
                    "city", "cidade", "location", "localização", "município", "ciudad", "localidad", "ubicación", "ville", "stadt", "wohnort"
                ]) and not any(term in normalized_combo for term in ["postal", "zip", "cep", "plz"]):
                    city_val = self.profile.get("personal", {}).get("city", "Jundiaí")
                    try:
                        inp.click()
                        inp.fill("")
                        inp.type(city_val, delay=80)
                        self.bm.human_delay(0.8, 1.2)
                        suggestion = self.page.locator(
                            "div.basic-typeahead__selectable-list li, "
                            "div[role='listbox'] [role='option'], "
                            "ul.typeahead-results li"
                        ).first
                        if suggestion.count() > 0 and suggestion.is_visible():
                            suggestion.click()
                            self.bm.human_delay(0.4, 0.8)
                            continue
                    except Exception:
                        pass

                # 4. Caso especial: CEP / Código Postal / ZIP Code
                if any(term in normalized_combo for term in ["postal code", "zip code", "zip", "código postal", "cep", "code postal", "plz"]):
                    cep_val = self.profile.get("personal", {}).get("postal_code", "13200-000")
                    inp.fill(cep_val)
                    self.bm.human_delay(0.2, 0.4)
                    continue

                # 5. Caso especial: Primeiro Nome e Sobrenome isolados
                if any(term in normalized_combo for term in ["first name", "given name", "primeiro nome", "primer nombre", "prénom", "vorname"]):
                    inp.fill(self.profile.get("personal", {}).get("first_name", "Murilo"))
                    continue
                if any(term in normalized_combo for term in ["last name", "surname", "family name", "sobrenome", "apellido", "nom de famille", "nachname"]):
                    inp.fill(self.profile.get("personal", {}).get("last_name", "Martins"))
                    continue

                # 6. Demais campos de texto genéricos
                answer = self.solver.answer_question(q_text, "text", [])
                inp.fill(str(answer))
                self.bm.human_delay(0.2, 0.5)
            except Exception:
                continue

    def _process_textareas(self, modal: Locator):
        """Preenche caixas de texto multilinha, gerando Cover Letter dinâmica se solicitado."""
        textareas = modal.locator("textarea:not([disabled])")
        for i in range(textareas.count()):
            try:
                ta = textareas.nth(i)
                if not ta.is_visible() or ta.input_value():
                    continue
                q_text = self._extract_field_label(modal, ta)
                q_lower = q_text.lower()

                # Verificar se o campo pede Carta de Apresentação / Motivação
                if any(term in q_lower for term in [
                    "cover letter", "carta de apresentação", "lettre de motivation",
                    "carta de presentación", "anschreiben", "why should we hire you",
                    "por que devemos te contratar", "why do you want to work",
                    "tell us why", "motivação", "fale sobre você"
                ]):
                    job_title = self.current_job.get("title", "Cloud & Infrastructure Engineer")
                    company = self.current_job.get("company", "")
                    job_loc = (self.current_job.get("location", "")).lower()
                    
                    if any(w in q_lower for w in ["carta de presentación", "presentación", "contratarte", "motivo", "por qué deberíamos", "cuéntanos"]) or "spain" in job_loc or "españa" in job_loc:
                        lang = "es"
                    elif any(w in q_lower for w in ["carta de apresentação", "apresentação", "por que devemos", "você", "motivação"]):
                        lang = "pt"
                    elif any(w in q_lower for w in ["lettre de motivation", "motivation", "pourquoi"]):
                        lang = "fr"
                    else:
                        lang = "en"

                    letter = self.cover_letter_gen.generate_cover_letter(
                        job_title=job_title,
                        company=company,
                        job_description=self.current_job_desc,
                        language=lang
                    )
                    ta.fill(letter)
                    logger.info(f"Carta de apresentacao personalizada gerada para {company} ({job_title}).")
                    self.bm.human_delay(0.5, 1.0)
                    continue

                answer = self.solver.answer_question(q_text, "textarea", [])
                ta.fill(str(answer))
                self.bm.human_delay(0.3, 0.7)
            except Exception:
                continue

    def _process_dropdowns(self, modal: Locator):
        """Processa selects nativos e dropdowns customizados do LinkedIn."""
        # 1. Selects nativos
        selects = modal.locator("select:not([disabled])")
        for i in range(selects.count()):
            try:
                sel = selects.nth(i)
                if not sel.is_visible():
                    continue
                q_text = self._extract_field_label(modal, sel)
                options = sel.locator("option").all_inner_texts()
                clean_options = [opt.strip() for opt in options if opt.strip() and "select an option" not in opt.lower()]
                if not clean_options:
                    continue

                chosen = self.solver.answer_question(q_text, "select", clean_options)
                sel.select_option(label=chosen)
                self.bm.human_delay(0.2, 0.5)
            except Exception:
                continue

        # 2. Dropdowns customizados (estilo fb-dropdown ou artdeco)
        custom_dropdowns = modal.locator(".fb-dropdown, div[data-test-form-builder-select], div.artdeco-dropdown")
        for i in range(custom_dropdowns.count()):
            try:
                dd = custom_dropdowns.nth(i)
                if not dd.is_visible():
                    continue

                trigger_btn = dd.locator("button, [role='combobox']").first
                if trigger_btn.count() == 0:
                    continue

                btn_text = trigger_btn.inner_text().strip().lower()
                if btn_text and "select an option" not in btn_text and "select" != btn_text:
                    continue  # Já tem seleção

                q_text = self._extract_field_label(modal, dd)

                # Abrir dropdown
                trigger_btn.click()
                self.bm.human_delay(0.4, 0.7)

                options_loc = self.page.locator("div[role='listbox'] [role='option'], ul[role='listbox'] li, .fb-dropdown__select-dropdown li")
                opts_texts = [o.strip() for o in options_loc.all_inner_texts() if o.strip()]
                clean_opts = [o for o in opts_texts if "select an option" not in o.lower()]

                if clean_opts:
                    chosen = self.solver.answer_question(q_text, "select", clean_opts)
                    for opt_idx, opt_str in enumerate(clean_opts):
                        if opt_str.lower() == chosen.lower() or chosen.lower() in opt_str.lower():
                            options_loc.nth(opt_idx).click()
                            self.bm.human_delay(0.2, 0.5)
                            break
            except Exception:
                continue

    def _process_radio_groups(self, modal: Locator):
        """Processa grupos de botões radio de forma universal (pelo atributo name ou containers)."""
        radios = modal.locator("input[type='radio']")
        if radios.count() == 0:
            return

        # Coletar todos os nomes únicos de grupos de radio
        radio_names = []
        for i in range(radios.count()):
            name = radios.nth(i).get_attribute("name")
            if name and name not in radio_names:
                radio_names.append(name)

        # Se não houver name explícito, agrupar como uma lista geral
        if not radio_names:
            radio_names = [None]

        for name in radio_names:
            group_radios = modal.locator(f"input[type='radio'][name='{name}']") if name else radios
            # Checar se algum já está marcado
            has_checked = False
            for i in range(group_radios.count()):
                if group_radios.nth(i).is_checked() or group_radios.nth(i).get_attribute("aria-checked") == "true":
                    has_checked = True
                    break
            if has_checked:
                continue

            # Extrair pergunta do grupo
            first_r = group_radios.first
            q_text = ""
            try:
                ancestor = first_r.locator("xpath=ancestor::div[count(.//input[@type='radio']) > 1]").last
                if ancestor.count() > 0:
                    lines = [l.strip() for l in ancestor.inner_text().split("\n") if l.strip()]
                    clean_lines = [l for l in lines if l.lower() not in ["yes", "no", "sim", "não", "nao"] and len(l) > 4]
                    if clean_lines:
                        q_text = clean_lines[0]
            except Exception:
                pass
            if not q_text:
                q_text = self._extract_field_label(modal, first_r)

            options = []
            for i in range(group_radios.count()):
                r = group_radios.nth(i)
                r_id = r.get_attribute("id")
                opt_txt = ""
                if r_id:
                    lbl = modal.locator(f"label[for='{r_id}']").first
                    if lbl.count() > 0:
                        opt_txt = lbl.inner_text().strip()
                if not opt_txt:
                    try:
                        parent_lbl = r.locator("xpath=ancestor::label").first
                        if parent_lbl.count() > 0:
                            opt_txt = parent_lbl.inner_text().strip()
                    except Exception:
                        pass
                options.append(opt_txt if opt_txt else f"Option {i}")

            chosen = self.solver.answer_question(q_text, "radio", options)

            clicked = False
            for i, opt in enumerate(options):
                if chosen.lower() in opt.lower() or opt.lower() in chosen.lower():
                    try:
                        group_radios.nth(i).evaluate("el => { el.scrollIntoView({block: 'center', behavior: 'instant'}); el.click(); }")
                    except Exception:
                        try:
                            group_radios.nth(i).check(force=True)
                        except Exception:
                            pass
                    clicked = True
                    self.bm.human_delay(0.2, 0.4)
                    break

            if not clicked and group_radios.count() > 0:
                try:
                    group_radios.first.evaluate("el => { el.scrollIntoView({block: 'center', behavior: 'instant'}); el.click(); }")
                except Exception:
                    pass
                self.bm.human_delay(0.2, 0.4)

    def _process_checkboxes(self, modal: Locator):
        """Processa checkboxes visíveis na página."""
        checkboxes = modal.locator("input[type='checkbox']")
        skills_dict = self.profile.get("skills_experience_years", {})

        for i in range(checkboxes.count()):
            try:
                cb = checkboxes.nth(i)
                if cb.is_checked():
                    continue

                label_text = self._extract_field_label(modal, cb).lower()

                confirmation_keywords = [
                    "confirm", "agree", "acknowledge", "certify", "understand",
                    "consent", "terms", "privacy", "concordo", "aceito", "ciente", "18 years"
                ]
                should_check = any(word in label_text for word in confirmation_keywords)

                if not should_check:
                    for skill_name, years in skills_dict.items():
                        if skill_name == "default":
                            continue
                        pattern = r"\b" + re.escape(skill_name.lower()) + r"\b"
                        if re.search(pattern, label_text) and int(years) > 0:
                            should_check = True
                            break

                if not should_check and any(term in label_text for term in ["remote", "b2b", "contractor", "authorized"]):
                    should_check = True

                if should_check:
                    cb.scroll_into_view_if_needed()
                    cb_id = cb.get_attribute("id")
                    if cb_id and modal.locator(f"label[for='{cb_id}']").count() > 0:
                        modal.locator(f"label[for='{cb_id}']").first.click()
                    else:
                        cb.check(force=True)
                    self.bm.human_delay(0.2, 0.4)

            except Exception:
                continue

    def _extract_field_label(self, modal: Locator, element: Locator) -> str:
        """Encontra o texto da pergunta ou rótulo associado a um campo de forma robusta, ignorando contadores e títulos de seção."""
        # 1. Aria-label no próprio input (no novo design do LinkedIn, contém a pergunta completa)
        aria_label = element.get_attribute("aria-label")
        if aria_label and not re.match(r"^\d+\s*(/|de)\s*\d+", aria_label) and len(aria_label) > 3:
            return aria_label.strip()

        # 2. Se tem id associado a um <label for="...">
        elem_id = element.get_attribute("id")
        if elem_id:
            label = modal.locator(f"label[for='{elem_id}']").first
            if label.count() > 0:
                txt = label.inner_text().strip()
                if txt and not re.match(r"^\d+\s*(/|de)\s*\d+", txt) and len(txt) > 2:
                    if txt.lower() not in ["additional questions", "perguntas adicionais"]:
                        return txt

        # 3. Procurar no container ancestral imediato (o mais próximo que tenha parágrafo ou label)
        for ancestor_sel in [
            "xpath=ancestor::div[contains(@class, 'fb-dash-form-element')]",
            "xpath=ancestor::div[contains(@class, 'jobs-easy-apply-form-section__grouping')]",
            "xpath=ancestor::div[.//p or .//label][1]"
        ]:
            try:
                ancestor = element.locator(ancestor_sel).first
                if ancestor.count() > 0:
                    lbls = ancestor.locator("p, label, span.t-14")
                    for k in range(lbls.count()):
                        cand = lbls.nth(k).inner_text().strip()
                        if cand and not re.match(r"^\d+\s*(/|de)\s*\d+", cand) and len(cand) > 3:
                            if cand.lower() not in ["additional questions", "perguntas adicionais"]:
                                return cand
            except Exception:
                continue

        # 4. Placeholder
        placeholder = element.get_attribute("placeholder")
        if placeholder:
            return placeholder.strip()

        return ""

    def _determine_next_action(self, modal: Locator) -> str:
        """Determina o botão de ação principal da etapa atual observando o footer do modal (EN, PT, ES, FR, DE)."""
        # 1. Checar botão primário no rodapé do modal (padrão universal do LinkedIn)
        footer_primary = modal.locator(
            "footer button.artdeco-button--primary, "
            ".jobs-easy-apply-modal__footer button.artdeco-button--primary, "
            "div[class*='footer'] button.artdeco-button--primary"
        ).first

        if footer_primary.count() > 0 and footer_primary.is_visible():
            btn_txt = footer_primary.inner_text().lower().strip()
            aria_txt = (footer_primary.get_attribute("aria-label") or "").lower().strip()
            combo = f"{btn_txt} {aria_txt}"

            if any(w in combo for w in [
                "submit", "enviar candidatura", "enviar solicitud", "envoyer la candidature",
                "envoyer", "postuler", "absenden", "invia", "postula"
            ]):
                return "SUBMIT"
            if any(w in combo for w in [
                "review", "revisar", "avaliar", "evaluar", "vérifier", "examiner",
                "überprüfen", "prüfen", "rivedere"
            ]):
                return "REVIEW"
            if any(w in combo for w in [
                "next", "avançar", "avancar", "continuar", "continue", "siguiente",
                "suivant", "weiter", "avanti", "seguinte", "próxima"
            ]):
                return "NEXT"

        # 2. Fallback com seletores específicos por texto e aria-label
        submit_btn = modal.locator(
            "button:has-text('Enviar candidatura'), button:has-text('Submit application'), "
            "button:has-text('Enviar solicitud'), button:has-text('Envoyer la candidature'), "
            "button:has-text('Bewerbung absenden'), button[aria-label*='Submit application' i], "
            "button[aria-label*='Enviar candidatura' i]"
        ).first
        if submit_btn.count() > 0 and submit_btn.is_visible():
            return "SUBMIT"

        review_btn = modal.locator(
            "button:has-text('Avaliar'), button:has-text('Revisar'), button:has-text('Review'), "
            "button:has-text('Evaluar'), button:has-text('Vérifier'), button:has-text('Überprüfen'), "
            "button[aria-label*='Review' i], button[aria-label*='Revisar' i], button[aria-label*='Avaliar' i]"
        ).first
        if review_btn.count() > 0 and review_btn.is_visible():
            return "REVIEW"

        next_btn = modal.locator(
            "button:has-text('Avançar'), button:has-text('Next'), button:has-text('Continuar'), "
            "button:has-text('Siguiente'), button:has-text('Suivant'), button:has-text('Weiter'), "
            "button[aria-label*='Continue to next step' i], button[aria-label*='Avançar' i], "
            "button[aria-label*='Continuar' i], button[aria-label*='Siguiente' i]"
        ).first
        if next_btn.count() > 0 and next_btn.is_visible():
            return "NEXT"

        return "BLOCKED"

    def _click_next_and_validate(self, modal: Locator) -> bool:
        """Clica no botão de avançar e valida se não ficou bloqueado por erro."""
        next_btn = modal.locator(
            "button[aria-label*='Continue to next step' i], "
            "button[aria-label*='Avançar' i], "
            "button[aria-label*='Continuar' i], "
            "button[aria-label*='Siguiente' i], "
            "button[aria-label*='Suivant' i], "
            "button[aria-label*='Weiter' i], "
            "button:has-text('Next'), "
            "button:has-text('Avançar'), "
            "button:has-text('Continuar'), "
            "button:has-text('Siguiente'), "
            "button:has-text('Suivant'), "
            "button:has-text('Weiter'), "
            "footer button.artdeco-button--primary"
        ).first
        if next_btn.count() == 0 or not next_btn.is_visible():
            return False

        try:
            next_btn.click(timeout=4000)
        except Exception:
            try:
                next_btn.click(force=True)
            except Exception:
                return False

        self.bm.human_delay(1.5, 2.5)

        errors = modal.locator(".artdeco-inline-feedback--error, [data-test-form-element-error-messages]")
        if errors.count() > 0 and errors.first.is_visible():
            return False

        return True

    def _recover_validation_errors(self, modal: Locator):
        """Tenta corrigir automaticamente campos obrigatórios que ficaram vazios ou com erro."""
        error_containers = modal.locator(
            ".fb-dash-form-element:has(.artdeco-inline-feedback--error), "
            ".jobs-easy-apply-form-section__grouping:has(.artdeco-inline-feedback--error), "
            "div:has(.artdeco-inline-feedback--error)"
        )
        for i in range(min(error_containers.count(), 10)):
            try:
                container = error_containers.nth(i)
                # 1. Campo de texto ou numérico com erro ou valor inválido
                err_input = container.locator("input[type='text'], input[type='number'], input:not([type])").first
                if err_input.count() > 0 and err_input.is_visible():
                    q_text = self._extract_field_label(modal, err_input).lower()
                    inp_type = (err_input.get_attribute("type") or "").lower()
                    inp_mode = (err_input.get_attribute("inputmode") or "").lower()
                    is_numeric = (
                        inp_type == "number"
                        or inp_mode == "numeric"
                        or any(w in q_text for w in ["year", "ano", "experiência", "quantos", "how many", "años", "années", "jahre", "experience"])
                    )

                    try:
                        err_input.click()
                        err_input.fill("")
                    except Exception:
                        pass

                    if is_numeric:
                        if any(w in q_text for w in ["site reliability", "sre", "cloud", "infra", "azure", "linux"]):
                            err_input.fill("4")
                        else:
                            err_input.fill("3")
                    elif any(w in q_text for w in ["perfil do linkedin", "link do linkedin", "url do linkedin", "linkedin profile", "linkedin url"]):
                        err_input.fill(self.profile.get("links", {}).get("linkedin", "https://www.linkedin.com/in/murilo-martins-0b9938186"))
                    elif any(w in q_text for w in ["city", "cidade", "location", "local", "ciudad", "ville"]):
                        err_input.fill("Jundiaí")
                    elif any(w in q_text for w in ["postal", "zip", "cep", "plz"]):
                        err_input.fill("13200-000")
                    elif any(w in q_text for w in ["salary", "pretensão", "rate", "remuneração", "salario"]):
                        err_input.fill("75000")
                    elif any(w in q_text for w in ["phone", "telefone", "teléfono", "portable"]):
                        err_input.fill(self.profile.get("personal", {}).get("phone_national", "11996697230"))
                    else:
                        err_input.fill("3")
                    self.bm.human_delay(0.2, 0.4)

                # 2. Radio sem seleção
                unselected_radios = container.locator("input[type='radio']")
                if unselected_radios.count() > 0:
                    lbls = container.locator("label")
                    found = False
                    for l_idx in range(lbls.count()):
                        l_txt = lbls.nth(l_idx).inner_text().strip().lower()
                        if l_txt in ["yes", "sim", "sí", "si", "oui", "ja", "agree", "concordo"]:
                            lbls.nth(l_idx).click()
                            found = True
                            break
                    if not found and lbls.count() > 0:
                        lbls.first.click()
                    self.bm.human_delay(0.2, 0.4)

                # 3. Select ou dropdown
                unselected_select = container.locator("select").first
                if unselected_select.count() > 0 and unselected_select.is_visible():
                    opts = unselected_select.locator("option").all_inner_texts()
                    valid_opts = [o.strip() for o in opts if o.strip() and "select" not in o.lower()]
                    if valid_opts:
                        unselected_select.select_option(label=valid_opts[0])
                        self.bm.human_delay(0.2, 0.4)

                # 4. Checkbox obrigatório
                unselected_cb = container.locator("input[type='checkbox']:not(:checked)").first
                if unselected_cb.count() > 0:
                    unselected_cb.check(force=True)
                    self.bm.human_delay(0.2, 0.4)
            except Exception:
                continue

    def _discard_application(self, modal: Locator):
        """Fecha o modal descartando o rascunho de forma limpa."""
        try:
            dismiss_btn = modal.locator(
                "button[aria-label*='Fechar' i], button[aria-label*='Dismiss' i], "
                "button[aria-label*='Cerrar' i], button[aria-label*='Fermer' i], "
                "button[aria-label*='Schließen' i], button.artdeco-modal__dismiss"
            ).first
            if dismiss_btn.count() > 0:
                dismiss_btn.click()
                self.bm.human_delay(1.0, 1.5)

                discard_btn = self.page.locator(
                    "button[data-control-name='discard_application_confirm_btn'], "
                    "button:has-text('Discard'), button:has-text('Descartar'), "
                    "button:has-text('Ignorer'), button:has-text('Verwerfen')"
                ).first
                if discard_btn.count() > 0 and discard_btn.is_visible():
                    discard_btn.click()
                    self.bm.human_delay(1.0, 1.5)
        except Exception:
            pass

    def _close_success_dialog(self):
        """Fecha o modal de parabéns/sucesso após a submissão."""
        try:
            done_btn = self.page.locator(
                "button[aria-label*='Dismiss' i], button:has-text('Done'), "
                "button:has-text('Concluído'), button:has-text('Listo'), "
                "button:has-text('Terminé'), button:has-text('Fertig')"
            ).first
            if done_btn.count() > 0 and done_btn.is_visible():
                done_btn.click()
                self.bm.human_delay(1.0, 1.5)
        except Exception:
            pass
