"""
Camada 3 — Filtro de especificação/afinidade.
Combina três estratégias: tabela de correlatas, classes colidentes,
similaridade semântica (embeddings multilíngues, com fallback TF-IDF).
"""
from __future__ import annotations

import csv
import json
import logging
import os
from functools import lru_cache

from ..config import COLLISIONS, THRESHOLD_ESPECIFICACAO, DATA_DIR
from ..utils.embeddings import cosseno, embeddings_disponivel, encode_textos

logger = logging.getLogger(__name__)


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
# Estratégia 3C (legado) — TF-IDF cosine similarity
# Mantido como fallback caso os embeddings não estejam disponíveis.
# ---------------------------------------------------------------------------

def _afinidade_tfidf(spec_a: str, spec_b: str) -> float:
    if not spec_a or not spec_b:
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vect = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        tfidf = vect.fit_transform([spec_a, spec_b])
        sim = cosine_similarity(tfidf[0], tfidf[1])[0][0]
        return float(sim)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Estratégia 3C — Similaridade semântica via embeddings
# ---------------------------------------------------------------------------

def _construir_indice_embeddings(candidatos: list[dict]) -> dict[str, "np.ndarray"]:
    """Codifica todos os textos de especificação únicos em uma única chamada."""
    textos_unicos: list[str] = []
    vistos: set[str] = set()
    for par in candidatos:
        for chave in ("spec_base", "spec_rpi"):
            txt = (par.get(chave) or "").strip()
            if txt and txt not in vistos:
                vistos.add(txt)
                textos_unicos.append(txt)

    if not textos_unicos:
        return {}

    embeddings = encode_textos(textos_unicos)
    if embeddings is None:
        return {}

    return {txt: emb for txt, emb in zip(textos_unicos, embeddings)}


# ---------------------------------------------------------------------------
# Camada 3 principal
# ---------------------------------------------------------------------------

def camada3(candidatos: list[dict]) -> list[dict]:
    """
    Filtra candidatos pela afinidade de especificação.
    Mantém apenas pares com score_spec ≥ THRESHOLD_ESPECIFICACAO.

    Estratégia de combinação:
        - sc_3a: tabela de correlatas (manual, alta confiança quando existe)
        - sc_3b: classes NCL (igual = 0.8, colidente = 0.7, senão 0)
        - sc_3c: similaridade semântica via embeddings (0.0-1.0)

    A modulação semântica reduz score_spec quando o spec semântico contradiz
    o sinal de classe — i.e., classes podem colidir formalmente mas se os
    textos descrevem produtos genuinamente diferentes, score_spec é dampened.
    Isso ataca os falsos positivos do tipo "mesma classe, conteúdo distinto".
    """
    if not candidatos:
        return []

    usar_embeddings = embeddings_disponivel()
    indice_emb: dict[str, object] = {}
    if usar_embeddings:
        logger.info("Camada 3: usando embeddings semânticos para %d candidatos", len(candidatos))
        indice_emb = _construir_indice_embeddings(candidatos)
    else:
        logger.info("Camada 3: embeddings indisponíveis — usando TF-IDF fallback")

    aprovados: list[dict] = []

    for par in candidatos:
        ncl_a = par.get("ncl_base", 0)
        ncl_b = par.get("ncl_rpi", 0)
        spec_a = (par.get("spec_base") or "").strip()
        spec_b = (par.get("spec_rpi") or "").strip()

        sc_3a = _afinidade_correlatas(ncl_a, ncl_b)
        sc_3b = _afinidade_classes(ncl_a, ncl_b)

        if usar_embeddings and indice_emb:
            emb_a = indice_emb.get(spec_a)
            emb_b = indice_emb.get(spec_b)
            sc_3c = cosseno(emb_a, emb_b)
        else:
            sc_3c = _afinidade_tfidf(spec_a, spec_b)

        # Modulação semântica: o sinal de classe é confirmado/temperado pela
        # similaridade semântica REAL. Aplicada somente com embeddings (TF-IDF
        # é ruidoso demais para servir de confirmação). Se os textos descrevem
        # domínios genuinamente distintos (sc_3c baixo), reduz-se a contribuição
        # de "mesma classe NCL" — atacando o falso positivo do tipo "compartilham
        # classe formal mas o produto é outro".
        if usar_embeddings and sc_3b > 0 and spec_a and spec_b:
            fator_confirmacao = 0.25 + 0.75 * min(1.0, sc_3c / 0.40)
            sc_3b_aj = sc_3b * fator_confirmacao
        else:
            sc_3b_aj = sc_3b

        score_spec = max(sc_3a, sc_3b_aj, sc_3c)

        if score_spec >= THRESHOLD_ESPECIFICACAO:
            updated = dict(par)
            updated["score_spec"] = round(score_spec, 4)
            updated["score_spec_semantico"] = round(sc_3c, 4)
            updated["camada_deteccao"] = 3
            aprovados.append(updated)

    return aprovados
