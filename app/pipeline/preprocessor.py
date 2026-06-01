"""
Camada 0 — Pré-processamento.
Gera campos derivados para cada marca antes das comparações.
"""
from __future__ import annotations

import re

from ..utils.metaphone_ptbr import metaphone_ptbr
from ..utils.normalizacao import bigramas, normalizar_base
from ..utils.nucleo_marcario import (
    extrair_nucleo,
    extrair_nucleo_distintivo,
    is_desgastado,
    is_marca_generica,
    is_nome_proprio,
    is_sigla,
)

# Sufixos de forma jurídica que aparecem no nome bruto e disparam falso positivo
# no padrão de sigla pontilhada (_RE_SIGLA_SEPARADA capta "S.A." como sigla).
_RE_FORMA_JURIDICA = re.compile(
    r"\s+(?:S\.?/?A\.?|LTDA?\.?|ME\.?|EPP\.?|EIRELI\.?|S\.?S\.?|MEI\.?)"
    r"(?:\s+|$)",
    re.IGNORECASE,
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
    considerar_dobra = bool(marca.get("considerar_dobra", False))
    nome_norm = normalizar_base(nome, considerar_dobra)
    nucleo = extrair_nucleo(nome)
    nucleo_distintivo = extrair_nucleo_distintivo(nucleo)

    resultado = dict(marca)
    resultado["nome_normalizado"] = nome_norm
    resultado["nucleo"] = nucleo
    resultado["nucleo_distintivo"] = nucleo_distintivo
    resultado["codigo_fonetico"] = metaphone_ptbr(nome_norm)
    # Código fonético do núcleo distintivo — usado no blocking para capturar
    # marcas "núcleo + palavras descritivas" (ex.: "NEXO" vs "NEXORA TRADE TECH"),
    # cujo código do nome completo diverge mas o do núcleo é próximo.
    resultado["codigo_fonetico_nucleo"] = metaphone_ptbr(nucleo_distintivo or nucleo)
    # Prefixo literal do elemento distintivo (sem passar pelo Metaphone) — índice
    # de blocking paralelo. O Metaphone descarta vogais não-iniciais e separa
    # "NEXO"(NX) de "NEXORA"(NXR); o prefixo literal as reaproxima (ambas "nexo").
    base_prefixo = (nucleo_distintivo or nucleo or nome_norm).replace(" ", "")
    resultado["prefixo_direto"] = base_prefixo[:4]
    resultado["bigrams_set"] = bigramas(nome)
    # Sigla pelo nome (sem forma jurídica) OU pelo núcleo distintivo.
    # A forma jurídica (S.A., LTDA) é removida do nome bruto antes do teste —
    # "S.A." dispararia falso positivo no padrão de sigla pontilhada.
    nome_sem_fj = _RE_FORMA_JURIDICA.sub(" ", nome).strip()
    resultado["is_sigla"] = is_sigla(nome_sem_fj) or is_sigla(nucleo_distintivo or nucleo)
    resultado["is_nome_proprio"] = is_nome_proprio(resultado)
    resultado["is_marca_generica"] = is_marca_generica(nucleo)
    resultado["is_desgastado"] = is_desgastado(nome)
    return resultado


def preprocessar_lote(marcas: list[dict]) -> list[dict]:
    """Pré-processa uma lista de marcas."""
    return [preprocessar(m) for m in marcas]
