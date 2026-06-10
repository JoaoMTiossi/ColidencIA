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
    # Tokens base: sem stopwords, sem numéricos puros, len>=2
    base = [
        t for t in normalizar_base(nome).split()
        if len(t) >= 2 and not t.isdigit() and t not in _STOP
    ]
    dist = [t for t in base if t not in vocab and t not in vocab_ncl]

    if not dist and base:
        # Proteção 1: marca de um único token (ex: BRASA, SUN, EGO, CACAU).
        # O token não pode ser "descritivo de si mesmo".
        if len(base) == 1:
            return base

        # Proteção 2: os tokens que passaram o filtro GERAL (vocab estático)
        # foram removidos apenas pelo vocab de CORPUS específico da classe.
        # O corpus é ruidoso — "brasa" aparece em muitos restaurantes mas ainda
        # é o elemento marcário de "BRASA NCL30" comparado a "BRASA KING NCL43".
        # Restaurar os tokens que sobreviveram ao filtro geral (para que
        # elementos distintivos não sejam apagados por frequência sectorial).
        after_general = [t for t in base if t not in vocab]
        if after_general:
            return after_general

    return dist


def _token_dominante(tokens: list[str]) -> str:
    """Token mais representativo: o mais longo com len>=4, ou o mais longo disponível."""
    longos = [t for t in tokens if len(t) >= 4]
    return max(longos, key=len) if longos else max(tokens, key=len)


def match_distintivo(
    nome_a: str,
    nome_b: str,
    ncl_a: int | None = None,
    ncl_b: int | None = None,
) -> float | None:
    """
    Melhor similaridade entre os tokens distintivos de duas marcas.

    Estratégia em duas camadas:
      1. Compara o PAR MAIS SIMILAR entre todos os tokens de cada lista —
         captura casos como "CAPRICHO" vs "CAPRICCHE" onde o token único de
         cada marca é exatamente o elemento marcário principal.
      2. Penaliza se o par mais similar não inclui o TOKEN DOMINANTE (mais
         longo) de pelo menos uma das marcas — evita inflação por tokens
         curtos/descritivos residuais que escaparam do vocabulário.

    Retorna None quando ao menos uma das marcas não possui elemento distintivo
    próprio (é composta apenas por termos descritivos).

    Quando `ncl_a`/`ncl_b` são informados, aplica também o vocabulário
    descritivo específico da classe (minerado do corpus acumulado).
    """
    da = tokens_distintivos(nome_a, ncl_a)
    db = tokens_distintivos(nome_b, ncl_b)
    if not da or not db:
        return None

    # Melhor par por similaridade (ortográfica ou fonética)
    best = 0.0
    best_a = best_b = ""
    for x in da:
        for y in db:
            s = max(jaro_winkler(x, y), similaridade_fonetica(x, y))
            if s > best:
                best, best_a, best_b = s, x, y

    # Penaliza quando o par de maior similaridade não inclui o token dominante
    # de NENHUMA das duas marcas — indica que tokens secundários/residuais
    # estão governando o score enquanto os elementos principais divergem.
    pa = _token_dominante(da)
    pb = _token_dominante(db)
    # Exact token match (e.g. sigla "jb"=="jb") is always treated as dominant —
    # the shared element IS the mark, regardless of which token is longest.
    dominante_incluido = (best_a == best_b) or (best_a == pa or best_b == pb)
    if not dominante_incluido:
        # Calcular score do par dominante como alternativa
        score_dom = max(jaro_winkler(pa, pb), similaridade_fonetica(pa, pb))
        # Retorna o maior entre o melhor par e o par dominante,
        # mas penaliza o melhor par não-dominante (75% do valor)
        best = max(score_dom, best * 0.75)

    return best
