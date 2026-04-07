"""
Cálculo de similaridade entre marcas usando RapidFuzz (3 algoritmos em paralelo).
"""

from __future__ import annotations

from rapidfuzz import fuzz

from ..config import THRESHOLD_IDENTICO, THRESHOLD_NUCLEO, THRESHOLD_SIMILAR
from .normalize import apply_phonetic, normalize


def similarity_score(a: str, b: str) -> float:
    """
    Retorna score 0.0–1.0 combinando 3 algoritmos.

    Usa o MÁXIMO dos 3 resultados (conservador: qualquer algoritmo que acuse = marcar).
        - Levenshtein ratio
        - Token Sort Ratio  (ordem das palavras não importa)
        - Token Set Ratio   (interseção de tokens)

    Ambas as strings passam por normalização base + equivalências fonéticas
    antes da comparação.
    """
    a_key = apply_phonetic(normalize(a))
    b_key = apply_phonetic(normalize(b))

    if not a_key or not b_key:
        return 0.0

    lev        = fuzz.ratio(a_key, b_key) / 100.0
    token_sort = fuzz.token_sort_ratio(a_key, b_key) / 100.0
    token_set  = fuzz.token_set_ratio(a_key, b_key) / 100.0

    return max(lev, token_sort, token_set)


__all__ = [
    'similarity_score',
    'THRESHOLD_IDENTICO',
    'THRESHOLD_SIMILAR',
    'THRESHOLD_NUCLEO',
]
