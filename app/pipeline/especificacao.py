"""
Camada 3 — Filtro de especificação/afinidade.
Combina três estratégias: tabela de correlatas, classes colidentes, TF-IDF.
"""
from __future__ import annotations

import csv
import json
import os
from functools import lru_cache

from ..config import COLLISIONS, THRESHOLD_ESPECIFICACAO, DATA_DIR


# ---------------------------------------------------------------------------
# Carregamento de dados de referência
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _carregar_correlatas() -> dict[tuple[int, int], float]:
    """Carrega especificacoes_correlatas.csv como dict {(ncl_a, ncl_b): afinidade}."""
    path = os.path.join(DATA_DIR, "especificacoes_correlatas.csv")
    resultado: dict[tuple[int, int], float] = {}
    if not os.path.exists(path):
        return resultado
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                a = int(row.get("ncl_a", 0))
                b = int(row.get("ncl_b", 0))
                af = float(row.get("afinidade", 0))
                resultado[(a, b)] = af
                resultado[(b, a)] = af
            except (ValueError, KeyError):
                pass
    return resultado


@lru_cache(maxsize=1)
def _carregar_traducoes() -> dict[str, str]:
    """Carrega traducoes.json como dict {termo_en: termo_pt}."""
    path = os.path.join(DATA_DIR, "traducoes.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Estratégia 3A — Tabela de correlatas
# ---------------------------------------------------------------------------

def _afinidade_correlatas(ncl_a: int, ncl_b: int) -> float:
    correlatas = _carregar_correlatas()
    return correlatas.get((ncl_a, ncl_b), 0.0)


# ---------------------------------------------------------------------------
# Estratégia 3B — Classes colidentes
# ---------------------------------------------------------------------------

def _afinidade_classes(ncl_a: int, ncl_b: int) -> float:
    if ncl_a == ncl_b:
        return 0.8
    if ncl_b in COLLISIONS.get(ncl_a, []):
        return 0.7
    return 0.0


# ---------------------------------------------------------------------------
# Estratégia 3C — TF-IDF cosine similarity
# ---------------------------------------------------------------------------

def _afinidade_tfidf(spec_a: str, spec_b: str) -> float:
    """Similaridade coseno entre especificações via TF-IDF."""
    if not spec_a or not spec_b:
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        vect = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        tfidf = vect.fit_transform([spec_a, spec_b])
        sim = cosine_similarity(tfidf[0], tfidf[1])[0][0]
        return float(sim)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Camada 3 principal
# ---------------------------------------------------------------------------

def camada3(candidatos: list[dict]) -> list[dict]:
    """
    Filtra candidatos pela afinidade de especificação.
    Mantém apenas pares com score_spec ≥ THRESHOLD_ESPECIFICACAO.

    Lógica de pontuação (em ordem de prioridade):
      1. Correlatas: tabela curada de afinidade entre classes — valor direto.
      2. Texto (TF-IDF): similaridade das especificações — valor primário.
         Classes colidentes adicionam bônus (+0.15 mesma / +0.10 colidentes)
         mas NÃO aprovam automaticamente sem overlap textual.
      3. Sem texto: apenas mesma classe passa (com cap conservador).
         Classes apenas colidentes (diferentes) são rejeitadas sem texto.
    """
    aprovados: list[dict] = []

    for par in candidatos:
        ncl_a = par.get("ncl_base", 0)
        ncl_b = par.get("ncl_rpi", 0)
        spec_a = par.get("spec_base", "")
        spec_b = par.get("spec_rpi", "")

        sc_3a = _afinidade_correlatas(ncl_a, ncl_b)
        sc_3b = _afinidade_classes(ncl_a, ncl_b)  # 0.8 mesma / 0.7 colidentes / 0.0
        sc_3c = _afinidade_tfidf(spec_a, spec_b)

        if sc_3b == 0.0:
            # Classes sem colisão: apenas texto ou correlatas
            score_spec = max(sc_3a, sc_3c)
        elif spec_a and spec_b:
            # Classes colidentes E texto presente: texto é primário, classe é bônus
            bonus = 0.15 if sc_3b >= 0.8 else 0.10
            score_spec = min(1.0, sc_3c + bonus)
            score_spec = max(score_spec, sc_3a)
        else:
            # Classes colidentes mas sem texto: apenas mesma classe passa
            # (classes apenas colidentes sem spec são descartadas)
            score_spec = sc_3b * 0.52 if sc_3b >= 0.8 else 0.0
            score_spec = max(score_spec, sc_3a)

        if score_spec >= THRESHOLD_ESPECIFICACAO:
            updated = dict(par)
            updated["score_spec"] = round(score_spec, 4)
            updated["camada_deteccao"] = 3
            aprovados.append(updated)

    return aprovados
