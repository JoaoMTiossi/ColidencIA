"""
Camada de distintividade — peso por token combinando lista curada + corpus de specs.

w(token, classe) ∈ [0.0, 1.0]:
  0.0 → totalmente genérico  (DE, LTDA, SEGUROS na cl.36)
  1.0 → totalmente distintivo (EDIPHARMA, AIKA, VELTI)

Três sinais combinados (min de todos → qualquer evidência de genericidade rebaixa):
  1. Lista curada (term_common): CAT_1/2/3 — cobertura universal
  2. Corpus de ESPECIFICAÇÕES por classe: tokens que os próprios requerentes
     usam para descrever seus produtos (sinal mais forte e preciso)
     Ex: "ESFIHA" em 42 specs da cl.30 → descritor da cl.30
         "LAVA JATO" em 18 specs da cl.37 → descritor da cl.37
"""

from __future__ import annotations

from .normalize import apply_phonetic, normalize
from ..data.term_common import (
    CAT_1_DESCRITORES,
    CAT_2_QUALIFICADORES,
    CAT_3_ESTRUTURAIS,
)

# ---------------------------------------------------------------------------
# Pesos da lista curada
# ---------------------------------------------------------------------------
_W_ESTRUTURAL    = 0.00   # DE, DO, LTDA
_W_DESCRITOR     = 0.15   # CONTABILIDADE, ENGENHARIA
_W_QUALIFICADOR  = 0.25   # BRASIL, MASTER, PRIME
_W_PROPRIO       = 1.00   # não está em nenhuma lista → presumivelmente distintivo

# ---------------------------------------------------------------------------
# Limiares do corpus de specs para classificar como descritor de classe
# ---------------------------------------------------------------------------
_SPEC_DF_MIN  = 5      # aparece em ≥5 specs da classe → descritor
_SPEC_FR_MIN  = 0.03   # ou em ≥3% das specs da classe → descritor
_W_SPEC_DESC  = 0.10   # peso atribuído a token descritor por spec

# (corpus de nomes de marca removido — sinal ambíguo, como discutido)


def _w_semente(token_norm: str) -> float:
    """Peso da lista curada. Usa forma normalizada (pré-fonética)."""
    t = token_norm.upper()
    if t in CAT_3_ESTRUTURAIS:   return _W_ESTRUTURAL
    if t in CAT_1_DESCRITORES:   return _W_DESCRITOR
    if t in CAT_2_QUALIFICADORES: return _W_QUALIFICADOR
    return _W_PROPRIO


def _w_spec(token_norm: str, classe: int, spec_corpus: dict) -> float:
    """
    Peso baseado no corpus de ESPECIFICAÇÕES da classe.
    Token que aparece frequentemente nas specs → descreve o produto → peso baixo.
    """
    if not spec_corpus:
        return 1.0
    cls_key = str(classe)
    N  = spec_corpus.get('_N', {}).get(cls_key, 0)
    df = spec_corpus.get(cls_key, {}).get(token_norm, 0)
    if df == 0 or N == 0:
        return 1.0
    fr = df / N
    if df >= _SPEC_DF_MIN or fr >= _SPEC_FR_MIN:
        return _W_SPEC_DESC
    return 1.0


def weight(token: str, classe: int, spec_corpus: dict) -> float:
    """
    Peso de distintividade combinado: min(semente, spec_corpus).
    """
    t = normalize(token)
    if not t:
        return 0.0
    ws = _w_semente(t)
    wc = _w_spec(t, classe, spec_corpus)
    return min(ws, wc)


def is_descriptive(token: str, classe: int, spec_corpus: dict) -> tuple[bool, str]:
    """
    Retorna (é_descritor, motivo) para uso no raciocínio da IA.

    Ex: is_descriptive("ESFIHA", 30, corpus)
        → (True, "aparece em 42/412 specs da cl.30 (10.2%) — descritor do produto")
    """
    t = normalize(token)
    if not t:
        return False, ''

    t_up = t.upper()
    if t_up in CAT_3_ESTRUTURAIS:
        return True, 'preposição/conjunção/sufixo jurídico — sem valor distintivo'
    if t_up in CAT_1_DESCRITORES:
        return True, f'descritor de segmento (lista curada) — não monopolizável'
    if t_up in CAT_2_QUALIFICADORES:
        return True, f'qualificador genérico (lista curada) — baixa distintividade'

    if spec_corpus:
        cls_key = str(classe)
        N  = spec_corpus.get('_N', {}).get(cls_key, 0)
        df = spec_corpus.get(cls_key, {}).get(t, 0)
        if N > 0 and df > 0:
            fr = df / N
            if df >= _SPEC_DF_MIN or fr >= _SPEC_FR_MIN:
                return True, (f'aparece em {df}/{N} specs da cl.{classe} ({fr:.1%})'
                              f' — descritor declarado do produto/serviço')

    return False, ''


def token_weights(marca: str, classe: int, spec_corpus: dict,
                  min_len: int = 3) -> list[tuple[str, float]]:
    """Retorna lista de (token_fonetico, peso) para todos os tokens."""
    result = []
    for tok in normalize(marca).split():
        if len(tok) < min_len:
            continue
        tp = apply_phonetic(tok)
        w  = weight(tok, classe, spec_corpus)
        result.append((tp, w))
    return result


def distinctive_tokens(marca: str, classe: int, spec_corpus: dict,
                        min_len: int = 3) -> list[tuple[str, float, bool, str]]:
    """
    Retorna lista de (token_original, peso, é_descritor, motivo) para análise IA.
    Permite que a IA explique por que cada token conta ou não.
    """
    result = []
    for tok in normalize(marca).split():
        if len(tok) < min_len:
            continue
        w   = weight(tok, classe, spec_corpus)
        is_d, motivo = is_descriptive(tok, classe, spec_corpus)
        result.append((tok, w, is_d, motivo))
    return result
