"""
Camada 0 — Pré-processamento.
Gera campos derivados para cada marca antes das comparações.
"""
from __future__ import annotations

from ..utils.metaphone_ptbr import metaphone_ptbr
from ..utils.normalizacao import bigramas, normalizar_base
from ..utils.nucleo_marcario import (
    extrair_nucleo,
    is_desgastado,
    is_marca_generica,
    is_nome_proprio,
    is_sigla,
)


def preprocessar(marca: dict) -> dict:
    """
    Recebe um dict com pelo menos os campos:
        marca (str), ncl (int), especificacao (str), apresentacao (str)

    Adiciona campos derivados:
        nome_normalizado, nucleo, codigo_fonetico, bigrams_set,
        is_sigla, is_nome_proprio, is_marca_generica, is_desgastado
    """
    nome = marca.get("marca") or marca.get("nome_marca") or ""
    nome_norm = normalizar_base(nome)
    nucleo = extrair_nucleo(nome)

    resultado = dict(marca)
    resultado["nome_normalizado"] = nome_norm
    resultado["nucleo"] = nucleo
    resultado["codigo_fonetico"] = metaphone_ptbr(nome_norm)
    resultado["bigrams_set"] = bigramas(nome)
    resultado["is_sigla"] = is_sigla(nome)
    resultado["is_nome_proprio"] = is_nome_proprio(nome)
    resultado["is_marca_generica"] = is_marca_generica(nucleo)
    resultado["is_desgastado"] = is_desgastado(nome)
    return resultado


def preprocessar_lote(marcas: list[dict]) -> list[dict]:
    """Pré-processa uma lista de marcas."""
    return [preprocessar(m) for m in marcas]
