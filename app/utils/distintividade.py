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
import json
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
    # Odontologia / saúde bucal
    "odontologia", "odonto", "dental", "ortodontia", "implante", "implantes",
    "protese", "proteses", "clareamento", "ortodontico",
    # Estética e beleza
    "tattoo", "tatuagem", "beauty", "care", "hair", "nails", "barber",
    "makeup", "make", "skin", "body", "wear", "fashion", "fit", "fitness",
    "estetica", "estetico", "beleza", "cabelo", "cabelos", "corte",
    "unhas", "depilacao", "massagem", "spa",
    # Termos evocativos genéricos em nomes de marcas de saúde/beleza
    # Nota: "viva" e "vita" removidos — são elementos primários de marca
    # em muitos casos (ex.: "VIVA+", "VITA CARE") e não devem ser eliminados.
    "sorriso", "sorrisos", "saude", "bem",
    "belo", "bela", "bella", "feliz", "felicidade", "alegria",
    "lindo", "linda", "bonito", "bonita", "perfeito", "perfeita",
    # Alimentos e bebidas
    "burger", "grill", "sushi", "lounge", "coffee", "drinks",
    # Negócios e serviços genéricos
    "group", "parts", "nutrition", "solutions", "consulting",
    # Automotivo
    "automotive", "motors", "funilaria", "serralheria", "borracharia",
    "mecanica", "funileiro",
    # Setores de serviço
    "engenharia", "transportes", "transporte",
    "otica", "oticas", "joalheria", "relojoaria", "floricultura",
    "lavanderia", "tinturaria", "chaveiro", "marcenaria",
    "pintura", "eletrica", "hidraulica",
    # Estabelecimento e espaço
    "espaco", "studio", "space", "lab", "home", "house",
    # Público-alvo descritivo
    "kids", "baby", "pet",
    # Comércio
    "shopping", "loja", "store", "shop",
    # Imóveis e veículos
    "imoveis", "veiculos", "automoveis", "rastreamento", "veicular",
    # Comunicação / papelaria
    "personalizada", "personalizados", "criativa", "papelaria",
    # Design e interiores
    "arquitetura", "interiores", "cosmeticos", "cosmetics",
    # Saúde e bem-estar
    "nutricao", "dieta", "bemestar",
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
def _vocab_inpi_servicos() -> frozenset[str]:
    """Tokens que aparecem em >= 2 descrições de serviços INPI → são descritivos."""
    path = os.path.join(DATA_DIR, "inpi_servicos.csv")
    if not os.path.exists(path):
        return frozenset()
    freq: Counter[str] = Counter()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for tok in set(normalizar_base(row.get("descricao", "")).split()):
                if len(tok) >= 3:
                    freq[tok] += 1
    return frozenset(t for t, c in freq.items() if c >= 2)


@lru_cache(maxsize=1)
def _vocab_descritivo() -> frozenset[str]:
    """Vocabulário descritivo combinado (NICE + INPI serviços + listas curadas + complementos)."""
    return (
        _vocab_nice()
        | _vocab_inpi_servicos()
        | _CURADAS
        | frozenset(COMPLEMENTOS_DESCRITIVOS)
        | frozenset(ELEMENTOS_DESGASTADOS)
    )


@lru_cache(maxsize=1)
def _vocab_corpus() -> dict[int, frozenset[str]]:
    """Vocabulário descritivo por classe, minerado do corpus acumulado de marcas.
    Ausência do arquivo é tratada silenciosamente (dict vazio = sem efeito)."""
    path = os.path.join(DATA_DIR, "vocab_descritivo_corpus.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {int(k): frozenset(v) for k, v in data.items()}
    except Exception:
        return {}


def tokens_distintivos(nome: str, ncl: int | None = None) -> list[str]:
    """Tokens com >= 2 chars que não são descritivos nem stopwords.

    O mínimo de 2 permite capturar siglas e marcas curtas genuínas ("OK",
    "RM", "BK") que são filtradas de forma errada com limite 3.
    Os 2-char connectors do português ("de", "do", "da", "os", "as"…)
    já estão cobertos por _STOP, então o limite 2 é seguro.

    Quando `ncl` é informado, remove também os termos identificados como
    descritivos para aquela classe específica pelo corpus acumulado.
    """
    vocab = _vocab_descritivo()
    vocab_ncl = _vocab_corpus().get(ncl, frozenset()) if ncl is not None else frozenset()
    return [
        t for t in normalizar_base(nome).split()
        if len(t) >= 2
        and not t.isdigit()          # Remove tokens puramente numéricos ("2022", "123")
        and t not in vocab
        and t not in vocab_ncl
        and t not in _STOP
    ]


def match_distintivo(
    nome_a: str,
    nome_b: str,
    ncl_a: int | None = None,
    ncl_b: int | None = None,
) -> float | None:
    """
    Melhor similaridade (ortográfica OU fonética) entre os elementos
    distintivos das duas marcas.

    Retorna None quando ao menos uma das marcas não possui elemento distintivo
    próprio (é composta apenas por termos descritivos) — nesse caso só há
    colidência se os nomes completos forem praticamente idênticos.

    Quando `ncl_a`/`ncl_b` são informados, aplica também o vocabulário
    descritivo específico da classe (minerado do corpus acumulado).
    """
    da = tokens_distintivos(nome_a, ncl_a)
    db = tokens_distintivos(nome_b, ncl_b)
    if not da or not db:
        return None
    return max(
        max(jaro_winkler(x, y), similaridade_fonetica(x, y))
        for x in da
        for y in db
    )
