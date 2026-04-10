"""
Camada 2 — Filtro fonético com blocking.
Usa blocking por código fonético + bigramas para reduzir comparações.
"""
from __future__ import annotations

from ..config import THRESHOLD_FONETICO, classes_colidem
from ..utils.normalizacao import jaccard_bigramas
from ..utils.similaridade import jaro_winkler, similaridade_fonetica, token_sort


def _levenshtein_1(a: str, b: str) -> bool:
    """Retorna True se edit distance entre a e b é ≤ 1."""
    if abs(len(a) - len(b)) > 1:
        return False
    if a == b:
        return True
    # Verificar se diferem em exatamente 1 char
    diffs = sum(x != y for x, y in zip(a, b))
    if len(a) == len(b):
        return diffs <= 1
    # Uma é maior — verificar se uma contém a outra
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(longer)):
        if longer[:i] + longer[i + 1:] == shorter:
            return True
    return False


def _buckets_vizinhos(codigo: str, index: dict[str, list[dict]]) -> list[dict]:
    """Retorna marcas no bucket exato + buckets com edit distance 1 no prefixo fonético."""
    prefixo = codigo[:4]
    candidatos: list[dict] = list(index.get(prefixo, []))

    # Buckets vizinhos (primeiros 4 chars do código com 1 edição)
    for chave in list(index.keys()):
        if chave != prefixo and _levenshtein_1(prefixo, chave[:4] if len(chave) >= 4 else chave):
            candidatos.extend(index[chave])

    return candidatos


def camada2(
    carteira: list[dict],
    rpi_restante: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Filtro fonético com blocking.

    Retorna:
        (candidatos_para_camada3, rpi_descartado)
    """
    # Construir índice fonético da carteira (chave: primeiros 4 chars do metaphone)
    indice_fonetico: dict[str, list[dict]] = {}
    for marca in carteira:
        cod = marca.get("codigo_fonetico", "")
        prefixo = cod[:4] if cod else ""
        indice_fonetico.setdefault(prefixo, []).append(marca)

    # Construir índice invertido de bigramas para blocking rápido O(1) por bigrama
    # Em vez de comparar cada RPI com todas as 49k marcas, busca só as que
    # compartilham bigramas (evita O(n×m) = 392M iterações Python)
    indice_bigrama: dict[str, set[int]] = {}  # bigrama → set de índices na carteira
    for idx, marca in enumerate(carteira):
        for bg in (marca.get("bigrams_set") or set()):
            indice_bigrama.setdefault(bg, set()).add(idx)

    candidatos: list[dict] = []

    for marca_rpi in rpi_restante:
        cod_rpi = marca_rpi.get("codigo_fonetico", "")
        bg_rpi = marca_rpi.get("bigrams_set") or set()

        # Obter candidatos via blocking fonético
        cands_foneticos = _buckets_vizinhos(cod_rpi, indice_fonetico)

        # Blocking por bigramas via índice invertido — O(|bigramas_rpi|) não O(n)
        cands_por_bigrama: list[dict] = []
        if bg_rpi:
            # Contar quantos bigramas em comum cada marca da carteira tem
            contagem: dict[int, int] = {}
            for bg in bg_rpi:
                for idx in indice_bigrama.get(bg, set()):
                    contagem[idx] = contagem.get(idx, 0) + 1

            denom_rpi = len(bg_rpi)
            for idx, inter in contagem.items():
                marca = carteira[idx]
                bg_cart = marca.get("bigrams_set") or set()
                union = denom_rpi + len(bg_cart) - inter
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
                col = classes_colidem(marca_base.get("ncl", 0), marca_rpi.get("ncl", 0))
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
        "marca_base": marca_base.get("marca") or marca_base.get("nome_marca", ""),
        "ncl_base": marca_base.get("ncl", 0),
        "spec_base": marca_base.get("especificacao", ""),
        "nucleo_base": marca_base.get("nucleo", ""),
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
                marca_base.get("nucleo", ""),
                marca_rpi.get("nucleo", ""),
            ),
            4,
        ),
        "score_ia": None,
        "camada_deteccao": 2,
        "classificacao": None,
        "classes_colidem_flag": col,
        "is_sigla": marca_rpi.get("is_sigla", False),
        "is_desgastado": marca_rpi.get("is_desgastado", False),
    }
