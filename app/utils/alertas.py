"""
Notificações de disponibilidade via webhook.

Envia mensagem POST quando o serviço sobe ou cai, permitindo
monitoramento sem ferramentas externas. Suporta Discord e qualquer
webhook genérico que aceite JSON.

Configure via variável de ambiente:
    ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/ID/TOKEN
    ALERT_SERVICE_NAME=ColidencIA-Producao
"""
from __future__ import annotations

import logging
import socket
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "desconhecido"


def _payload(mensagem: str, webhook_url: str) -> dict:
    """Monta o payload correto para Discord ou webhook genérico."""
    if "discord.com" in webhook_url:
        return {"content": mensagem}
    # Slack / genérico
    return {"text": mensagem}


def enviar_alerta(mensagem: str) -> None:
    """Dispara o webhook de forma síncrona. Não lança exceções."""
    from ..config import ALERT_WEBHOOK_URL, ALERT_SERVICE_NAME  # evita import circular

    if not ALERT_WEBHOOK_URL:
        return

    try:
        import urllib.request
        import json

        texto = f"[{ALERT_SERVICE_NAME}] {mensagem} | host: {_hostname()}"
        payload = _payload(texto, ALERT_WEBHOOK_URL)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            ALERT_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 204):
                logger.warning("Webhook retornou status %d", resp.status)
    except Exception as exc:
        logger.warning("Falha ao enviar alerta: %s", exc)


async def enviar_alerta_async(mensagem: str) -> None:
    """Versão assíncrona — roda `enviar_alerta` em thread para não bloquear."""
    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, enviar_alerta, mensagem)


def alerta_startup() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"✅ Serviço INICIADO em {now}"


def alerta_shutdown() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"🔴 Serviço ENCERRADO em {now}"
