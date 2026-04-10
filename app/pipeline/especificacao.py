"""
Camada 3 — Filtro de especificação/afinidade.
Combina três estratégias: tabela de correlatas, classes colidentes, TF-IDF.

Performance: TF-IDF é calculado em BATCH (1 fit para todo o lote),
não individualmente por par. Isso reduz de ~400k chamadas sklearn para 1.
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
# Estratégia 3C — TF-IDF cosine similarity (BATCH)
# ---------------------------------------------------------------------------

def _construir_indice_tfidf(specs: list[str]) -> dict:
    """
    Constrói índice TF-IDF para uma lista de especificações únicas.
    Retorna dict com 'vectorizer' e 'matrix' (linhas = índice em specs).
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vect = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        matrix = vect.fit_transform(specs)
        return {"vectorizer": vect, "matrix": matrix, "specs": specs}
    except Exception:
        return {}


def _cosine_sim_batch(
    indice: dict,
    spec_to_idx: dict[str, int],
    pairs: list[tuple[str, str]],
) -> list[float]:
    """
    Calcula similaridade coseno em batch para uma lista de pares (spec_a, spec_b).
    Usa matriz TF-IDF pré-computada — muito mais rápido que per-pair.
    """
    if not indice:
        return [0.0] * len(pairs)

    try:
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        matrix = indice["matrix"]
        scores: list[float] = []

        # Processar em sub-lotes para controlar uso de memória
        CHUNK = 5000
        for i in range(0, len(pairs), CHUNK):
            chunk = pairs[i:i + CHUNK]
            idx_a = [spec_to_idx.get(sa, -1) for sa, _ in chunk]
            idx_b = [spec_to_idx.get(sb, -1) for _, sb in chunk]

            valid = [(j, a, b) for j, (a, b) in enumerate(zip(idx_a, idx_b))
                     if a >= 0 and b >= 0]

            chunk_scores = [0.0] * len(chunk)
            if valid:
                rows_a = matrix[[v[1] for v in valid]]
                rows_b = matrix[[v[2] for v in valid]]
                # Diagonal da matriz de similaridade = sim entre pares correspondentes
                sims = np.array(rows_a.multiply(rows_b).sum(axis=1)).flatten()
                # Normalizar (TF-IDF com sublinear_tf pode não estar L2-norm)
                norms_a = np.sqrt(np.array(rows_a.power(2).sum(axis=1)).flatten())
                norms_b = np.sqrt(np.array(rows_b.power(2).sum(axis=1)).flatten())
                denom = norms_a * norms_b
                denom[denom == 0] = 1.0
                cosines = sims / denom
                for k, (j, _, _) in enumerate(valid):
                    chunk_scores[j] = float(max(0.0, cosines[k]))

            scores.extend(chunk_scores)

        return scores
    except Exception:
        return [0.0] * len(pairs)


# ---------------------------------------------------------------------------
# Camada 3 principal
# ---------------------------------------------------------------------------

def camada3(candidatos: list[dict]) -> list[dict]:
    """
    Filtra candidatos pela afinidade de especificação.
    Mantém apenas pares com score_spec ≥ THRESHOLD_ESPECIFICACAO.

    Lógica de pontuação:
      - Classes colidentes adicionam bônus (+0.15 mesma / +0.10 colidentes)
        mas NÃO aprovam sem overlap textual (TF-IDF necessário).
      - Sem texto de spec: apenas mesma classe passa (cap conservador).
        Classes apenas colidentes sem texto são rejeitadas.
      - TF-IDF calculado em batch (1 fit por chamada, não 1 por par).
    """
    if not candidatos:
        return []

    # ── 1. Pré-computar sc_3a e sc_3b; separar pares que precisam de TF-IDF ──
    meta: list[tuple[float, float, str, str]] = []  # (sc_3a, sc_3b, spec_a, spec_b)
    for par in candidatos:
        ncl_a = par.get("ncl_base", 0)
        ncl_b = par.get("ncl_rpi", 0)
        sc_3a = _afinidade_correlatas(ncl_a, ncl_b)
        sc_3b = _afinidade_classes(ncl_a, ncl_b)
        spec_a = par.get("spec_base") or ""
        spec_b = par.get("spec_rpi") or ""
        meta.append((sc_3a, sc_3b, spec_a, spec_b))

    # ── 2. Construir índice TF-IDF batch sobre specs únicas ──
    unique_specs: list[str] = []
    spec_to_idx: dict[str, int] = {}
    for _, _, sa, sb in meta:
        for s in (sa, sb):
            if s and s not in spec_to_idx:
                spec_to_idx[s] = len(unique_specs)
                unique_specs.append(s)

    indice = _construir_indice_tfidf(unique_specs) if unique_specs else {}

    # Identificar quais pares precisam TF-IDF (têm texto em ambos os lados)
    pairs_tfidf = [(sa, sb) for _, _, sa, sb in meta]
    sc_3c_list = _cosine_sim_batch(indice, spec_to_idx, pairs_tfidf)

    # ── 3. Aplicar lógica de score e filtro ──
    aprovados: list[dict] = []
    for par, (sc_3a, sc_3b, spec_a, spec_b), sc_3c in zip(candidatos, meta, sc_3c_list):

        if sc_3b == 0.0:
            # Classes sem colisão: apenas texto ou correlatas decidem
            score_spec = max(sc_3a, sc_3c)
        elif spec_a and spec_b:
            # Classes colidentes com texto: texto é primário, classe é bônus
            bonus = 0.15 if sc_3b >= 0.8 else 0.10
            score_spec = min(1.0, sc_3c + bonus)
            score_spec = max(score_spec, sc_3a)
        else:
            # Classes colidentes sem texto: apenas mesma classe passa (conservador)
            score_spec = sc_3b * 0.52 if sc_3b >= 0.8 else 0.0
            score_spec = max(score_spec, sc_3a)

        if score_spec >= THRESHOLD_ESPECIFICACAO:
            updated = dict(par)
            updated["score_spec"] = round(score_spec, 4)
            updated["camada_deteccao"] = 3
            aprovados.append(updated)

    return aprovados
