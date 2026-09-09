"""
Painel interativo via Linha de Comando (CLI) para controle do robo de vagas internacionais.
"""

import sys
import os
import re
from pathlib import Path

# Garantir encoding UTF-8 no terminal Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

from core.engine import ApplicationEngine
from core.tracker import ApplicationTracker
from core.ai_solver import QuestionSolver
from setup_session import setup_login_session

console = Console()
CONFIG_PATH = Path("config/config.yaml")
PROFILE_PATH = Path("config/profile.yaml")


def show_banner():
    banner_text = (
        "[bold cyan]>> AUTO-APPLY LINKEDIN INTERNACIONAL <<[/bold cyan]\n"
        "[dim]Candidaturas automaticas com IA, filtros remotos globais e protecao anti-bloqueio[/dim]"
    )
    console.print(Panel.fit(banner_text, border_style="cyan"))


def get_current_dry_run_state() -> bool:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("bot", {}).get("dry_run", True)
    except Exception:
        return True


def toggle_dry_run():
    """Modifica o arquivo config.yaml preservando integralmente todos os comentários existentes."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(r"dry_run:\s*(true|false)", content, re.IGNORECASE)
        if match:
            current_str = match.group(1).lower()
            new_state = current_str == "false"
            new_str = "true" if new_state else "false"
            content = re.sub(r"dry_run:\s*(true|false)", f"dry_run: {new_str}", content, count=1, flags=re.IGNORECASE)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(content)

            if new_state:
                console.print("\n[bold yellow][OK] Modo SIMULACAO (Dry-Run) ATIVADO.[/bold yellow] O robo preenchera sem submeter.")
            else:
                console.print("\n[bold red][OK] Modo REAL ATIVADO.[/bold red] O robo submetera as candidaturas automaticamente.")
        else:
            console.print("[red]Nao foi possivel encontrar a chave 'dry_run' no arquivo config.yaml.[/red]")
    except Exception as e:
        console.print(f"[red]Erro ao alterar configuracao: {e}[/red]")


def view_statistics():
    """Exibe as estatísticas usando o tracker.display_statistics()."""
    tracker = ApplicationTracker()
    tracker.display_statistics(console=console)


def test_question_solver():
    """Testa o resolvedor de perguntas com casos reais de formulários internacionais."""
    console.print("\n[bold cyan][TESTE] Resolucao de Perguntas Frequentes Internacionais:[/bold cyan]")
    solver = QuestionSolver(str(PROFILE_PATH), str(CONFIG_PATH))

    test_cases = [
        ("How many years of work experience do you have with Python?", "number", []),
        ("How many years of experience do you have with React?", "number", []),
        ("Are you legally authorized to work in the United States?", "radio", ["Yes", "No"]),
        ("Will you now or in the future require visa sponsorship?", "radio", ["Yes", "No"]),
        ("What is your English language proficiency level?", "select", ["Basic", "Intermediate", "Fluent", "Native"]),
        ("What is your desired annual compensation (in USD)?", "number", []),
        ("Are you comfortable working remotely as an independent contractor (B2B)?", "radio", ["Yes", "No"]),
        ("What is your notice period or availability to start?", "text", []),
        ("Please share your LinkedIn profile URL.", "text", []),
        ("Please share your GitHub URL.", "text", []),
    ]

    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Pergunta do Formulario")
    table.add_column("Tipo")
    table.add_column("Resposta Automatica Gerada", style="bold green")

    for q, ftype, opts in test_cases:
        ans = solver.answer_question(q, ftype, opts)
        table.add_row(q, ftype, str(ans))

    console.print(table)
    console.print("[dim]Voce pode customizar todas as respostas no arquivo config/profile.yaml[/dim]\n")


def run_applications_with_progress():
    """Inicia o ApplicationEngine com feedback e barra de progresso."""
    tracker = ApplicationTracker()
    today_count = tracker.get_applications_today_count()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            max_daily = cfg.get("limits", {}).get("max_applications_per_day", 15)
    except Exception:
        max_daily = 15

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[bold cyan]{task.completed}/{task.total} vagas[/bold cyan]"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Candidaturas Hoje", total=max_daily, completed=min(today_count, max_daily))

        def update_progress(current, total):
            progress.update(task, completed=current, total=total)

        engine = ApplicationEngine(str(CONFIG_PATH), str(PROFILE_PATH))
        engine.run(progress_callback=update_progress)


def main():
    while True:
        try:
            show_banner()
            dry_run = get_current_dry_run_state()
            mode_badge = "[bold yellow][SIMULACAO][/bold yellow]" if dry_run else "[bold red][MODO REAL][/bold red]"

            console.print(f"Status Atual do Robo: {mode_badge}\n")
            console.print("[1] Iniciar candidaturas automaticas")
            console.print("[2] Ver estatisticas")
            console.print("[3] Testar respostas do resolvedor de perguntas")
            console.print("[4] Alternar modo Dry-Run / Real")
            console.print("[5] Sair")
            console.print("[dim]------------------------------------[/dim]")
            console.print("[0] Configuracao de Login / Setup Session\n")

            choice = Prompt.ask("Escolha uma opcao", choices=["1", "2", "3", "4", "5", "0"], default="1")

            if choice == "1":
                run_applications_with_progress()
            elif choice == "2":
                view_statistics()
            elif choice == "3":
                test_question_solver()
            elif choice == "4":
                toggle_dry_run()
            elif choice == "5":
                console.print("\n[cyan]Saindo... Boas candidaturas internacionais![/cyan]\n")
                break
            elif choice == "0":
                setup_login_session()

            Prompt.ask("\nPressione [ENTER] para voltar ao menu")
            console.clear()

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Operacao cancelada pelo usuario (Ctrl+C).[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[bold red]Erro no menu principal: {str(e)}[/bold red]")
            Prompt.ask("\nPressione [ENTER] para continuar")
            console.clear()


if __name__ == "__main__":
    main()
