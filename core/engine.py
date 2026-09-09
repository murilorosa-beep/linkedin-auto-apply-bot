"""
Motor principal de orquestração do robô de candidaturas internacionais (ApplicationEngine).
Gerencia a busca, retries com tenacity, preenchimento, limites diários e logs em data/bot.log.
"""

import sys
import os
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import random
import yaml
import logging
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from rich.console import Console
from rich.table import Table

from core.browser import BrowserManager
from core.tracker import ApplicationTracker
from core.ai_solver import QuestionSolver
from core.search import JobSearchEngine
from core.form_handler import EasyApplyHandler
from core.matcher import JobMatcher
from core.recruiter_finder import RecruiterFinder
from utils.telegram_notifier import TelegramNotifier

console = Console()

# Configuração de Logging para arquivo data/bot.log
LOG_DIR = Path("data")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"

logger = logging.getLogger("AutoApplyBot")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


class ApplicationEngine:
    def __init__(self, config_path: str = "config/config.yaml", profile_path: str = "config/profile.yaml"):
        self.config_path = config_path
        self.profile_path = profile_path
        self.config = self._load_yaml(config_path)
        self.profile = self._load_yaml(profile_path)
        self.tracker = ApplicationTracker()
        self.solver = QuestionSolver(profile_path, config_path)
        logger.info("ApplicationEngine inicializado.")

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Arquivo de configuracao nao encontrado: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def apply_with_retry(self, form_handler: EasyApplyHandler, job: Dict[str, Any]) -> tuple[str, str]:
        """
        Aplica para uma vaga com até 3 tentativas e espera exponencial usando tenacity.
        Em caso de erro de rede ou timeout, tenta novamente.
        """
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=8),
            reraise=True
        )
        def _attempt():
            return form_handler.apply_to_job(job)

        try:
            return _attempt()
        except Exception as e:
            logger.error(f"Falha apos 3 tentativas na vaga {job.get('job_id')}: {str(e)}")
            return "FAILED", f"Erro apos retries: {str(e)}"

    def run(self, progress_callback=None, stop_event=None):
        """Executa o ciclo completo de busca e candidatura com suporte a cancelamento por stop_event."""
        # Conectar ao logger do Streamlit para streaming ao vivo na UI
        try:
            from utils.logger import setup_streamlit_logger
            setup_streamlit_logger()
        except Exception:
            pass

        limits = self.config.get("limits", {})
        bot_cfg = self.config.get("bot", {})
        search_cfg = self.config.get("search", {})

        max_daily = limits.get("max_applications_per_day", 15)
        applied_today = self.tracker.get_applications_today_count()

        dry_run = bot_cfg.get("dry_run", True)
        mode_str = "[bold yellow]SIMULACAO (Dry Run)[/bold yellow]" if dry_run else "[bold red]MODO REAL (Candidaturas Enviadas)[/bold red]"

        console.print(f"\n[cyan]Modo de Operacao Atual:[/cyan] {mode_str}")
        console.print(f"[cyan]Candidaturas hoje:[/cyan] [bold]{applied_today}/{max_daily}[/bold]")
        logger.info(f"Iniciando ciclo. Modo Dry Run: {dry_run}. Aplicacoes hoje: {applied_today}/{max_daily}")

        if applied_today >= max_daily:
            console.print(f"[bold red]Limite diario de {max_daily} candidaturas ja foi atingido hoje![/bold red]")
            console.print("[dim]Isso protege sua conta contra bloqueios. Tente novamente amanha.[/dim]\n")
            logger.warning(f"Limite diario de {max_daily} atingido. Encerrando ciclo.")
            return

        keywords = search_cfg.get("keywords", ["Software Engineer"])
        locations = search_cfg.get("locations", ["Worldwide"])
        max_pages = limits.get("max_pages_per_search", 3)

        # Suporte a diferentes nomes de parâmetros de pausa
        min_delay = limits.get("pause_between_jobs_min", limits.get("min_delay_seconds", 8))
        max_delay = limits.get("pause_between_jobs_max", limits.get("max_delay_seconds", 20))

        session_dir = bot_cfg.get("session_dir", ".session")
        headless = bot_cfg.get("headless", False)

        console.print("\n[yellow]Iniciando navegador com perfil seguro...[/yellow]")
        bm = BrowserManager(session_dir=session_dir, headless=headless)

        try:
            page = bm.start()
            search_engine = JobSearchEngine(bm, self.config)
            form_handler = EasyApplyHandler(bm, self.solver, self.config, self.profile)
            matcher = JobMatcher(self.profile, self.config)
            recruiter_finder = RecruiterFinder(page, self.profile)
            telegram = TelegramNotifier(self.config_path)

            # Validação de sessão ativa
            console.print("[cyan]Verificando sessao ativa do LinkedIn...[/cyan]")
            is_logged, msg = bm.is_logged_in()
            if not is_logged:
                console.print(f"[bold red]Erro de autenticacao: {msg}[/bold red]")
                logger.error(f"Sessao invalida: {msg}")
                return

            console.print(f"[bold green][OK] {msg}[/bold green]\n")
            logger.info("Sessao confirmada e ativa.")

            total_jobs_processed_cycle = 0

            for keyword in keywords:
                if stop_event and stop_event.is_set():
                    logger.info("Interrupcao solicitada pela interface.")
                    break

                for location in locations:
                    if (stop_event and stop_event.is_set()) or applied_today >= max_daily:
                        break

                    console.print(f"[bold magenta]>> Buscando vagas:[/bold magenta] '{keyword}' em '{location}'")
                    logger.info(f"Iniciando busca para '{keyword}' em '{location}'.")

                    for page_num in range(1, max_pages + 1):
                        if (stop_event and stop_event.is_set()) or applied_today >= max_daily:
                            break

                        console.print(f"  [dim]Carregando pagina {page_num}...[/dim]")
                        loaded = search_engine.load_search_page(keyword, location, page_num)
                        if not loaded:
                            console.print("  [red]Nao foi possivel carregar a pagina de busca. Pulando para proximo termo.[/red]")
                            logger.warning(f"Falha ao carregar pagina {page_num} de '{keyword}'.")
                            break

                        jobs = search_engine.extract_job_cards()
                        console.print(f"  [dim]Encontradas {len(jobs)} vagas na pagina.[/dim]")
                        logger.info(f"Pagina {page_num}: {len(jobs)} vagas encontradas.")

                        if not jobs:
                            logger.info(f"Nenhuma vaga extraida na pagina {page_num}.")
                            continue

                        for job in jobs:
                            if (stop_event and stop_event.is_set()) or applied_today >= max_daily:
                                if stop_event and stop_event.is_set():
                                    logger.info("Execucao interrompida a pedido do usuario.")
                                else:
                                    console.print(f"\n[bold yellow]Limite diario de {max_daily} candidaturas atingido![/bold yellow]")
                                    logger.info("Limite diario atingido durante o processamento das vagas.")
                                break

                            job_id = job["job_id"]
                            title = job["title"]
                            company = job["company"]

                            if self.tracker.is_already_processed(job_id):
                                continue

                            if not job["is_easy_apply"]:
                                self.tracker.record_job(
                                    job_id, title, company, job["location"], job["url"],
                                    "SKIPPED", "Nao e Easy Apply", match_score=0
                                )
                                continue

                            # 0. Filtro Early Applicant (Vagas com menos de 100 candidatos / recentes)
                            filters_cfg = self.config.get("filters", {})
                            early_only = filters_cfg.get("early_applicant_only", False)
                            max_threshold = filters_cfg.get("max_applicants_threshold", 100)
                            app_count = job.get("applicants_count", -1)
                            is_early = job.get("is_early_applicant", False)

                            if early_only and not is_early and app_count > max_threshold:
                                console.print(f"  [dim][PULADA] Filtro Early Applicant ({app_count} candidatos > {max_threshold}): {title}[/dim]")
                                self.tracker.record_job(
                                    job_id, title, company, job.get("location", ""), job["url"],
                                    "SKIPPED", f"Muitos concorrentes ({app_count} candidatos)", match_score=0
                                )
                                continue

                            # 1. Triagem Semântica Prévia (Match Score, Blacklist de Empresa/Título e Localização Híbrida)
                            job_loc = job.get("location", "")
                            job_wp = job.get("workplace_type", "")
                            pre_match = matcher.calculate_match(
                                title, "", location=job_loc, workplace_type=job_wp, company=company
                            )
                            min_match_score = limits.get("min_match_score", 40)
                            if pre_match["score"] < min_match_score or pre_match.get("recommendation") == "SKIP":
                                skip_reason = pre_match.get("summary", f"Match insuficiente ({pre_match['score']}%)")
                                console.print(f"  [dim][PULADA] {skip_reason}: {title} @ {company}[/dim]")
                                self.tracker.record_job(
                                    job_id, title, company, job_loc, job["url"],
                                    "SKIPPED", skip_reason,
                                    match_score=pre_match["score"]
                                )
                                continue

                            total_jobs_processed_cycle += 1
                            early_badge = " [🥇 Early]" if is_early else ""
                            console.print(f"\n  [bold cyan][VAGA #{total_jobs_processed_cycle}][/bold cyan] {title} @ {company} [{job_wp}]{early_badge} (Match: {pre_match['score']}%)")
                            logger.info(f"Processando vaga {job_id}: '{title}' na empresa '{company}' [{job_wp}] (Match: {pre_match['score']}%).")

                            # 2. Execução da candidatura com retry
                            status, note = self.apply_with_retry(form_handler, job)

                            # 3. Mapear Recrutador / Hiring Team se presente na página
                            try:
                                recruiter = recruiter_finder.extract_recruiter_info(job)
                                if recruiter:
                                    self.tracker.save_recruiter(recruiter)
                                    console.print(f"    [bold magenta]🤝 Recrutador Mapeado:[/bold magenta] {recruiter['name']} ({recruiter['title']})")
                                    # Notificar no Telegram sobre recrutador encontrado
                                    telegram.notify_recruiter(
                                        recruiter_name=recruiter["name"],
                                        recruiter_title=recruiter.get("title", "Hiring Team"),
                                        company=recruiter.get("company", company),
                                        profile_url=recruiter.get("profile_url", ""),
                                        note=recruiter.get("outreach_note", "")
                                    )
                                    # Auto-Connect se configurado no bot
                                    if bot_cfg.get("auto_connect_recruiters", False) and recruiter.get("profile_url"):
                                        console.print(f"    [cyan]🚀 Enviando convite de conexão para {recruiter['name']}...[/cyan]")
                                        ok_conn, msg_conn = recruiter_finder.send_connection_invite(recruiter["profile_url"], recruiter["outreach_note"])
                                        if ok_conn:
                                            self.tracker.update_recruiter_status(recruiter.get("id", 0), "SENT")
                                            console.print(f"    [green]✅ Convite de conexão enviado com sucesso![/green]")
                            except Exception as re_err:
                                logger.debug(f"Erro ao buscar recrutador: {re_err}")

                            # 4. Refinar Match Score se descrição completa estiver disponível
                            final_score = pre_match["score"]
                            is_latam = pre_match.get("is_latam_friendly", False)
                            has_sponsorship = pre_match.get("has_visa_sponsorship", False)

                            if form_handler.current_job_desc:
                                full_match = matcher.calculate_match(
                                    title, form_handler.current_job_desc, location=job_loc, workplace_type=job_wp, company=company
                                )
                                final_score = full_match["score"]
                                is_latam = full_match.get("is_latam_friendly", is_latam)
                                has_sponsorship = full_match.get("has_visa_sponsorship", has_sponsorship)

                            self.tracker.record_job(
                                job_id, title, company, job["location"], job["url"],
                                status, note, match_score=final_score,
                                is_latam_friendly=is_latam,
                                has_visa_sponsorship=has_sponsorship
                            )

                            if status in ("APPLIED", "DRY_RUN"):
                                applied_today += 1
                                color = "green" if status == "APPLIED" else "yellow"
                                console.print(f"  [{color}][OK] {status} (Match {final_score}%): {note} ({applied_today}/{max_daily})[/{color}]")
                                logger.info(f"Resultado vaga {job_id}: {status} - {note} (Match: {final_score}%)")

                                # Notificação em tempo real no Telegram
                                telegram.notify_application(
                                    job_title=title,
                                    company=company,
                                    location=job_loc,
                                    url=job["url"],
                                    match_score=final_score,
                                    mode=status
                                )

                                # Se for oportunidade com patrocínio de visto/relocação, dispara alerta dourado extra
                                if has_sponsorship:
                                    telegram.notify_visa_sponsorship(
                                        job_title=title,
                                        company=company,
                                        location=job_loc,
                                        url=job["url"],
                                        match_score=final_score
                                    )

                                pause_sec = random.uniform(min_delay, max_delay)
                                console.print(f"  [dim]Pausa de seguranca humana: {pause_sec:.1f}s...[/dim]")
                                
                                # Pausa responsiva com verificação de cancelamento a cada 0.5s
                                elapsed = 0.0
                                while elapsed < pause_sec:
                                    if stop_event and stop_event.is_set():
                                        break
                                    time.sleep(0.5)
                                    elapsed += 0.5

                            elif status == "SKIPPED":
                                console.print(f"  [dim][PULADA] {note}[/dim]")
                                logger.info(f"Vaga {job_id} pulada: {note}")
                            else:
                                console.print(f"  [red][FALHA] {note}[/red]")
                                logger.warning(f"Vaga {job_id} falhou: {note}")

                            if progress_callback:
                                progress_callback(applied_today, max_daily)

            console.print("\n[bold green]Ciclo de busca e candidaturas finalizado com sucesso![/bold green]")
            logger.info("Ciclo de candidaturas finalizado com sucesso.")

        except KeyboardInterrupt:
            console.print("\n[yellow]Execucao interrompida pelo usuario (Ctrl+C).[/yellow]")
            logger.info("Execucao interrompida pelo usuario.")
        except Exception as e:
            console.print(f"\n[bold red]Erro inesperado no robo: {str(e)}[/bold red]")
            logger.error(f"Erro inesperado no robo: {str(e)}", exc_info=True)
        finally:
            bm.close()
            console.print("[dim]Navegador fechado com seguranca.[/dim]\n")
            logger.info("Navegador encerrado.")


# Alias para retrocompatibilidade
AutoApplyBot = ApplicationEngine
