"""
Orquestrador do pipeline de colidência (Camadas 0–5).
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from typing import Callable

from ..config import DESPACHOS_OPOSICAO, DESPACHOS_PAN
from ..parsers.parse_excel import parse_excel
from ..parsers.parse_xml import parse_rpi_xml
from .fonetica import camada2
from .ia_refinamento import camada5
from .nome_identico import camada1
from .preprocessor import preprocessar_lote
from .scoring import camada4
from .especificacao import camada3

logger = logging.getLogger(__name__)

_RE_PARENTESES = re.compile(r'\([^)]*\)')
_RE_SUFIXOS = re.compile(
    r'\b(ltda|me|epp|eireli|s/?a|ss|mei|inc|llc|corp|sa|cia|'
    r'sociedade anonima|industria|comercio|servicos|participacoes|'
    r'holding|grupo)\b',
    re.IGNORECASE,
)
_RE_NAO_ALFA = re.compile(r'[^a-z\s]')   # remove dígitos (CPF/CNPJ) e pontuação
_RE_ESPACOS  = re.compile(r'\s{2,}')


def _normalizar_titular(t: str) -> str:
    """Normaliza nome do titular para comparação: sem parênteses, sem acento, sem sufixos jurídicos."""
    t = _RE_PARENTESES.sub(' ', t)          # remove (BR/SP), (CPF), etc.
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = _RE_SUFIXOS.sub(' ', t)
    t = _RE_NAO_ALFA.sub(' ', t)            # remove dígitos e pontuação restante
    t = _RE_ESPACOS.sub(' ', t).strip()
    return t


def executar_pipeline(
    path_carteira: str,
    path_rpi: str,
    despachos_selecionados: list[str] | None = None,
    progress_cb: Callable[[str, int], None] | None = None,
    usar_ia: bool = True,
) -> dict:
    """
    Executa o pipeline completo de colidência.

    Parâmetros:
        path_carteira: caminho para o Excel da carteira
        path_rpi: caminho para o XML da RPI
        despachos_selecionados: lista de códigos de despacho a considerar
                                (None = todos os relevantes)
        progress_cb: callback(mensagem: str, pct: int) para atualizar progresso
        usar_ia: se True e OPENAI_API_KEY configurada, executa camada 5

    Retorna dict com:
        resultados, stats, custo_ia_usd, tempo_seg
    """
    t0 = time.time()

    def _progress(msg: str, pct: int = 0) -> None:
        logger.info("[%d%%] %s", pct, msg)
        if progress_cb:
            progress_cb(msg, pct)

    # -----------------------------------------------------------------------
    # Camada 0 — Carregar e pré-processar
    # -----------------------------------------------------------------------
    _progress("Carregando carteira de clientes...", 5)
    carteira_raw = parse_excel(path_carteira)
    _progress(f"Carteira carregada: {len(carteira_raw)} registros", 10)

    # Índices da carteira para filtros "RPI é cliente"
    processos_carteira: set[str] = {
        str(m.get("processo", "")).strip()
        for m in carteira_raw
        if str(m.get("processo", "")).strip()
    }
    titulares_carteira_norm: set[str] = {
        _normalizar_titular(m.get("titular", ""))
        for m in carteira_raw
        if _normalizar_titular(m.get("titular", ""))
    }
    titulares_carteira_lista: list[str] = list(titulares_carteira_norm)

    carteira = preprocessar_lote(carteira_raw)

    _progress("Carregando RPI...", 15)
    rpi_raw, rpi_numero, rpi_data = parse_rpi_xml(path_rpi)

    # Pré-corte: remover da RPI marcas cujo processo já está na carteira
    # (publicações/republicações da própria marca do cliente — sem colidência possível).
    total_rpi_bruto = len(rpi_raw)
    rpi_raw = [
        r for r in rpi_raw
        if str(r.get("processo", "")).strip() not in processos_carteira
    ]
    removidos_processo = total_rpi_bruto - len(rpi_raw)
    if removidos_processo:
        _progress(
            f"Pré-filtro: {removidos_processo} marca(s) da RPI removida(s) "
            f"— processo já consta na carteira",
            17,
        )

    # Filtrar por despachos selecionados
    if despachos_selecionados:
        rpi_raw = [r for r in rpi_raw if r["despacho_codigo"] in despachos_selecionados]

    total_rpi_oposicao = sum(1 for r in rpi_raw if r["despacho_codigo"] in DESPACHOS_OPOSICAO)
    total_rpi_pan = sum(1 for r in rpi_raw if r["despacho_codigo"] in DESPACHOS_PAN)

    _progress(f"RPI {rpi_numero} ({rpi_data}): {len(rpi_raw)} marcas filtradas", 20)
    rpi = preprocessar_lote(rpi_raw)

    # -----------------------------------------------------------------------
    # Corpus de vocabulário — coleta frequência de tokens por classe NCL
    # Usa TODAS as marcas (não só colidências) para estatística não-enviesada.
    # -----------------------------------------------------------------------
    from collections import Counter as _Counter
    _corpus_termos: _Counter[tuple[int, str]] = _Counter()
    _corpus_classes: _Counter[int] = _Counter()
    for _m in carteira + rpi:
        _ncl = _m.get("ncl", 0)
        if _ncl <= 0:
            continue
        _toks = set(t for t in (_m.get("nome_normalizado", "") or "").split() if len(t) >= 3)
        for _tok in _toks:
            _corpus_termos[(_ncl, _tok)] += 1
        _corpus_classes[_ncl] += 1

    # -----------------------------------------------------------------------
    # Camada 1 — Nome idêntico
    # -----------------------------------------------------------------------
    _progress("Camada 1: Verificando nomes idênticos...", 30)
    alertas_c1_raw, rpi_restante = camada1(carteira, rpi)
    _progress(f"Camada 1: {len(alertas_c1_raw)} marcas idênticas detectadas", 32)

    # Filtro de afinidade NCL/especificação: marcas idênticas só viram
    # alerta se a NCL/spec forem concorrentes. "MISTER X" classe 25 contra
    # "MISTER X" classe 7 (máquinas) não deve gerar colidência.
    if alertas_c1_raw:
        alertas_c1 = camada3(alertas_c1_raw)
        for a in alertas_c1:
            a["camada_deteccao"] = 1  # camada3 sobrescreve; restaurar origem
        removidos_c1 = len(alertas_c1_raw) - len(alertas_c1)
        if removidos_c1:
            _progress(
                f"Camada 1: {removidos_c1} marca(s) idêntica(s) removida(s) "
                f"— NCL/especificação não concorrente",
                34,
            )
    else:
        alertas_c1 = alertas_c1_raw
    _progress(f"Camada 1: {len(alertas_c1)} colidências confirmadas", 35)

    # -----------------------------------------------------------------------
    # Camada 2 — Filtro fonético
    # -----------------------------------------------------------------------
    _progress(f"Camada 2: Filtro fonético ({len(rpi_restante)} marcas restantes)...", 40)
    candidatos_c2, _ = camada2(carteira, rpi_restante)
    _progress(f"Camada 2: {len(candidatos_c2)} candidatos após filtro fonético", 50)

    # -----------------------------------------------------------------------
    # Camada 3 — Filtro de especificação
    # -----------------------------------------------------------------------
    _progress("Camada 3: Filtro de especificação...", 55)
    candidatos_c3 = camada3(candidatos_c2)
    _progress(f"Camada 3: {len(candidatos_c3)} candidatos com afinidade suficiente", 60)

    # -----------------------------------------------------------------------
    # Camada 4 — Scoring composto
    # -----------------------------------------------------------------------
    _progress("Camada 4: Calculando scores...", 65)
    todos_candidatos = candidatos_c3  # alertas da camada 1 já têm score
    scored_c4 = camada4(todos_candidatos)
    _progress(f"Camada 4: {len(scored_c4)} pares acima do threshold", 70)

    # Unir resultados da camada 1 com os da camada 4
    todos_resultados = alertas_c1 + scored_c4

    # -----------------------------------------------------------------------
    # Camada 5 — Refinamento IA
    # -----------------------------------------------------------------------
    custo_ia = 0.0
    if usar_ia and todos_resultados:
        _progress(f"Camada 5: Refinamento IA ({len(todos_resultados)} pares)...", 75)

        def _ia_progress(msg: str) -> None:
            _progress(f"Camada 5: {msg}", 80)

        todos_resultados, custo_ia = camada5(todos_resultados, _ia_progress)
        _progress(f"Camada 5: Refinamento IA concluído (custo: ${custo_ia:.4f})", 90)

    # -----------------------------------------------------------------------
    # Pós-processamento
    # -----------------------------------------------------------------------
    _progress("Gerando relatório...", 95)

    # Filtrar "NENHUMA" que podem ter vindo da IA
    todos_resultados = [r for r in todos_resultados if r.get("classificacao") != "NENHUMA"]

    # Filtrar pares onde o titular da RPI bate com QUALQUER cliente da carteira.
    # Cobre o caso "cliente A da carteira × marca nova do cliente A na RPI"
    # que o filtro de processo não pegou (processo ainda não está na carteira).
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz

    # Cache por titular_rpi único — evita O(n_pares × n_titulares) com rapidfuzz.
    # Pré-computa uma vez por titular distinto, não por par.
    _cache_titular: dict[str, bool] = {}

    def _titular_rpi_eh_cliente(titular_rpi: str) -> bool:
        if not titular_rpi:
            return False
        norm = _normalizar_titular(titular_rpi)
        if not norm:
            return False
        if norm in _cache_titular:
            return _cache_titular[norm]
        if norm in titulares_carteira_norm:
            _cache_titular[norm] = True
            return True
        if titulares_carteira_lista:
            match = _rf_process.extractOne(
                norm, titulares_carteira_lista,
                scorer=_rf_fuzz.ratio, score_cutoff=92,
            )
            resultado = match is not None
            _cache_titular[norm] = resultado
            return resultado
        _cache_titular[norm] = False
        return False

    antes = len(todos_resultados)
    todos_resultados = [
        r for r in todos_resultados
        if not _titular_rpi_eh_cliente(r.get("titular_rpi", ""))
    ]
    removidos_titular = antes - len(todos_resultados)
    if removidos_titular:
        _progress(
            f"Pós-processamento: {removidos_titular} par(es) removido(s) "
            f"— titular da RPI é cliente",
            96,
        )

    # Ordenar por score_final DESC
    todos_resultados.sort(key=lambda r: r.get("score_final", r.get("score_nome", 0)), reverse=True)

    # Remover duplicatas (mesma marca_base + marca_rpi + ncl_base + ncl_rpi)
    seen: set[tuple] = set()
    dedup: list[dict] = []
    for r in todos_resultados:
        key = (
            r.get("marca_base", ""),
            r.get("ncl_base", 0),
            r.get("marca_rpi", ""),
            r.get("ncl_rpi", 0),
        )
        if key not in seen:
            seen.add(key)
            dedup.append(r)

    # Estatísticas
    stats = {
        "rpi_numero": rpi_numero,
        "rpi_data": rpi_data,
        "total_carteira": len(carteira),
        "total_rpi": len(rpi_raw),
        "total_rpi_oposicao": total_rpi_oposicao,
        "total_rpi_pan": total_rpi_pan,
        "alertas_total": len(dedup),
        "alertas_alta": sum(1 for r in dedup if r.get("classificacao") == "ALTA"),
        "alertas_media": sum(1 for r in dedup if r.get("classificacao") == "MEDIA"),
        "alertas_baixa": sum(1 for r in dedup if r.get("classificacao") == "BAIXA"),
        "alertas_oposicao": sum(1 for r in dedup if r.get("tipo_acao") == "OPOSICAO"),
        "alertas_pan": sum(1 for r in dedup if r.get("tipo_acao") == "PAN"),
        "camada1_count": len(alertas_c1),
        "camada2_count": len(candidatos_c2),
        "camada3_count": len(candidatos_c3),
        "camada4_count": len(scored_c4),
    }

    tempo = round(time.time() - t0, 2)
    _progress(f"Pipeline concluído em {tempo}s — {len(dedup)} alertas", 100)

    return {
        "resultados": dedup,
        "stats": stats,
        "custo_ia_usd": custo_ia,
        "tempo_seg": tempo,
        "corpus_update": {
            "termos": {f"{ncl}:{tok}": cnt for (ncl, tok), cnt in _corpus_termos.items()},
            "classes": {str(ncl): cnt for ncl, cnt in _corpus_classes.items()},
        },
    }
