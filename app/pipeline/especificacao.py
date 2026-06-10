"""
Camada 3 — Filtro de especificação/afinidade.
Combina três estratégias: tabela de correlatas, classes colidentes,
similaridade semântica (embeddings multilíngues, com fallback TF-IDF batch).

Para cross-class, a especificação TEXTUAL decide — não apenas o número NCL.
Classe 35 (transversal) não dá passe automático a todos os pares.
"""
from __future__ import annotations

import csv
import json
import logging
import os
from functools import lru_cache

import numpy as np

from ..config import (
    AFINIDADE_TRANSVERSAL,
    CLASSES_TRANSVERSAIS,
    COLLISIONS,
    DATA_DIR,
    THRESHOLD_ESPECIFICACAO,
    THRESHOLD_SPEC_CROSS,
)
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
        return 0.95
    af_tabela = _afinidade_correlatas(ncl_a, ncl_b)
    # Transversal (35) e não-classificada (0): o CSV pode refinar para cima, mas
    # nunca abaixo de AFINIDADE_TRANSVERSAL — é o piso mínimo destas classes.
    if ncl_a in CLASSES_TRANSVERSAIS or ncl_b in CLASSES_TRANSVERSAIS:
        return max(af_tabela, AFINIDADE_TRANSVERSAL)
    if ncl_a == 0 or ncl_b == 0:
        return max(af_tabela, AFINIDADE_TRANSVERSAL)
    if af_tabela > 0:
        return af_tabela
    if ncl_b in COLLISIONS.get(ncl_a, []) or ncl_a in COLLISIONS.get(ncl_b, []):
        return 0.60
    return 0.0


# ---------------------------------------------------------------------------
# Estratégia 3C — TF-IDF batch (fallback quando embeddings indisponíveis)
#
# Diferente do legado (um vectorizer por par), aqui treinamos UN ÚNICO
# vectorizer em todas as specs únicas e calculamos cosine em batch via
# operação matricial. Resultado: O(n) em vez de O(n²) vectorizers.
# ---------------------------------------------------------------------------

def _batch_tfidf(textos_a: list[str], textos_b: list[str]) -> list[float]:
    """
    Calcula cosine TF-IDF para N pares (spec_a[i], spec_b[i]) em batch.
    Retorna lista de floats com um score por par.
    """
    if not textos_a:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        # Corpus único: specs de ambos os lados (sem duplicatas desnecessárias)
        corpus = textos_a + textos_b
        vect = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        mat = vect.fit_transform(corpus)

        n = len(textos_a)
        mat_a = mat[:n]   # specs da carteira
        mat_b = mat[n:]   # specs da RPI

        # Diagonal da matriz de similaridade = score par a par
        # Evitar cosine_similarity full (n×n) — usar multiplicação linha a linha
        scores: list[float] = []
        for i in range(n):
            row_a = mat_a[i]
            row_b = mat_b[i]
            sim = cosine_similarity(row_a, row_b)[0][0]
            scores.append(float(sim))
        return scores

    except Exception as exc:
        logger.warning("TF-IDF batch falhou: %s", exc)
        return [0.0] * len(textos_a)


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

    Estratégia:
      - Mesma classe: passa com base no sinal de classe (rápido).
      - Cross-class: a ESPECIFICAÇÃO TEXTUAL decide.
        Passes automáticos somente quando a afinidade de classe é ≥ 0.80
        (correlatas genuínas) OU quando há overlap textual real (TF-IDF/embeddings).
        Classe 35 (transversal) NÃO concede passe automático cross-class —
        sua afinidade baixou para AFINIDADE_TRANSVERSAL=0.45, abaixo do gate 0.80.

    Scores:
      sc_3a = tabela de correlatas (0 se ausente)
      sc_3b = afinidade de classes (0.95 mesma, 0.45–0.80 cross)
      sc_3c = similaridade textual (embeddings > TF-IDF batch > 0.0)
    """
    if not candidatos:
        return []

    usar_embeddings = embeddings_disponivel()
    indice_emb: dict[str, object] = {}
    if usar_embeddings:
        logger.info("Camada 3: usando embeddings semânticos para %d candidatos", len(candidatos))
        indice_emb = _construir_indice_embeddings(candidatos)
    else:
        logger.info("Camada 3: embeddings indisponíveis — pré-calculando TF-IDF em batch")

    # Pré-calcular TF-IDF em batch para todos os pares (quando sem embeddings)
    tfidf_scores: list[float] = []
    if not usar_embeddings:
        specs_a = [(par.get("spec_base") or "").strip() for par in candidatos]
        specs_b = [(par.get("spec_rpi") or "").strip() for par in candidatos]
        tfidf_scores = _batch_tfidf(specs_a, specs_b)

    aprovados: list[dict] = []

    for i, par in enumerate(candidatos):
        ncl_a = par.get("ncl_base", 0)
        ncl_b = par.get("ncl_rpi", 0)
        spec_a = (par.get("spec_base") or "").strip()
        spec_b = (par.get("spec_rpi") or "").strip()

        sc_3a = _afinidade_correlatas(ncl_a, ncl_b)
        sc_3b = _afinidade_classes(ncl_a, ncl_b)

        # Score textual: embeddings (se disponíveis) ou TF-IDF batch
        if usar_embeddings and indice_emb:
            emb_a = indice_emb.get(spec_a)
            emb_b = indice_emb.get(spec_b)
            sc_3c = cosseno(emb_a, emb_b)
        elif tfidf_scores:
            sc_3c = tfidf_scores[i]
        else:
            sc_3c = 0.0

        mesma_classe = (ncl_a == ncl_b)
        # Pares vindos da Camada 1 (nome idêntico): aplicar gate mais suave.
        # O nome ser idêntico já é o sinal mais forte — a classe só precisa ter
        # alguma relação (mesmo que fraca). O gate textual cross-class não se aplica.
        nome_identico = (par.get("camada_deteccao") == 1)

        if mesma_classe:
            # Mesma classe: sinal de classe suficiente (sc_3b=0.95 sempre passa)
            if usar_embeddings and sc_3b > 0 and spec_a and spec_b:
                # Modulação semântica suave: não reduz abaixo de 60% do sc_3b
                fator = max(0.60, 0.25 + 0.75 * min(1.0, sc_3c / 0.40))
                sc_3b_aj = sc_3b * fator
            else:
                sc_3b_aj = sc_3b
            score_spec = max(sc_3a, sc_3b_aj, sc_3c)

        elif nome_identico:
            # Cross-class mas nome idêntico: gate suave — basta haver qualquer
            # afinidade de classe (inclui correlatas fracas e COLLISIONS).
            if sc_3b < THRESHOLD_ESPECIFICACAO and sc_3a < THRESHOLD_ESPECIFICACAO:
                continue  # apenas descarta se classes completamente sem relação
            score_spec = max(sc_3a, sc_3b, sc_3c)

        else:
            # Cross-class: a especificação TEXTUAL decide.
            # Passe automático só quando a afinidade de classe é genuinamente alta
            # (correlatas manuais ≥ 0.80) — classe 35 com AFINIDADE_TRANSVERSAL=0.45
            # não satisfaz este critério e precisará de overlap textual.
            spec_ok = sc_3c >= THRESHOLD_SPEC_CROSS
            classe_genuina = sc_3b >= 0.80  # afim por tabela de correlatas ou COLLISIONS forte

            if not spec_ok and not classe_genuina:
                continue  # descarta cross-class sem overlap textual nem classe genuína

            # Score: blend ponderado priorizando o sinal de texto
            if spec_ok:
                score_spec = max(sc_3a, sc_3b * 0.5 + sc_3c * 0.5, sc_3c)
            else:
                # Classe genuína mas sem overlap textual: afinidade reduzida
                score_spec = sc_3b * 0.70

        if score_spec >= THRESHOLD_ESPECIFICACAO:
            updated = dict(par)
            updated["score_spec"] = round(score_spec, 4)
            updated["score_spec_semantico"] = round(sc_3c, 4)
            updated["camada_deteccao"] = 3
            aprovados.append(updated)

    return aprovados
