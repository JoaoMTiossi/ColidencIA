"""
Extração do núcleo marcário — parte distintiva da marca.
"""
from __future__ import annotations

import re

from ..config import COMPLEMENTOS_DESCRITIVOS, ELEMENTOS_DESGASTADOS
from .normalizacao import normalizar_base

# Stopwords que indicam início do complemento descritivo
_STOPWORDS: frozenset[str] = frozenset({
    "de", "do", "da", "dos", "das", "e", "em", "com", "para", "por",
    "ltda", "me", "epp", "eireli", "sa", "ss", "mei", "s/a",
    "comercio", "industria", "servicos", "solucoes", "assessoria",
    "consultoria", "grupo", "holding", "participacoes",
    "and", "of", "the", "for", "by", "with",
    "y", "del", "los", "las",
})

# Padrão de sigla: 2-4 letras maiúsculas, pode ter ponto separando
_RE_SIGLA = re.compile(r'^[A-Z]{2,4}\.?$')


def extrair_nucleo(marca: str) -> str:
    """
    Extrai o núcleo marcário (tokens antes do primeiro stopword/complemento).

    Exemplos:
        "INSPIRE STUDIO DE PILATES" → "INSPIRE"
        "CAVALINHO AZUL"            → "CAVALINHO AZUL"
        "NOVA GERACAO"              → "NOVA GERACAO"
    """
    norm = normalizar_base(marca)
    tokens = norm.split()
    nucleo: list[str] = []

    for tok in tokens:
        if tok in _STOPWORDS and nucleo:
            break
        if tok in COMPLEMENTOS_DESCRITIVOS and nucleo:
            break
        nucleo.append(tok)

    return " ".join(nucleo) if nucleo else norm


def is_sigla(texto: str) -> bool:
    """Retorna True se o texto normalizado parece ser uma sigla (≤4 chars alfanuméricos)."""
    norm = normalizar_base(texto).replace(" ", "").upper()
    return len(norm) <= 4 and norm.isalpha()


def is_nome_proprio(texto: str) -> bool:
    """Heurística simples: dois tokens, ambos com inicial maiúscula."""
    tokens = texto.strip().split()
    if len(tokens) < 2:
        return False
    return all(t[0].isupper() for t in tokens if t)


def is_marca_generica(nucleo: str) -> bool:
    """Retorna True se o núcleo é composto apenas por elementos desgastados."""
    tokens = set(normalizar_base(nucleo).split())
    if not tokens:
        return False
    return bool(tokens & ELEMENTOS_DESGASTADOS) and len(tokens) <= 2


def is_desgastado(marca: str) -> bool:
    """Retorna True se qualquer token principal é um elemento desgastado."""
    tokens = set(normalizar_base(marca).split())
    return bool(tokens & ELEMENTOS_DESGASTADOS)
