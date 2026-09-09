import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yaml
from rich.console import Console
from rich.panel import Panel
from core.browser import BrowserManager

console = Console()

def setup_login_session():
    console.print(Panel.fit(
        "[bold cyan]Configuração de Sessão Segura do LinkedIn[/bold cyan]\n\n"
        "1. Uma janela real do navegador será aberta.\n"
        "2. Acesse sua conta do LinkedIn com seu e-mail e senha.\n"
        "3. Complete a verificação em duas etapas (2FA) ou CAPTCHA, se solicitado.\n"
        "4. Quando estiver no seu Feed inicial do LinkedIn, [bold green]retorne aqui e pressione ENTER[/bold green].\n\n"
        "[dim]Sua sessão ficará salva de forma persistente e o robô não precisará de sua senha.[/dim]",
        border_style="cyan"
    ))

    # Carregar configuração da sessão
    session_dir = ".session"
    try:
        with open("config/config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            session_dir = cfg.get("bot", {}).get("session_dir", ".session")
    except Exception:
        pass

    bm = BrowserManager(session_dir=session_dir, headless=False)
    page = bm.start()

    console.print("[yellow]Navegando para o LinkedIn...[/yellow]")
    page.goto("https://www.linkedin.com/login")

    input("\n>>> Quando você tiver feito login com sucesso e estiver no Feed, pressione [ENTER] para salvar e fechar: ")

    # Verificar se o login foi bem sucedido
    current_url = page.url
    if "feed" in current_url or "mynetwork" in current_url or "jobs" in current_url:
        console.print("[bold green]✔ Sessão autenticada e salva com sucesso no diretório persistente![/bold green]")
    else:
        console.print(f"[yellow]Aviso: URL atual é '{current_url}'. A sessão foi salva, mas certifique-se de estar conectado.[/yellow]")

    bm.close()
    console.print("[green]Navegador fechado com segurança. Você já pode iniciar o robô.[/green]\n")

if __name__ == "__main__":
    setup_login_session()
