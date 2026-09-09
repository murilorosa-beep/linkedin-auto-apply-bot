"""
Módulo de inicialização e controle do navegador Playwright com perfil persistente e comportamento humano.
"""

import os
import random
import time
from typing import Optional
from playwright.sync_api import sync_playwright, BrowserContext, Page


class BrowserManager:
    def __init__(self, session_dir: str = ".session", headless: bool = False):
        self.session_dir = os.path.abspath(session_dir)
        self.headless = headless
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        os.makedirs(self.session_dir, exist_ok=True)

    def start(self) -> Page:
        """Inicia o contexto persistente usando preferencialmente o Google Chrome real com stealth avançado."""
        self.playwright = sync_playwright().start()

        # Argumentos do Chrome para neutralizar detecção de automação
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--start-maximized",
            "--no-default-browser-check",
            "--no-first-run"
        ]

        # Detectar se o Google Chrome ou Edge oficial está instalado no Windows
        channel_to_use = None
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
        if any(os.path.exists(p) for p in chrome_paths):
            channel_to_use = "chrome"
        elif os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            channel_to_use = "msedge"

        launch_kwargs = {
            "user_data_dir": self.session_dir,
            "headless": self.headless,
            "args": args,
            "ignore_default_args": ["--enable-automation"],
            "locale": "pt-BR,en-US",
            "timezone_id": "America/Sao_Paulo",
            "bypass_csp": True,
        }

        if channel_to_use:
            launch_kwargs["channel"] = channel_to_use

        if not self.headless:
            launch_kwargs["no_viewport"] = True
        else:
            launch_kwargs["viewport"] = {"width": 1366, "height": 768}

        try:
            self.context = self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            # Fallback se o canal específico falhar
            if "channel" in launch_kwargs:
                del launch_kwargs["channel"]
                self.context = self.playwright.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise

        # Usar a primeira página aberta pelo contexto persistente
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        # Injetar script para camuflar automação (remover navigator.webdriver e expor chrome nativo)
        self.page.add_init_script("""
            // 1. Remover flag de automação
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 2. Simular objeto chrome nativo
            window.navigator.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // 3. Plugins e linguagens naturais
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en'],
            });

            // 4. Mascarar permissões
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        return self.page

    def human_delay(self, min_seconds: float = 2.0, max_seconds: float = 5.0):
        """Pausa por tempo aleatório simulando o tempo de leitura ou reação humana."""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def human_type(self, selector: str, text: str, clear_first: bool = True):
        """Digita texto simulando velocidade humana caractere por caractere."""
        if not self.page:
            return

        locator = self.page.locator(selector)
        locator.scroll_into_view_if_needed()
        locator.click()

        if clear_first:
            locator.fill("")
            self.human_delay(0.2, 0.5)

        for char in str(text):
            locator.type(char, delay=random.randint(35, 95))
            if random.random() < 0.05:  # Pequena pausa ocasional de digitação
                time.sleep(random.uniform(0.1, 0.3))

    def human_click(self, selector: str):
        """Move o mouse e clica em um elemento com pequena pausa natural."""
        if not self.page:
            return
        locator = self.page.locator(selector)
        locator.scroll_into_view_if_needed()
        self.human_delay(0.3, 0.8)
        locator.click()
        self.human_delay(0.5, 1.2)

    def scroll_page(self, distance: int = 400, steps: int = 3):
        """Rola a página suavemente para baixo."""
        if not self.page:
            return
        for _ in range(steps):
            self.page.mouse.wheel(0, distance)
            self.human_delay(0.4, 0.9)

    def is_logged_in(self) -> tuple[bool, str]:
        """
        Verifica se a sessão do LinkedIn está ativa e válida.
        Retorna (True, 'ok') se estiver no feed, ou (False, motivo) caso contrário.
        """
        if not self.page:
            return False, "Navegador não iniciado."

        try:
            self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            self.human_delay(2.0, 3.5)

            current_url = self.page.url.lower()

            # 1. Sucesso: Página de Feed, Minha Rede ou Vagas
            if any(path in current_url for path in ["/feed", "/mynetwork", "/jobs"]):
                return True, "Sessão autenticada e ativa com sucesso."

            # 2. Desafio de Segurança / CAPTCHA
            if any(path in current_url for path in ["/checkpoint", "/challenge", "/security"]):
                return False, "Desafio de seguranca ou CAPTCHA detectado. Execute 'python setup_session.py' para resolver manualmente."

            # Verificar presença explícita de iframes de CAPTCHA
            if self.page.locator("iframe[title*='recaptcha'], iframe[title*='challenge'], #captcha-internal").count() > 0:
                return False, "CAPTCHA detectado na pagina. Necessario resolver manualmente."

            # 3. Não autenticado (tela de login)
            if any(path in current_url for path in ["/login", "/signup", "/uas/login"]):
                return False, "Sessao expirada ou desconectada. Execute 'python setup_session.py' para logar."

            return False, f"Pagina inesperada apos navegar para o feed ({self.page.url})."

        except Exception as e:
            return False, f"Falha de conexao ao validar sessao: {str(e)}"

    def close(self):
        """Fecha o contexto e o Playwright com segurança."""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
