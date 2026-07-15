"""
Peso IDF (Inverse Document Frequency) para dosar o crédito de similaridade
concedido a um TOKEN COMPARTILHADO entre duas marcas.

Problema: em fonetica.py::_score_fonetico, um token compartilhado entre as
duas marcas de um par recebe crédito fixo (0.72 exato/metaphone, 0.70 quase,
0.62 desgastado) independente de quão comum esse token é. Isso trata
igualmente "CAPRICHO" (raro, altamente distintivo) e "MEGA"/"TOP"/"MAX"
(onipresentes, sem força distintiva) — poluindo o relatório com dezenas de
alertas fracos entre marcas que só têm em comum um termo de mercado genérico.

peso_idf(token) devolve um fator em [0.5, 1.0]:
  - token raro                         → próximo de 1.0 (crédito integral).
  - token muito comum / desgastado     → 0.5 (metade do crédito).
  - interpolação logarítmica entre os dois extremos.

Fonte de frequência: as ~10.449 descrições oficiais de produtos/serviços NICE
(app/data/nice_classificacao.csv) servem de proxy de "quão comum" é um token
no universo marcário/comercial. Termos de marketing genéricos que raramente
aparecem nessas descrições técnicas (ex.: "mega", "top", "king") não seriam
capturados só pela frequência no corpus — por isso a lista
ELEMENTOS_DESGASTADOS (config.py) é usada como sinal complementar e decisivo
de "muito comum": qualquer token nela cai direto no piso 0.5.

Corpus ausente/vazio → peso_idf devolve 1.0 para qualquer token (equivalente
a não aplicar nenhum desconto — comportamento idêntico ao anterior a este
módulo).
"""
from __future__ import annotations

import csv
import math
import os
from collections import Counter
from functools import lru_cache

from ..config import DATA_DIR, ELEMENTOS_DESGASTADOS
from .normalizacao import normalizar_base

PESO_IDF_MIN: float = 0.5
PESO_IDF_MAX: float = 1.0


@lru_cache(maxsize=1)
def _doc_freq() -> tuple[Counter, int]:
    """Frequência de documentos (linhas do CSV NICE) que contêm cada token.

    Retorna (Counter() vazio, 0) se o arquivo não existir — tratado por
    peso_idf como corpus vazio (devolve 1.0, sem penalização).
    """
    path = os.path.join(DATA_DIR, "nice_classificacao.csv")
    if not os.path.exists(path):
        return Counter(), 0
    freq: Counter = Counter()
    n = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n += 1
            for tok in set(normalizar_base(row.get("descricao", "")).split()):
                if len(tok) >= 2:
                    freq[tok] += 1
    return freq, n


@lru_cache(maxsize=4096)
def peso_idf(token: str) -> float:
    """Peso [0.5, 1.0] de crédito a conceder a um token compartilhado entre
    duas marcas.

    - Corpus indisponível → 1.0 (sem alterar comportamento anterior).
    - Token vazio → 1.0.
    - Token em ELEMENTOS_DESGASTADOS → 0.5 (piso): sinal de "muito comum" que
      independe da frequência no corpus NICE (termos de marketing como
      "mega"/"top" raramente aparecem em descrições técnicas de produto).
    - Demais tokens: interpolação log entre 1.0 (nunca visto no corpus) e 0.5
      (presente em praticamente todo documento).
    """
    tok = normalizar_base(token or "").strip()
    if not tok:
        return PESO_IDF_MAX

    freq, n = _doc_freq()
    if n == 0:
        return PESO_IDF_MAX

    if tok in ELEMENTOS_DESGASTADOS:
        return PESO_IDF_MIN

    df = freq.get(tok, 0)
    if df == 0:
        return PESO_IDF_MAX

    # rel cresce de 0 (token raríssimo) a ~1 (token em quase todo documento).
    rel = math.log(df + 1) / math.log(n + 1)
    peso = PESO_IDF_MAX - (PESO_IDF_MAX - PESO_IDF_MIN) * rel
    return max(PESO_IDF_MIN, min(PESO_IDF_MAX, peso))
