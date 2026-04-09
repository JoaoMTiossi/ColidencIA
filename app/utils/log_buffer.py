"""
Buffer circular de logs em memória para exibição na interface web.
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Deque


_MAX_ENTRIES = 300

# Buffer global acessível por toda a aplicação
_buffer: Deque[dict] = deque(maxlen=_MAX_ENTRIES)


def get_logs(limit: int = 100, since_id: int = 0) -> list[dict]:
    """Retorna as últimas entradas do buffer, opcionalmente após um ID."""
    entries = list(_buffer)
    if since_id:
        entries = [e for e in entries if e["id"] > since_id]
    return entries[-limit:]


def add_log(level: str, message: str, source: str = "app") -> None:
    """Adiciona uma entrada ao buffer manualmente."""
    entry_id = _buffer[-1]["id"] + 1 if _buffer else 1
    _buffer.append({
        "id": entry_id,
        "ts": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "source": source,
        "msg": message,
    })


class WebLogHandler(logging.Handler):
    """Handler que envia logs do Python para o buffer web."""

    _counter = 0

    def emit(self, record: logging.LogRecord) -> None:
        WebLogHandler._counter += 1
        try:
            msg = self.format(record)
            # Truncar mensagens longas
            if len(msg) > 300:
                msg = msg[:297] + "..."
            # Ignorar logs muito verbosos de libs externas
            if record.name.startswith(("httpx", "httpcore", "urllib3", "multipart")):
                return
            entry_id = _buffer[-1]["id"] + 1 if _buffer else 1
            _buffer.append({
                "id": entry_id,
                "ts": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "source": record.name.split(".")[-1],
                "msg": msg,
            })
        except Exception:
            pass


def instalar_handler() -> None:
    """Instala o handler de log web na raiz do logging."""
    handler = WebLogHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    # Não instalar duas vezes
    if not any(isinstance(h, WebLogHandler) for h in root.handlers):
        root.addHandler(handler)
