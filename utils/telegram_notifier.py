"""
Módulo de notificações em tempo real via Telegram Bot.
Envia alertas instantâneos de candidaturas aplicadas e recrutadores mapeados.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Tuple, Optional
import yaml

logger = logging.getLogger("AutoApplyBot")


class TelegramNotifier:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        """Carrega credenciais do config.yaml e variáveis de ambiente .env."""
        cfg = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception:
                pass

        tg_cfg = cfg.get("telegram", {})
        self.enabled = tg_cfg.get("enabled", False)

        # Prioriza variável de ambiente (.env), com fallback para config.yaml
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", tg_cfg.get("bot_token", "")).strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", tg_cfg.get("chat_id", "")).strip()

    def is_configured(self) -> bool:
        """Verifica se o bot está com token e chat_id configurados."""
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Envia mensagem de texto para o chat configurado via API HTTP do Telegram."""
        if not self.is_configured():
            logger.debug("Telegram não configurado. Notificação ignorada.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("Notificação enviada com sucesso no Telegram.")
                    return True
        except Exception as e:
            logger.warning(f"Falha ao enviar notificação no Telegram: {e}")
            return False

        return False

    def test_connection(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> Tuple[bool, str]:
        """Testa o token do bot e envia uma mensagem de teste."""
        bot_token = (token or self.bot_token or "").strip()
        cid = (str(chat_id) if chat_id is not None else self.chat_id or "").strip()

        if not bot_token:
            return False, "Token do bot do Telegram não informado."
        if not cid:
            return False, "Chat ID do Telegram não informado."

        old_token = self.bot_token
        old_cid = self.chat_id
        self.bot_token = bot_token
        self.chat_id = cid
        try:
            msg = (
                "🤖 <b>LinkedIn AutoApply AI Conectado!</b>\n\n"
                "✅ Seu bot do Telegram está funcionando perfeitamente.\n"
                "Você receberá alertas em tempo real a cada candidatura e recrutador mapeado!"
            )
            success = self.send_message(msg)
            if success:
                return True, "Mensagem de teste enviada com sucesso para o Telegram!"
            return False, "Erro ao conectar. Verifique se o Bot Token e o Chat ID estão corretos."
        finally:
            self.bot_token = old_token
            self.chat_id = old_cid

    def notify_application(
        self,
        job_title: str,
        company: str,
        location: str,
        url: str,
        match_score: int,
        mode: str = "APPLIED"
    ) -> bool:
        """Notifica o envio de uma candidatura."""
        if not self.enabled:
            return False

        mode_badge = "🚀 <b>Candidatura Enviada!</b>" if mode == "APPLIED" else "🟡 <b>Simulação (Dry-Run)</b>"
        msg = (
            f"{mode_badge}\n\n"
            f"📌 <b>Cargo:</b> {job_title}\n"
            f"🏢 <b>Empresa:</b> {company}\n"
            f"📍 <b>Localização:</b> {location}\n"
            f"🎯 <b>Match Score:</b> {match_score}%\n\n"
            f"🔗 <a href='{url}'>Ver Vaga no LinkedIn</a>"
        )
        return self.send_message(msg)

    def notify_recruiter(
        self,
        recruiter_name: str,
        recruiter_title: str,
        company: str,
        profile_url: str,
        note: str
    ) -> bool:
        """Notifica quando um recrutador / hiring team é identificado."""
        if not self.enabled:
            return False

        msg = (
            f"🤝 <b>Novo Recrutador Mapeado!</b>\n\n"
            f"👤 <b>Nome:</b> {recruiter_name}\n"
            f"💼 <b>Cargo:</b> {recruiter_title}\n"
            f"🏢 <b>Empresa:</b> {company}\n\n"
            f"📝 <b>Mensagem de Conexão Sugerida:</b>\n"
            f"<code>{note}</code>\n\n"
        )
        if profile_url:
            msg += f"🔗 <a href='{profile_url}'>Abrir Perfil no LinkedIn</a>"

        return self.send_message(msg)

    def notify_visa_sponsorship(
        self,
        job_title: str,
        company: str,
        location: str,
        url: str,
        match_score: int
    ) -> bool:
        """Envia alerta de alta prioridade quando uma vaga com patrocínio de visto ou relocação é detectada."""
        if not self.enabled:
            return False

        msg = (
            "✈️ <b>ALERTA DOURADO: PATROCÍNIO DE VISTO / RELOCATION!</b>\n\n"
            f"🎯 <b>Cargo:</b> {job_title}\n"
            f"🏢 <b>Empresa:</b> {company}\n"
            f"📍 <b>Localização:</b> {location}\n"
            f"⭐ <b>Match Score:</b> {match_score}%\n\n"
            "✨ <i>Esta empresa declarou suporte explícito a visto de trabalho ou assistência de realocação para profissionais internacionais.</i>\n\n"
            f"🔗 <a href='{url}'>Ver Vaga no LinkedIn</a>"
        )
        return self.send_message(msg)

