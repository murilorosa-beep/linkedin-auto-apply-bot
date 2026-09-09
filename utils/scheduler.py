"""
Motor de Agendamento Automático em Segundo Plano (Smart Scheduler).
Monitora horários de pico (ex: 09:30 e 15:00) e executa o robô no piloto automático.
"""

import time
import datetime
import threading
import logging
from typing import List, Optional, Callable, Dict, Any
from utils.config_manager import load_config

logger = logging.getLogger("AutoApplyBot")


class SmartScheduler:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SmartScheduler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, run_callback: Optional[Callable] = None):
        if getattr(self, "_initialized", False):
            if run_callback:
                self.run_callback = run_callback
            return

        self.run_callback = run_callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_run_slots: set = set()
        self._initialized = True

    def start(self):
        """Inicia a thread do agendador em segundo plano caso ainda não esteja rodando."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SmartSchedulerThread")
        self._thread.start()
        logger.info("SmartScheduler iniciado com sucesso.")

    def stop(self):
        """Para a thread do agendador."""
        self._stop_event.set()
        logger.info("SmartScheduler interrompido.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self):
        """Loop contínuo de verificação a cada 20 segundos."""
        while not self._stop_event.is_set():
            try:
                cfg = load_config()
                sched_cfg = cfg.get("scheduler", {})
                is_enabled = sched_cfg.get("enabled", False)

                if is_enabled and self.run_callback:
                    target_times: List[str] = sched_cfg.get("times", ["09:30", "15:00"])
                    now = datetime.datetime.now()
                    current_hm = now.strftime("%H:%M")
                    current_date_hm = now.strftime("%Y-%m-%d_") + current_hm

                    for target_hm in target_times:
                        slot_id = f"{now.strftime('%Y-%m-%d')}_{target_hm.strip()}"
                        if current_hm == target_hm.strip() and slot_id not in self._last_run_slots:
                            logger.info(f"Horário de pico atingido ({target_hm})! Iniciando ciclo automático.")
                            self._last_run_slots.add(slot_id)
                            try:
                                self.run_callback()
                            except Exception as e:
                                logger.error(f"Erro ao executar callback do agendador: {e}")

                # Limpeza diária de slots antigos
                if len(self._last_run_slots) > 20:
                    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
                    self._last_run_slots = {s for s in self._last_run_slots if s.startswith(today_str)}

            except Exception as e:
                logger.debug(f"Erro no ciclo do agendador: {e}")

            time.sleep(20)

    def get_next_run(self) -> str:
        """Calcula o próximo horário de execução programado."""
        cfg = load_config()
        sched_cfg = cfg.get("scheduler", {})
        if not sched_cfg.get("enabled", False):
            return "Desativado"

        target_times = sorted(sched_cfg.get("times", ["09:30", "15:00"]))
        if not target_times:
            return "Nenhum horário configurado"

        now = datetime.datetime.now()
        current_hm = now.strftime("%H:%M")

        # Procura o próximo horário hoje
        for t in target_times:
            if t > current_hm:
                return f"Hoje às {t}"

        # Se todos já passaram hoje, será o primeiro de amanhã
        return f"Amanhã às {target_times[0]}"
