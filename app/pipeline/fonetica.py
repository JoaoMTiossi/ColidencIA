"""
Camada 2 — Filtro fonético com blocking por token distintivo.

Estratégia de indexação:
  1. Código fonético de cada TOKEN DISTINTIVO da marca — resolve o problema
     de marcas onde o elemento relevante está no meio ou fim do nome:
     "INTER TOTAL" indexada sob "total" → encontra "TOTAL".
  2. Código fonético de cada TOKEN DESGASTADO (ELEMENTOS_DESGASTADOS) —
     marcas cujo único identificador é um termo fraco (TOP, MAX, VIP, MEGA).
  3. Código fonético do nome completo — fallback para siglas e variações
     ortográficas (Levenshtein-1).
  4. Código fonético do primeiro token do NÚCLEO MARCÁRIO — garante blocking
     position-independent quando o núcleo aparece em posições diferentes:
     "HOF locação de guindastes" e "Locação de guindastes HOF" → ambos
     indexados sob metaphone("hof") → encontram-se.

Normalização pré-indexação (normalizacao.py):
  - "M G" / "H.O.F" / "M. G." → colapso de siglas antes do blocking.

A busca usa match exato para tokens/núcleo e Levenshtein-1 para nome completo.
"""
from __future__ import annotations

from collections import defaultdict

from ..config import CLASSES_TRANSVERSAIS, COLLISIONS, ELEMENTOS_DESGASTADOS, THRESHOLD_FONETICO, classes_colidem
from ..utils.distintividade import tokens_distintivos
from ..utils.metaphone_ptbr import metaphone_ptbr
from ..utils.normalizacao import jaccard_bigramas, normalizar_base
from ..utils.similaridade import jaro_winkler, similaridade_fonetica, token_sort


_AFINIDADE_MIN_CLASSE: float = 0.60


def _classes_elegiveis(ncl: int) -> set[int]:
    """Retorna o conjunto de classes NCL elegíveis para comparação com ncl."""
    from .especificacao import _carregar_correlatas
    elegiveis: set[int] = {ncl}
    if ncl in CLASSES_TRANSVERSAIS or ncl == 0:
        return set(range(0, 46))
    correlatas = _carregar_correlatas()
    for (a, b), af in correlatas.items():
        if a == ncl and af >= _AFINIDADE_MIN_CLASSE:
            elegiveis.add(b)
    for cls in COLLISIONS.get(ncl, []):
        elegiveis.add(cls)
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


def _busca_exata(
    codigo: str,
    index: dict[tuple[int, str], list[dict]],
    classes: set[int],
) -> list[dict]:
    """Busca marcas no bucket exato de cada classe elegível."""
    resultado: list[dict] = []
    for cls in classes:
        resultado.extend(index.get((cls, codigo), []))
    return resultado


def _busca_com_vizinhos(
    codigo: str,
    index: dict[tuple[int, str], list[dict]],
    classes: set[int],
    chaves_por_classe: dict[int, list[str]],
) -> list[dict]:
    """Busca no bucket exato + buckets com Levenshtein-1 (tolerância a variações).

    Usa `chaves_por_classe` (pré-computado uma vez na indexação) para varrer
    apenas os códigos da classe corrente — sem isso, cada busca percorria
    TODAS as chaves do índice para cada classe elegível (O(classes × chaves)),
    o que degenerava em quase full-scan com carteiras grandes.
    """
    resultado: list[dict] = []
    for cls in classes:
        resultado.extend(index.get((cls, codigo), []))
        for k in chaves_por_classe.get(cls, ()):
            if k != codigo and _levenshtein_1(codigo, k):
                resultado.extend(index[(cls, k)])
    return resultado


def camada2(
    carteira: list[dict],
    rpi_restante: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Filtro fonético com blocking por token distintivo + desgastado + nome completo.

    Indexação da carteira:
      - Por cada token distintivo (código fonético completo, sem truncagem).
      - Por cada token desgastado (ELEMENTOS_DESGASTADOS) — cobre marcas cujo
        único identificador é um termo fraco: "TOP", "MAX", "VIP", "MEGA".
      - Por código fonético do nome completo (fallback, com Levenshtein-1).

    Busca para cada marca da RPI:
      - Tokens distintivos → busca exata no índice.
      - Tokens desgastados → busca exata no índice.
      - Código fonético do nome completo → busca com Levenshtein-1.
    """
    indice_fonetico: dict[tuple[int, str], list[dict]] = defaultdict(list)
    _buckets_ids: dict[tuple[int, str], set[int]] = defaultdict(set)
    # Índice invertido de bigramas: (ncl, bigrama) → marcas da carteira que o
    # contêm. Substitui a varredura completa de todas as marcas das classes
    # elegíveis (que degenerava em O(n×m) quando classe 35/transversal tornava
    # todas as classes elegíveis).
    indice_bigrama: dict[tuple[int, str], list[dict]] = defaultdict(list)

    def _indexar(ncl: int, codigo: str, marca: dict) -> None:
        if not codigo:
            return
        chave = (ncl, codigo)
        if id(marca) not in _buckets_ids[chave]:
            _buckets_ids[chave].add(id(marca))
            indice_fonetico[chave].append(marca)

    for marca in carteira:
        ncl = marca.get("ncl", 0)
        nome = marca.get("marca") or marca.get("nome_marca", "")

        # 1. Indexar por cada token distintivo (código fonético completo)
        for tok in tokens_distintivos(nome, ncl):
            cod_tok = metaphone_ptbr(tok)
            if cod_tok:
                _indexar(ncl, cod_tok, marca)

        # 2. Indexar por tokens desgastados — para marcas cujo único elemento
        #    de identidade é um termo desgastado ("TOP", "MAX", "VIP", "MEGA").
        for tok in normalizar_base(nome).split():
            if len(tok) >= 2 and tok in ELEMENTOS_DESGASTADOS:
                cod_tok = metaphone_ptbr(tok)
                if cod_tok:
                    _indexar(ncl, cod_tok, marca)

        # 3. Indexar pelo código do nome completo (fallback / siglas curtas)
        cod_full = marca.get("codigo_fonetico", "")
        if cod_full:
            _indexar(ncl, cod_full, marca)

        # 4. Indexar pelo código do núcleo marcário (position-independent).
        #    Garante que "HOF x" encontra "x HOF" mesmo quando o núcleo
        #    aparece em posições diferentes nos dois nomes.
        nucleo = marca.get("nucleo", "")
        if nucleo:
            first_tok = nucleo.split()[0]
            if len(first_tok) >= 2:
                cod_nuc = metaphone_ptbr(first_tok)
                if cod_nuc:
                    _indexar(ncl, cod_nuc, marca)

        # 5. Indexar pelo prefixo literal do núcleo distintivo (sem Metaphone).
        #    Reaproxima variações que o código fonético separa por descartar
        #    vogais não-iniciais (ex.: "NEXO" e "NEXORA" → ambas "nexo").
        prefixo = marca.get("prefixo_direto", "")
        if len(prefixo) >= 3:
            _indexar(ncl, f"_d:{prefixo}", marca)

        for bg in marca.get("bigrams_set", ()):
            indice_bigrama[(ncl, bg)].append(marca)

    # Chaves do índice fonético agrupadas por classe — pré-computado uma vez
    # para que _busca_com_vizinhos não varra o índice inteiro a cada chamada.
    chaves_por_classe: dict[int, list[str]] = defaultdict(list)
    for (cls, cod) in indice_fonetico:
        chaves_por_classe[cls].append(cod)

    candidatos: list[dict] = []

    for marca_rpi in rpi_restante:
        ncl_rpi = marca_rpi.get("ncl", 0)
        nome_rpi = marca_rpi.get("nome_marca", "")
        bg_rpi = marca_rpi.get("bigrams_set", set())
        classes_ok = _classes_elegiveis(ncl_rpi)

        # 1. Busca por tokens distintivos da marca RPI (exata — sem Levenshtein)
        cands_tokens: list[dict] = []
        for tok in tokens_distintivos(nome_rpi, ncl_rpi):
            cod = metaphone_ptbr(tok)
            if cod:
                cands_tokens.extend(_busca_exata(cod, indice_fonetico, classes_ok))

        # 2. Busca por tokens desgastados da marca RPI (exata)
        cands_desgastados: list[dict] = []
        for tok in normalizar_base(nome_rpi).split():
            if len(tok) >= 2 and tok in ELEMENTOS_DESGASTADOS:
                cod = metaphone_ptbr(tok)
                if cod:
                    cands_desgastados.extend(_busca_exata(cod, indice_fonetico, classes_ok))

        # 2b. Busca pelo núcleo da marca RPI (position-independent)
        cands_nucleo: list[dict] = []
        nucleo_rpi_str = marca_rpi.get("nucleo", "")
        if nucleo_rpi_str:
            first_tok_rpi = nucleo_rpi_str.split()[0]
            if len(first_tok_rpi) >= 2:
                cod = metaphone_ptbr(first_tok_rpi)
                if cod:
                    cands_nucleo.extend(_busca_exata(cod, indice_fonetico, classes_ok))

        # 2c. Busca pelo prefixo literal do núcleo distintivo (sem Metaphone)
        cands_direto: list[dict] = []
        prefixo_rpi = marca_rpi.get("prefixo_direto", "")
        if len(prefixo_rpi) >= 3:
            cands_direto = _busca_exata(f"_d:{prefixo_rpi}", indice_fonetico, classes_ok)

        # 3. Busca pelo código do nome completo (com Levenshtein-1)
        cod_rpi = marca_rpi.get("codigo_fonetico", "")
        cands_full = (
            _busca_com_vizinhos(cod_rpi, indice_fonetico, classes_ok, chaves_por_classe)
            if cod_rpi else []
        )

        # 4. Blocking por bigramas via índice invertido. Acumula a contagem de
        #    bigramas compartilhados por marca e só calcula o Jaccard exato para
        #    quem atinge o mínimo necessário: J = i/(a+b-i) ≥ 0.3 com b ≥ i
        #    implica i ≥ 0.3·a — condição necessária usada como pré-filtro.
        cands_bigrama: list[dict] = []
        if bg_rpi:
            contagem: dict[int, list] = {}  # id(marca) → [marca, n_compartilhados]
            for cls in classes_ok:
                for bg in bg_rpi:
                    for marca in indice_bigrama.get((cls, bg), ()):
                        mid = id(marca)
                        ent = contagem.get(mid)
                        if ent is None:
                            contagem[mid] = [marca, 1]
                        else:
                            ent[1] += 1
            min_inter = 0.3 * len(bg_rpi)
            for marca, inter in contagem.values():
                if inter >= min_inter:
                    bg_cart = marca.get("bigrams_set", set())
                    union = len(bg_rpi | bg_cart)
                    if union > 0 and inter / union >= 0.3:
                        cands_bigrama.append(marca)

        # Unir candidatos sem duplicatas
        todos_ids: set[int] = set()
        todos_candidatos: list[dict] = []
        for m in cands_tokens + cands_desgastados + cands_nucleo + cands_direto + cands_full + cands_bigrama:
            mid = id(m)
            if mid not in todos_ids:
                todos_ids.add(mid)
                todos_candidatos.append(m)

        # Calcular score e filtrar pelo threshold
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
    ncl_a = marca_base.get("ncl", 0)
    ncl_b = marca_rpi.get("ncl", 0)

    # Quando o primeiro token distintivo de ambas coincide, ele É o elemento
    # primário da marca (ex: "MS" em "MS MARCOS SOUZA" e "INSTITUTO MS",
    # "LK" em "LK IMPORT.CG" e "LK STREET URBAN").
    # O score do par de tokens lidera — nome completo divergente não penaliza.
    toks_a = tokens_distintivos(nome_a, ncl_a)
    toks_b = tokens_distintivos(nome_b, ncl_b)
    score_primeiro_tok = 0.0
    if toks_a and toks_b:
        sim_primeiro = jaro_winkler(toks_a[0], toks_b[0])
        if sim_primeiro >= 0.92:
            score_primeiro_tok = sim_primeiro

    # Token containment — vigilância marcária: se o token dominante de uma
    # marca aparece verbatim (ou quase) em qualquer posição da outra, isso é
    # um hit independente da similaridade do nome completo.
    # Captura: "SUN" ⊂ "Capri Sun", "Cuidar" ⊂ "adoro cuidar", etc.
    score_containment = 0.0
    if toks_a and toks_b:
        set_a = set(toks_a)
        set_b = set(toks_b)
        # Token compartilhado exato
        shared = set_a & set_b
        if shared:
            score_containment = 0.72
        else:
            # Token de uma quase-idêntico a token da outra
            for t_a in toks_a:
                for t_b in toks_b:
                    if jaro_winkler(t_a, t_b) >= 0.92:
                        score_containment = 0.70
                        break
                if score_containment:
                    break
        # Equivalência fonética: mesmo código metaphone = cópia fonética
        # (ex.: "kmey" e "kemei" → ambos "KM"; JW=0.67 passaria pelo gate).
        if not score_containment:
            for t_a in toks_a:
                cod_a = metaphone_ptbr(t_a)
                if cod_a:
                    for t_b in toks_b:
                        if cod_a == metaphone_ptbr(t_b):
                            score_containment = max(score_containment, 0.72)
                            break
                    if score_containment:
                        break

    # Siglas e nomes curtos — usar max(ratio, jaro_winkler)
    if (marca_base.get("is_sigla") or marca_rpi.get("is_sigla")
            or len(nome_a) <= 4 or len(nome_b) <= 4):
        from rapidfuzz import fuzz
        ratio = fuzz.ratio(nome_a, nome_b) / 100.0
        jw = jaro_winkler(nome_a, nome_b)
        return min(1.0, max(ratio, jw, score_primeiro_tok, score_containment))

    jw_nome = jaro_winkler(nome_a, nome_b)
    jw_nucleo = jaro_winkler(nucleo_a, nucleo_b) * 1.1
    jac = jaccard_bigramas(nome_a, nome_b)

    return min(1.0, max(jw_nome, jw_nucleo, jac, score_primeiro_tok, score_containment))


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
        "score_spec": 0.0,
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
        "apresentacao_base": marca_base.get("apresentacao", ""),
        "apresentacao_rpi": marca_rpi.get("apresentacao", ""),
        "is_nome_proprio_base": bool(marca_base.get("is_nome_proprio")),
        "is_nome_proprio_rpi": bool(marca_rpi.get("is_nome_proprio")),
    }
