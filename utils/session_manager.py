"""
Gerenciador de verificação e controle da sessão do LinkedIn.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

SESSION_DIR = Path(".session")


def is_session_dir_initialized() -> bool:
    """Verifica se a pasta de sessão existe e contém arquivos de perfil."""
    if not SESSION_DIR.exists():
        return False
    # Checar se existem arquivos de cache/cookies dentro
    items = list(SESSION_DIR.glob("*"))
    return len(items) > 0


def check_linkedin_login_status() -> Tuple[bool, str]:
    """
    Testa rapidamente a sessão abrindo o navegador em modo headless para verificar se o feed carrega.
    """
    if not is_session_dir_initialized():
        return False, "Sessão não configurada. Faça login inicial."

    try:
        from core.browser import BrowserManager
        bm = BrowserManager(session_dir=str(SESSION_DIR), headless=True)
        bm.start()
        is_logged, msg = bm.is_logged_in()
        bm.close()
        return is_logged, msg
    except Exception as e:
        return False, f"Erro ao verificar sessão: {str(e)}"


def launch_manual_login_process():
    """Inicia o script setup_session.py em uma nova janela de terminal para o usuário logar."""
    python_exe = sys.executable
    cmd = [python_exe, "setup_session.py"]
    if sys.platform == "win32":
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(cmd)
