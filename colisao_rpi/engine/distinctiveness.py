"""
FASE 2 — Peso de distintividade por token.

w(token, classe) ∈ [0.0, 1.0]
  0.0 → totalmente genérico (DE, LTDA, SEGUROS na classe 36)
  1.0 → totalmente distintivo (EDIPHARMA, AIKA, VELTI)

Combinação híbrida: semente (lista estática) + corpus (frequência por classe).
  - Qualquer sinal de genericidade rebaixa o peso (min de ambos).
  - Corpus vazio → só semente (comportamento seguro de fallback).
"""

from __future__ import annotations

from .normalize import apply_phonetic, normalize
from ..data.term_common import (
    CAT_1_DESCRITORES,
    CAT_2_QUALIFICADORES,
    CAT_3_ESTRUTURAIS,
)

# Pesos da semente por categoria
_W_ESTRUTURAL   = 0.00   # DE, DO, LTDA — sem valor distintivo
_W_DESCRITOR    = 0.15   # CONTABILIDADE, ENGENHARIA — descreve segmento
_W_QUALIFICADOR = 0.25   # BRASIL, MASTER, PRIME — qualifica mas não distingue
_W_PROPRIO      = 1.00   # token não na lista → presumivelmente distintivo

# Limiares do corpus para rebaixar para genérico
_CORPUS_DF_MIN  = 10     # nº de marcas na classe contendo o token
_CORPUS_FR_MIN  = 0.005  # frequência relativa mínima (0.5% das marcas da classe)
_W_CORPUS_GENERICO = 0.20


def _w_semente(token_norm: str) -> float:
    """
    Peso baseado na lista estática. Recebe a forma NORMALIZADA (pré-fonética)
    para garantir que 'SUSHI' (não 'SUXI') seja encontrado na lista.
    """
    t = token_norm.upper()
    if t in CAT_3_ESTRUTURAIS:
        return _W_ESTRUTURAL
    if t in CAT_1_DESCRITORES:
        return _W_DESCRITOR
    if t in CAT_2_QUALIFICADORES:
        return _W_QUALIFICADOR
    return _W_PROPRIO


def _w_corpus(token: str, classe: int, corpus: dict) -> float:
    """
    Peso baseado na frequência do token na classe dentro do corpus.
    Retorna 1.0 se corpus vazio ou token inédito (sem penalidade).
    """
    if not corpus:
        return 1.0
    cls_key = str(classe)
    N   = corpus.get('_N', {}).get(cls_key, 0)
    df  = corpus.get(cls_key, {}).get(token, 0)
    if df == 0 or N == 0:
        return 1.0  # inédito → distintivo
    fr = df / N
    if df >= _CORPUS_DF_MIN or fr >= _CORPUS_FR_MIN:
        return _W_CORPUS_GENERICO
    return 1.0


def weight(token: str, classe: int, corpus: dict) -> float:
    """
    Peso de distintividade combinado: min(semente, corpus).
    Qualquer sinal de genericidade rebaixa o token.

    Usa a forma NORMALIZADA (pré-fonética) para lookup na lista estática,
    e a forma FONÉTICA para lookup no corpus (consistente com indexação).
    """
    t  = normalize(token)       # normalizado: sem acentos, uppercase, sem pontuação
    if not t:
        return 0.0
    tp = apply_phonetic(t)      # fonético: para corpus
    ws = _w_semente(t)          # lista: usa forma normalizada (ex: "SUSHI" não "SUXI")
    wc = _w_corpus(tp, classe, corpus)
    return min(ws, wc)


def token_weights(marca: str, classe: int, corpus: dict,
                  min_len: int = 3) -> list[tuple[str, float]]:
    """
    Retorna lista de (token_fonetico, peso) para todos os tokens da marca.
    Tokens com peso 0 são incluídos para contabilização do denominador.
    """
    result = []
    for tok in normalize(marca).split():
        if len(tok) < min_len:
            continue
        tp = apply_phonetic(tok)
        w  = weight(tok, classe, corpus)
        result.append((tp, w))
    return result
