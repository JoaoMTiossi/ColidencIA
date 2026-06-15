"""
FASE 3 — Similaridade entre marcas: bruta + ponderada por distintividade.

similarity_score(a, b)           — score bruto (Levenshtein + token_sort).
                                   Usado no override de conjunto e R3/R4 herdados.

weighted_similarity(a, b, cl, c) — score ponderado pelos pesos de distintividade
                                   de cada token. Tokens genéricos pesam ~0, então
                                   "ACT CONTAB." × "ROTA CONTAB." dá score baixo
                                   mesmo que CONTABILIDADE seja idêntico em ambas.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from ..config import THRESHOLD_IDENTICO, THRESHOLD_NUCLEO, THRESHOLD_SIMILAR
from .normalize import apply_phonetic, normalize
from .distinctiveness import token_weights


def similarity_score(a: str, b: str) -> float:
    """
    Score bruto 0.0–1.0: max(Levenshtein, token_sort_ratio).
    Usado para override de conjunto marcário (nomes quasi-idênticos no todo).
    """
    a_key = apply_phonetic(normalize(a))
    b_key = apply_phonetic(normalize(b))
    if not a_key or not b_key:
        return 0.0
    lev        = fuzz.ratio(a_key, b_key) / 100.0
    token_sort = fuzz.token_sort_ratio(a_key, b_key) / 100.0
    return max(lev, token_sort)


def weighted_similarity(a: str, b: str, classe: int, corpus: dict) -> float:
    """
    Score ponderado por distintividade 0.0–1.0.

    Alinha cada token de A com o melhor token de B (greedy por similaridade
    fonética); cada par contribui com sim(ta, tb) * w_par onde
    w_par = max(w_a, w_b).  O denominador soma todos os max-pesos para
    normalizar.  Tokens genéricos (w≈0) não inflam o score.

    Ex:
      "ACT CONTABILIDADE" × "ROTA CONTABILIDADE"
        ACT↔ROTA:           sim=0.29 w=1.00  contrib=0.29
        CONTABILIDADE↔CONT: sim=1.00 w=0.15  contrib=0.15
        soma_pesos = 1.00+0.15 = 1.15
        score = (0.29+0.15)/1.15 = 0.38  → NÃO colide ✓

      "EDIPHARMA" × "EDITH FARMA"
        EDIPHARMA↔EDITH:    sim=0.67 w=1.00  contrib=0.67
        (nada)↔FARMA:       sim=0.61 w=1.00  contrib=0.61
        soma = 2.00
        score = 1.28/2.00 = 0.64  → aciona pelo núcleo/conjunto ✓
    """
    tws_a = token_weights(a, classe, corpus)
    tws_b = token_weights(b, classe, corpus)

    if not tws_a or not tws_b:
        return similarity_score(a, b)

    used_b = set()
    total_num = 0.0
    total_den = 0.0

    # Para cada token de A, encontrar melhor parceiro em B
    for tok_a, w_a in tws_a:
        best_sim, best_j = 0.0, -1
        for j, (tok_b, w_b) in enumerate(tws_b):
            if j in used_b:
                continue
            s = fuzz.ratio(tok_a, tok_b) / 100.0
            if s > best_sim:
                best_sim, best_j = s, j

        if best_j >= 0:
            w_b = tws_b[best_j][1]
            w_pair = max(w_a, w_b)
            total_num += best_sim * w_pair
            total_den += w_pair
            used_b.add(best_j)
        else:
            total_den += w_a

    # Tokens de B não casados contribuem no denominador
    for j, (tok_b, w_b) in enumerate(tws_b):
        if j not in used_b:
            total_den += w_b

    if total_den == 0:
        return 0.0
    return min(total_num / total_den, 1.0)


__all__ = [
    'similarity_score',
    'weighted_similarity',
    'THRESHOLD_IDENTICO',
    'THRESHOLD_SIMILAR',
    'THRESHOLD_NUCLEO',
]
