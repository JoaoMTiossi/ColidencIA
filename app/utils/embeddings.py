"""
Embeddings semânticos para comparação de especificações.

Substitui o TF-IDF (que mede apenas overlap lexical) por similaridade semântica
de fato — capturando que "calçados femininos" e "sapatos para mulher" são o
mesmo conceito, e que "venda de café" e "venda de roupas" são domínios
distintos apesar de compartilharem "venda".

Usa um modelo multilíngue da família sentence-transformers. Carregamento é
lazy (acontece apenas no primeiro uso) e o modelo fica em memória.
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)
_EMBED_DIM = 384  # dimensão do MiniLM-L12

_model = None
_model_lock = threading.Lock()
_model_load_failed = False


def _get_model():
    """Carrega o modelo de embeddings (lazy, thread-safe, com fallback)."""
    global _model, _model_load_failed
    if _model_load_failed:
        return None
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Carregando modelo de embeddings: %s", _MODEL_NAME)
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info("Modelo de embeddings pronto")
        except Exception as e:
            logger.warning(
                "Falha ao carregar modelo de embeddings (%s) — usando TF-IDF fallback: %s",
                _MODEL_NAME, e,
            )
            _model_load_failed = True
            _model = None
    return _model


def embeddings_disponivel() -> bool:
    """Retorna True se o modelo de embeddings está disponível para uso."""
    return _get_model() is not None


def encode_textos(textos: list[str]) -> np.ndarray | None:
    """
    Codifica uma lista de textos em uma matriz N×D de embeddings normalizados.
    Retorna None se o modelo não estiver disponível.
    """
    if not textos:
        return np.zeros((0, _EMBED_DIM), dtype=np.float32)
    model = _get_model()
    if model is None:
        return None
    return model.encode(
        textos,
        batch_size=64,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def cosseno(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """Similaridade coseno entre embeddings já normalizados (dot product)."""
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))
