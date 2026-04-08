"""
Métricas de similaridade entre marcas.
"""
from __future__ import annotations

import jellyfish
from rapidfuzz import fuzz

from .normalizacao import jaccard_bigramas, normalizar_base
from .metaphone_ptbr import metaphone_ptbr


def jaro_winkler(a: str, b: str) -> float:
    """Jaro-Winkler normalizado (0.0–1.0) sobre textos normalizados."""
    na = normalizar_base(a)
    nb = normalizar_base(b)
    if not na or not nb:
        return 0.0
    try:
        return jellyfish.jaro_winkler_similarity(na, nb)
    except Exception:
        return 0.0


def levenshtein_normalizado(a: str, b: str) -> float:
    """Distância de Levenshtein normalizada (0.0–1.0)."""
    na = normalizar_base(a)
    nb = normalizar_base(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return fuzz.ratio(na, nb) / 100.0


def token_sort(a: str, b: str) -> float:
    """Token Sort Ratio (ordem irrelevante)."""
    na = normalizar_base(a)
    nb = normalizar_base(b)
    return fuzz.token_sort_ratio(na, nb) / 100.0


def token_set(a: str, b: str) -> float:
    """Token Set Ratio (interseção de tokens)."""
    na = normalizar_base(a)
    nb = normalizar_base(b)
    return fuzz.token_set_ratio(na, nb) / 100.0


def similaridade_nome(a: str, b: str) -> float:
    """
    Score combinado para comparação de nomes de marcas.
    Usa o máximo entre Jaro-Winkler, Token Sort e Jaccard de bigramas.
    """
    jw = jaro_winkler(a, b)
    ts = token_sort(a, b)
    jac = jaccard_bigramas(a, b)
    return max(jw, ts, jac)


def similaridade_fonetica(a: str, b: str) -> float:
    """Compara os códigos fonéticos Metaphone PT-BR."""
    ka = metaphone_ptbr(normalizar_base(a))
    kb = metaphone_ptbr(normalizar_base(b))
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    return fuzz.ratio(ka, kb) / 100.0


def similaridade_par(nome_a: str, nucleo_a: str, nome_b: str, nucleo_b: str) -> dict[str, float]:
    """
    Calcula todas as métricas de similaridade para um par de marcas.
    Retorna dict com: score_nome, score_fonetico, score_nucleo, score_bigrama
    """
    s_nome = similaridade_nome(nome_a, nome_b)
    s_fon = similaridade_fonetica(nome_a, nome_b)
    s_nucleo = max(
        similaridade_nome(nucleo_a, nucleo_b),
        similaridade_fonetica(nucleo_a, nucleo_b),
    )
    s_bigrama = jaccard_bigramas(nome_a, nome_b)

    return {
        "score_nome": round(s_nome, 4),
        "score_fonetico": round(s_fon, 4),
        "score_nucleo": round(s_nucleo, 4),
        "score_bigrama": round(s_bigrama, 4),
    }
