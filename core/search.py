"""
Módulo de busca e extração de vagas no LinkedIn com filtros internacionais e retries robustos.
"""

import time
import random
import urllib.parse
import re
import logging
from typing import List, Dict, Any, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from core.browser import BrowserManager

logger = logging.getLogger("AutoApplyBot")


class JobSearchEngine:
    def __init__(self, browser_mgr: BrowserManager, config: Dict[str, Any]):
        self.bm = browser_mgr
        self.page: Page = browser_mgr.page
        self.config = config.get("search", {})

    def build_search_url(self, keyword: str, location: str, start_index: int = 0) -> str:
        """Constrói a URL de busca do LinkedIn com os filtros internacionais."""
        base_url = "https://www.linkedin.com/jobs/search/?"
        params = {
            "keywords": keyword,
            "location": location,
            "start": str(start_index),
            "sortBy": "DD"  # Mais recentes primeiro
        }

        # Filtro de Modalidades de Trabalho (LinkedIn f_WT: 1=Presencial, 2=Remoto, 3=Híbrido)
        workplace_types = self.config.get("workplace_types", [])
        if workplace_types and "all" not in workplace_types:
            wt_mapping = {
                "on_site": "1", "presencial": "1", "1": "1",
                "remote": "2", "remoto": "2", "home_office": "2", "2": "2",
                "hybrid": "3", "hibrido": "3", "híbrido": "3", "3": "3"
            }
            codes = []
            for wt in workplace_types:
                code = wt_mapping.get(str(wt).lower())
                if code and code not in codes:
                    codes.append(code)
            
            # Se não selecionou todas as 3 modalidades, aplica o filtro específico
            if codes and len(codes) < 3:
                params["f_WT"] = ",".join(sorted(codes))
        elif self.config.get("remote_only", False):
            # Fallback para configuração legada
            params["f_WT"] = "2"

        # Filtro Candidatura Simplificada (Easy Apply)
        if self.config.get("easy_apply_only", True):
            params["f_AL"] = "true"

        # Filtro Data de Publicação
        date_posted = self.config.get("date_posted", "past_week")
        if date_posted == "past_24h":
            params["f_TPR"] = "r86400"
        elif date_posted == "past_week":
            params["f_TPR"] = "r604800"
        elif date_posted == "past_month":
            params["f_TPR"] = "r2592000"

        # Filtro Nível de Experiência
        exp_levels = self.config.get("experience_levels", [])
        if exp_levels:
            params["f_E"] = ",".join(str(lvl) for lvl in exp_levels)

        return base_url + urllib.parse.urlencode(params)

    def load_search_page(self, keyword: str, location: str, page_num: int = 1, max_retries: int = 3) -> bool:
        """
        Navega para a página de busca com retry automático (até 3 tentativas) em caso de Timeout.
        """
        start_index = (page_num - 1) * 25
        url = self.build_search_url(keyword, location, start_index)
        
        # Delay aleatório entre paginações (2 a 5 segundos)
        if page_num > 1:
            page_delay = random.uniform(2.0, 5.0)
            logger.info(f"Pausa entre paginas de busca: {page_delay:.1f}s")
            time.sleep(page_delay)

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Carregando pagina {page_num} de busca (Tentativa {attempt}/{max_retries}): {url}")
                self.page.goto(url, wait_until="domcontentloaded", timeout=35000)
                self.bm.human_delay(3.0, 5.0)

                current_url = self.page.url.lower()
                # Verificar se foi deslogado
                if "/login" in current_url or "/checkpoint" in current_url:
                    logger.warning("Redirecionado para tela de login/checkpoint durante a busca.")
                    return False

                # Verificar se não há resultados para o termo
                no_results_loc = self.page.locator(
                    "div:has-text('No matching jobs found'), h1:has-text('No matching jobs found'), h2:has-text('No matching jobs found')"
                )
                if no_results_loc.count() > 0 and no_results_loc.first.is_visible():
                    logger.info(f"Nenhuma vaga encontrada para '{keyword}' em '{location}'.")
                    return True

                return True

            except PlaywrightTimeoutError as te:
                logger.warning(f"Timeout ao carregar pagina de busca na tentativa {attempt}/{max_retries}: {str(te)}")
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                else:
                    logger.error(f"Falha definitiva ao carregar pagina de busca apos {max_retries} tentativas.")
                    return False
            except Exception as e:
                logger.warning(f"Erro ao navegar na tentativa {attempt}/{max_retries}: {str(e)}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                else:
                    logger.error(f"Erro fatal na navegacao de busca: {str(e)}")
                    return False

        return False

    def scroll_job_list(self):
        """Rola a lista lateral de vagas para forçar o LinkedIn a carregar todos os cards da página."""
        try:
            container_selector = ".jobs-search-results-list"
            if self.page.locator(container_selector).count() > 0:
                for _ in range(4):
                    self.page.eval_on_selector(
                        container_selector,
                        "el => el.scrollTop += el.offsetHeight"
                    )
                    self.bm.human_delay(0.8, 1.4)
            else:
                self.bm.scroll_page(distance=400, steps=3)
        except Exception:
            pass

    def extract_job_cards(self) -> List[Dict[str, Any]]:
        """Extrai os dados essenciais de todas as vagas visíveis na página de resultados."""
        self.scroll_job_list()
        jobs: List[Dict[str, Any]] = []

        card_selectors = [
            "li.jobs-search-results__list-item",
            "div.job-card-container",
            "li[data-occludable-job-id]"
        ]

        card_locator = None
        for sel in card_selectors:
            if self.page.locator(sel).count() > 0:
                card_locator = self.page.locator(sel)
                break

        if not card_locator:
            return jobs

        count = card_locator.count()
        for idx in range(count):
            try:
                card = card_locator.nth(idx)
                
                # Tentar extrair o Job ID
                job_id = (
                    card.get_attribute("data-occludable-job-id")
                    or card.get_attribute("data-job-id")
                    or ""
                )

                # Link e título da vaga
                title_elem = card.locator("a.job-card-list__title, a.job-card-container__link").first
                title = ""
                href = ""
                if title_elem.count() > 0:
                    title = title_elem.inner_text().strip()
                    href = title_elem.get_attribute("href") or ""
                    if not job_id and href:
                        match = re.search(r"/jobs/view/(\d+)", href)
                        if match:
                            job_id = match.group(1)

                if not job_id:
                    continue

                # Empresa
                company = ""
                company_elem = card.locator(
                    ".artdeco-entity-lockup__subtitle, .job-card-container__primary-description"
                ).first
                if company_elem.count() > 0:
                    company = company_elem.inner_text().strip()

                # Localização
                location = ""
                loc_elem = card.locator(
                    ".artdeco-entity-lockup__caption, .job-card-container__metadata-item"
                ).first
                if loc_elem.count() > 0:
                    location = loc_elem.inner_text().strip()

                # Identificar Modalidade de Trabalho no Card
                card_text = card.inner_text().lower()
                loc_lower = location.lower()
                workplace_type = "Presencial"
                if any(w in card_text or w in loc_lower for w in ["remote", "remoto", "teletrabalho", "home office", "a distância"]):
                    workplace_type = "Remoto"
                elif any(w in card_text or w in loc_lower for w in ["hybrid", "híbrido", "hibrido"]):
                    workplace_type = "Híbrido"

                # Identificar selo de Early Applicant e contagem de candidatos
                is_early_applicant = any(w in card_text for w in [
                    "be an early applicant", "seja um dos primeiros", "early applicant",
                    "under 10 applicants", "under 25 applicants", "menos de 10", "menos de 25"
                ])
                applicants_count = -1
                match_app = re.search(r"(\d+)\s+(?:applicants|candidaturas|solicitudes|candidatos)", card_text)
                if match_app:
                    try:
                        applicants_count = int(match_app.group(1))
                    except Exception:
                        pass
                if is_early_applicant and applicants_count == -1:
                    applicants_count = 25

                # Verificar se tem indicador de Easy Apply (EN, PT, ES, FR)
                is_easy_apply = any(t in card_text for t in [
                    "easy apply", "candidatura simplificada", "solicitud sencilla",
                    "solicitud fácil", "candidature simplifiée"
                ]) or self.config.get("easy_apply_only", True)

                full_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

                jobs.append({
                    "job_id": str(job_id),
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": full_url,
                    "is_easy_apply": is_easy_apply,
                    "workplace_type": workplace_type,
                    "is_early_applicant": is_early_applicant,
                    "applicants_count": applicants_count
                })

            except Exception:
                continue

        return jobs
