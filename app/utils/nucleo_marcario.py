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
    Extrai o núcleo marcário (parte distintiva da marca).

    Quando a marca começa com complemento descritivo (tipo de negócio),
    pula-o para encontrar o elemento verdadeiramente distintivo.

    Exemplos:
        "INSPIRE STUDIO DE PILATES"         → "INSPIRE"
        "INSTITUTO DA ACÚSTICA"             → "acustica"
        "PIZZARIA DO VAQUEIRO 2022"         → "vaqueiro 2022"
        "BARBEARIA STUDIO MATTOS"           → "mattos"
        "RESTAURANTE CASA DO NORDESTINO"    → "nordestino"
        "CAVALINHO AZUL"                    → "cavalinho azul"
    """
    norm = normalizar_base(marca)
    tokens = norm.split()

    # Pular complementos descritivos do início (ex: restaurante, instituto, barbearia)
    # e stopwords sequenciais (de, do, da) antes da parte distintiva.
    start = 0
    if len(tokens) > 1:
        while start < len(tokens) and tokens[start] in COMPLEMENTOS_DESCRITIVOS:
            start += 1
        while start < len(tokens) and tokens[start] in _STOPWORDS:
            start += 1

    nucleo: list[str] = []
    for tok in tokens[start:]:
        if tok in _STOPWORDS and nucleo:
            break
        if tok in COMPLEMENTOS_DESCRITIVOS and nucleo:
            break
        nucleo.append(tok)

    nucleo_str = " ".join(nucleo) if nucleo else norm
    # Permite siglas de 2 chars (LL, MS, LK); só rejeita núcleo de 1 char
    if len(nucleo_str.replace(" ", "")) < 2:
        return norm
    return nucleo_str


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
    """Retorna True se o núcleo é composto majoritariamente por elementos desgastados."""
    tokens = normalizar_base(nucleo).split()
    if not tokens:
        return False
    desg = sum(1 for t in tokens if t in ELEMENTOS_DESGASTADOS)
    if desg == len(tokens):
        return True
    if len(tokens) >= 3 and desg / len(tokens) >= 2 / 3:
        return True
    return False


def extrair_nucleo_distintivo(nucleo: str) -> str:
    """
    Remove tokens desgastados das bordas do núcleo para revelar o elemento
    verdadeiramente distintivo.

    Exemplos:
        "saude jaguara"   → "jaguara"
        "cafe joao"       → "joao"
        "saude forte"     → ""   (todos desgastados)
        "jaguara saude"   → "jaguara"
        "jaguara"         → "jaguara"
    """
    tokens = normalizar_base(nucleo).split()
    while tokens and tokens[0] in ELEMENTOS_DESGASTADOS:
        tokens.pop(0)
    while tokens and tokens[-1] in ELEMENTOS_DESGASTADOS:
        tokens.pop()
    return " ".join(tokens)


def is_desgastado(marca: str) -> bool:
    """Retorna True se qualquer token principal é um elemento desgastado."""
    tokens = set(normalizar_base(marca).split())
    return bool(tokens & ELEMENTOS_DESGASTADOS)
