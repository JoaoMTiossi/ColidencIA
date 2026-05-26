"""
Análise de distintividade de marcas.

O problema central de falsos positivos é que a similaridade calculada sobre o
NOME COMPLETO é inflada por palavras descritivas/setoriais compartilhadas
(ex: "BARBEARIA", "IGREJA", "ODONTOLOGIA", "VEÍCULOS"). Duas marcas como
"BARBEARIA INTELLIMEN" e "BARBEARIA DOM INÁCIO" recebem score alto apesar de
não haver colidência real — os elementos distintivos ("intellimen" vs "inacio")
nada têm em comum.

Este módulo isola os tokens distintivos de cada marca (removendo vocabulário
descritivo) e mede a similaridade apenas entre eles.
"""
from __future__ import annotations

import csv
import os
from collections import Counter
from functools import lru_cache

from ..config import COMPLEMENTOS_DESCRITIVOS, DATA_DIR, ELEMENTOS_DESGASTADOS
from .normalizacao import normalizar_base
from .similaridade import jaro_winkler, similaridade_fonetica

# Stopwords e conectores que nunca são distintivos
_STOP: frozenset[str] = frozenset({
    "de", "do", "da", "dos", "das", "e", "em", "com", "por", "para",
    "a", "o", "os", "as", "no", "na", "nas", "nos", "um", "uma",
    "ao", "aos", "the", "of", "and", "for", "by", "la", "le", "el",
})

# Palavras descritivas/setoriais frequentes que NÃO constam na lista NICE
# (estrangeirismos e termos de atividade detectados em auditoria de RPIs).
_CURADAS: frozenset[str] = frozenset({
    "odontologia", "odonto", "dental", "tattoo", "tatuagem",
    "beauty", "care", "hair", "nails", "barber", "makeup", "make",
    "skin", "body", "wear", "fashion", "fit", "fitness",
    "burger", "grill", "sushi", "lounge", "coffee", "drinks",
    "group", "parts", "nutrition", "solutions", "consulting",
    "automotive", "motors", "engenharia", "transportes", "transporte",
    "estetica", "espaco", "studio", "space", "lab", "home", "house",
    "kids", "baby", "pet", "shopping", "loja", "store", "shop",
    "imoveis", "veiculos", "automoveis", "rastreamento", "veicular",
    "personalizada", "personalizados", "criativa", "papelaria",
    "arquitetura", "interiores", "cosmeticos", "cosmetics",
})


@lru_cache(maxsize=1)
def _vocab_nice() -> frozenset[str]:
    """Tokens que aparecem em >= 3 descrições oficiais NICE → são descritivos."""
    path = os.path.join(DATA_DIR, "nice_classificacao.csv")
    if not os.path.exists(path):
        return frozenset()
    freq: Counter[str] = Counter()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for tok in set(normalizar_base(row.get("descricao", "")).split()):
                if len(tok) >= 3:
                    freq[tok] += 1
    return frozenset(t for t, c in freq.items() if c >= 3)


@lru_cache(maxsize=1)
def _vocab_descritivo() -> frozenset[str]:
    """Vocabulário descritivo combinado (NICE + listas curadas + complementos)."""
    return (
        _vocab_nice()
        | _CURADAS
        | frozenset(COMPLEMENTOS_DESCRITIVOS)
        | frozenset(ELEMENTOS_DESGASTADOS)
    )


def tokens_distintivos(nome: str) -> list[str]:
    """Tokens com >= 3 chars que não são descritivos nem stopwords."""
    vocab = _vocab_descritivo()
    return [
        t for t in normalizar_base(nome).split()
        if len(t) >= 3 and t not in vocab and t not in _STOP
    ]


def match_distintivo(nome_a: str, nome_b: str) -> float | None:
    """
    Melhor similaridade (ortográfica OU fonética) entre os elementos
    distintivos das duas marcas.

    Retorna None quando ao menos uma das marcas não possui elemento distintivo
    próprio (é composta apenas por termos descritivos) — nesse caso só há
    colidência se os nomes completos forem praticamente idênticos.
    """
    da = tokens_distintivos(nome_a)
    db = tokens_distintivos(nome_b)
    if not da or not db:
        return None
    return max(
        max(jaro_winkler(x, y), similaridade_fonetica(x, y))
        for x in da
        for y in db
    )
