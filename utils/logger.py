"""
Sistema de streaming de logs em memória para a interface Streamlit.
"""

import logging
from collections import deque
from datetime import datetime
from typing import List, Dict

# Fila circular thread-safe para armazenar os últimos 200 logs
LOG_BUFFER = deque(maxlen=200)


class StreamlitLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage()
            }
            LOG_BUFFER.append(log_entry)
        except Exception:
            self.handleError(record)


# Instância global do handler
_handler_instance = None


def setup_streamlit_logger():
    """Conecta o buffer de logs ao logger principal do robô."""
    global _handler_instance
    logger = logging.getLogger("AutoApplyBot")
    if _handler_instance is None:
        _handler_instance = StreamlitLogHandler()
        _handler_instance.setLevel(logging.INFO)
        logger.addHandler(_handler_instance)
    return logger


def get_recent_logs(limit: int = 100) -> List[Dict[str, str]]:
    """Retorna os logs mais recentes armazenados no buffer."""
    return list(LOG_BUFFER)[-limit:]


def clear_logs():
    """Limpa o buffer de logs."""
    LOG_BUFFER.clear()
