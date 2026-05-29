"""
Camada 2 — Filtro fonético com blocking.
Usa blocking por código fonético + bigramas para reduzir comparações.
Indexa a carteira por (ncl, prefixo_fonético) para comparar somente dentro
das classes elegíveis de cada marca da RPI.
"""
from __future__ import annotations

from collections import defaultdict

from ..config import CLASSES_TRANSVERSAIS, COLLISIONS, THRESHOLD_FONETICO, classes_colidem
from ..utils.normalizacao import jaccard_bigramas
from ..utils.similaridade import jaro_winkler, similaridade_fonetica, token_sort


# Threshold mínimo de afinidade para que duas classes sejam comparadas
_AFINIDADE_MIN_CLASSE: float = 0.50

def _classes_elegiveis(ncl: int) -> set[int]:
    """Retorna o conjunto de classes NCL elegíveis para comparação com ncl.

    Inclui a própria classe + todas com afinidade >= _AFINIDADE_MIN_CLASSE
    na tabela de correlatas + as classes da matriz COLLISIONS como fallback
    (afinidade implícita 0.60 > threshold 0.50) + as classes transversais
    (35), que correlacionam com todas.
    """
    from .especificacao import _carregar_correlatas
    elegiveis: set[int] = {ncl}
    # Classe transversal ou não-classificada (NCL=0): elegível contra todas (0..45)
    if ncl in CLASSES_TRANSVERSAIS or ncl == 0:
        return set(range(0, 46))
    correlatas = _carregar_correlatas()
    for (a, b), af in correlatas.items():
        if a == ncl and af >= _AFINIDADE_MIN_CLASSE:
            elegiveis.add(b)
    for cls in COLLISIONS.get(ncl, []):
        elegiveis.add(cls)
    # Qualquer classe é elegível contra as transversais e contra NCL=0
    elegiveis |= CLASSES_TRANSVERSAIS
    elegiveis.add(0)
    return elegiveis


def _levenshtein_1(a: str, b: str) -> bool:
    """Retorna True se edit distance entre a e b é ≤ 1."""
    if abs(len(a) - len(b)) > 1:
        return False
    if a == b:
        return True
    diffs = sum(x != y for x, y in zip(a, b))
    if len(a) == len(b):
        return diffs <= 1
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(longer)):
        if longer[:i] + longer[i + 1:] == shorter:
            return True
    return False


def _buckets_vizinhos(
    codigo: str,
    index: dict[tuple[int, str], list[dict]],
    classes: set[int],
) -> list[dict]:
    """Retorna marcas no bucket exato + buckets com edit distance 1, filtrados por classes."""
    prefixo = codigo[:4]
    candidatos: list[dict] = []
    for cls in classes:
        chave_exata = (cls, prefixo)
        candidatos.extend(index.get(chave_exata, []))
        for (c, k) in list(index.keys()):
            if c == cls and k != prefixo and _levenshtein_1(prefixo, k[:4] if len(k) >= 4 else k):
                candidatos.extend(index[(c, k)])
    return candidatos


def camada2(
    carteira: list[dict],
    rpi_restante: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Filtro fonético com blocking por classe NCL elegível.

    O índice fonético é keyed por (ncl, prefixo_fonético) — para cada marca
    da RPI só são consultadas as entradas cujas classes são elegíveis
    (mesma classe + correlatas >= 0.50 + COLLISIONS fallback).

    Retorna:
        (candidatos_para_camada3, rpi_descartado)
    """
    # Construir índice fonético por (ncl, prefixo).
    # Indexa cada marca tanto pelo prefixo do NOME COMPLETO quanto pelo
    # prefixo do NÚCLEO distintivo — assim "NEXO" e "NEXORA TRADE TECH"
    # caem no mesmo bucket pelo núcleo, mesmo que o código do nome completo
    # divirja. Usa um set de ids para não duplicar a marca no mesmo bucket.
    indice_fonetico: dict[tuple[int, str], list[dict]] = defaultdict(list)
    _buckets_ids: dict[tuple[int, str], set[int]] = defaultdict(set)
    # Índice por (ncl, bigrams_frozenset) não é viável — usar lista por ncl para bigramas
    indice_bigrama: dict[int, list[dict]] = defaultdict(list)

    def _indexar(ncl: int, prefixo: str, marca: dict) -> None:
        if not prefixo:
            return
        chave = (ncl, prefixo)
        if id(marca) not in _buckets_ids[chave]:
            _buckets_ids[chave].add(id(marca))
            indice_fonetico[chave].append(marca)

    for marca in carteira:
        ncl = marca.get("ncl", 0)
        cod = marca.get("codigo_fonetico", "")
        cod_nuc = marca.get("codigo_fonetico_nucleo", "")
        _indexar(ncl, cod[:4] if cod else "", marca)
        _indexar(ncl, cod_nuc[:4] if cod_nuc else "", marca)
        if marca.get("bigrams_set"):
            indice_bigrama[ncl].append(marca)

    candidatos: list[dict] = []

    for marca_rpi in rpi_restante:
        ncl_rpi = marca_rpi.get("ncl", 0)
        cod_rpi = marca_rpi.get("codigo_fonetico", "")
        bg_rpi = marca_rpi.get("bigrams_set", set())

        cod_nucleo_rpi = marca_rpi.get("codigo_fonetico_nucleo", "")

        classes_ok = _classes_elegiveis(ncl_rpi)

        # Blocking fonético filtrado por classes elegíveis — consulta tanto
        # pelo código do nome completo quanto pelo código do núcleo distintivo.
        cands_foneticos = _buckets_vizinhos(cod_rpi, indice_fonetico, classes_ok)
        if cod_nucleo_rpi and cod_nucleo_rpi[:4] != cod_rpi[:4]:
            cands_foneticos = cands_foneticos + _buckets_vizinhos(
                cod_nucleo_rpi, indice_fonetico, classes_ok
            )

        # Blocking por bigramas, somente em classes elegíveis
        cands_por_bigrama: list[dict] = []
        if bg_rpi:
            for cls in classes_ok:
                for marca in indice_bigrama.get(cls, []):
                    bg_cart = marca.get("bigrams_set", set())
                    if bg_cart:
                        inter = len(bg_rpi & bg_cart)
                        union = len(bg_rpi | bg_cart)
                        if union > 0 and inter / union >= 0.3:
                            cands_por_bigrama.append(marca)

        # Unir candidatos (sem duplicatas)
        todos_ids: set[int] = set()
        todos_candidatos: list[dict] = []
        for m in cands_foneticos + cands_por_bigrama:
            mid = id(m)
            if mid not in todos_ids:
                todos_ids.add(mid)
                todos_candidatos.append(m)

        # Calcular score dentro dos candidatos
        for marca_base in todos_candidatos:
            score = _score_fonetico(marca_base, marca_rpi)
            if score >= THRESHOLD_FONETICO:
                col = classes_colidem(marca_base.get("ncl", 0), ncl_rpi)
                candidatos.append(_criar_candidato(marca_base, marca_rpi, score, col))

    return candidatos, []


def _score_fonetico(marca_base: dict, marca_rpi: dict) -> float:
    """Calcula score combinado para o filtro fonético."""
    nome_a = marca_base.get("nome_normalizado", "")
    nome_b = marca_rpi.get("nome_normalizado", "")
    nucleo_a = marca_base.get("nucleo", "")
    nucleo_b = marca_rpi.get("nucleo", "")

    # Casos especiais: siglas e nomes curtos — usar max(ratio, jaro_winkler)
    if (marca_base.get("is_sigla") or marca_rpi.get("is_sigla")
            or len(nome_a) <= 4 or len(nome_b) <= 4):
        from rapidfuzz import fuzz
        ratio = fuzz.ratio(nome_a, nome_b) / 100.0
        jw = jaro_winkler(nome_a, nome_b)
        return max(ratio, jw)

    jw_nome = jaro_winkler(nome_a, nome_b)
    jw_nucleo = jaro_winkler(nucleo_a, nucleo_b) * 1.1  # bonus por nucleo
    jac = jaccard_bigramas(nome_a, nome_b)

    return min(1.0, max(jw_nome, jw_nucleo, jac))


def _criar_candidato(
    marca_base: dict,
    marca_rpi: dict,
    score_fonetico: float,
    col: bool,
) -> dict:
    return {
        "processo_base": marca_base.get("processo", ""),
        "marca_base": marca_base.get("marca") or marca_base.get("nome_marca", ""),
        "ncl_base": marca_base.get("ncl", 0),
        "ncl_versao_base": marca_base.get("ncl_versao", 12),
        "spec_base": marca_base.get("especificacao", ""),
        "nucleo_base": marca_base.get("nucleo", ""),
        "titular_base": marca_base.get("titular", ""),
        "marca_rpi": marca_rpi.get("nome_marca", ""),
        "ncl_rpi": marca_rpi.get("ncl", 0),
        "spec_rpi": marca_rpi.get("especificacao", ""),
        "nucleo_rpi": marca_rpi.get("nucleo", ""),
        "processo_rpi": marca_rpi.get("processo", ""),
        "titular_rpi": marca_rpi.get("titular", ""),
        "despacho_codigo": marca_rpi.get("despacho_codigo", ""),
        "despacho_nome": marca_rpi.get("despacho_nome", ""),
        "tipo_acao": marca_rpi.get("tipo_acao", ""),
        "score_nome": round(
            jaro_winkler(
                marca_base.get("nome_normalizado", ""),
                marca_rpi.get("nome_normalizado", ""),
            ),
            4,
        ),
        "score_fonetico": round(score_fonetico, 4),
        "score_spec": 0.0,  # será calculado na camada 3
        "score_nucleo": round(
            jaro_winkler(
                marca_base.get("nucleo_distintivo") or marca_base.get("nucleo", ""),
                marca_rpi.get("nucleo_distintivo") or marca_rpi.get("nucleo", ""),
            ),
            4,
        ),
        "score_ia": None,
        "camada_deteccao": 2,
        "classificacao": None,
        "classes_colidem_flag": col,
        "is_sigla": bool(marca_base.get("is_sigla") or marca_rpi.get("is_sigla")),
        "is_desgastado": bool(marca_base.get("is_desgastado") or marca_rpi.get("is_desgastado")),
        "is_marca_generica": bool(marca_base.get("is_marca_generica") or marca_rpi.get("is_marca_generica")),
        "nucleo_base_generico": bool(marca_base.get("is_marca_generica")),
        "nucleo_rpi_generico": bool(marca_rpi.get("is_marca_generica")),
        "nucleo_distintivo_base": marca_base.get("nucleo_distintivo", ""),
        "nucleo_distintivo_rpi": marca_rpi.get("nucleo_distintivo", ""),
    }
