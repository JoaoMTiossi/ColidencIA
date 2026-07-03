"""
Orquestrador do pipeline de colidência (Camadas 0–5).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from typing import Callable

from ..config import DESPACHOS_OPOSICAO, DESPACHOS_PAN, OUTPUT_DIR, TAMANHO_LOTE_RPI
from ..parsers.parse_excel import parse_excel
from ..parsers.parse_xml import parse_rpi_xml
from .fonetica import camada2
from .ia_refinamento import camada5
from .nome_identico import camada1, reclassificar_pos_c3
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


def _chave_par(r: dict) -> tuple:
    """Chave de identidade de um par marca_base×marca_rpi usada pelo dedup."""
    return (
        r.get("marca_base", ""),
        r.get("ncl_base", 0),
        r.get("marca_rpi", ""),
        r.get("ncl_rpi", 0),
    )


def _dedup_pares(pares: list[dict]) -> list[dict]:
    """Remove duplicatas (mesma marca em múltiplos registros da carteira
    gera pares com a mesma chave), mantendo o de maior score."""
    ordenados = sorted(
        pares,
        key=lambda r: r.get("score_final", r.get("score_nome", 0)),
        reverse=True,
    )
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in ordenados:
        key = _chave_par(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _remover_pares_ja_em_c1(alertas_c1: list[dict], scored_c4: list[dict]) -> list[dict]:
    """
    Dedup cruzado C1×C4: como a camada 1 agora deixa fluir para C2 TODAS as
    marcas da RPI (mesmo as que já geraram alerta com alguma marca da
    carteira — ver nome_identico.camada1), o MESMO par (marca_base × marca_rpi)
    pode aparecer tanto em alertas_c1 quanto em scored_c4.

    O alerta C1 é juridicamente decidido (art. 124, XIX LPI) e deve vencer
    SEMPRE — mesmo quando o score_final do C4 for maior que o do C1 (ex.:
    nucleo_identico cross-class não colidente tem score_final=0.70, abaixo de
    muitos scores C4). Por isso a remoção é por chave de par, não por score.
    """
    chaves_c1 = {_chave_par(r) for r in alertas_c1}
    return [r for r in scored_c4 if _chave_par(r) not in chaves_c1]


def _gravar_checkpoint(
    path: str,
    resultados: list[dict],
    lote: int,
    total_lotes: int,
    custo_ia_usd: float,
    rpi_numero: str,
) -> None:
    """
    Grava os resultados acumulados após cada lote — se a execução cair no
    meio, o trabalho dos lotes concluídos não se perde. Escrita atômica
    (tmp + os.replace). Falha de gravação NUNCA aborta o pipeline.
    """
    try:
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        payload = {
            "rpi_numero": rpi_numero,
            "lote": lote,
            "total_lotes": total_lotes,
            "custo_ia_usd": round(custo_ia_usd, 4),
            "resultados": resultados,
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("Falha ao gravar checkpoint (não crítico): %s", e)


def _processar_lote(
    carteira: list[dict],
    rpi_chunk: list[dict],
    usar_ia: bool,
    custo_inicial: float,
    filtrar_titular: Callable[[list[dict]], tuple[list[dict], int]],
    progress: Callable[[str, int], None],
    pct: int,
) -> tuple[list[dict], float, dict]:
    """
    Executa C1→C5 para um lote de marcas da RPI contra a carteira completa.

    custo_inicial: gasto IA acumulado nos lotes anteriores — o budget da
    camada 5 é global por execução, não por lote.

    Retorna (resultados_do_lote, custo_ia_do_lote, contadores).
    """
    # Camada 1 — Nome idêntico
    alertas_c1_raw, rpi_restante = camada1(carteira, rpi_chunk)

    # Filtro de afinidade NCL/especificação sobre os alertas C1. Decisão de
    # design (deliberada): nome idêntico cross-class SEM afinidade real é
    # descartado aqui — o princípio da especialidade prevalece; alto renome
    # (art. 125 LPI) é exceção rara, avaliada manualmente fora do pipeline.
    if alertas_c1_raw:
        alertas_c1 = camada3(alertas_c1_raw)
        for a in alertas_c1:
            a["camada_deteccao"] = 1  # camada3 sobrescreve; restaurar origem
            # A C3 refinou score_spec — re-derivar classificacao/nivel/score
            # para o registro sair consistente (sem ALTA com afinidade baixa).
            reclassificar_pos_c3(a)
    else:
        alertas_c1 = alertas_c1_raw

    # Camada 2 — Filtro fonético
    candidatos_c2, _ = camada2(carteira, rpi_restante)

    # Camada 3 — Filtro de especificação
    candidatos_c3 = camada3(candidatos_c2)

    # Camada 4 — Scoring composto (alertas C1 já têm score, bypassam C4)
    scored_c4 = camada4(candidatos_c3)

    # Pós-filtros PRÉ-IA — rodam antes da camada 5 para não gastar orçamento
    # com pares que seriam removidos no pós-processamento.
    alertas_c1, rem_t1 = filtrar_titular(alertas_c1)
    scored_c4, rem_t4 = filtrar_titular(scored_c4)
    alertas_c1 = _dedup_pares(alertas_c1)
    scored_c4 = _dedup_pares(scored_c4)
    # Dedup cruzado: um par já decidido em C1 (nome/núcleo idêntico) nunca
    # deve reaparecer como candidato C4 — o alerta C1 sempre vence, mesmo com
    # score_final menor (ver docstring de _remover_pares_ja_em_c1).
    scored_c4 = _remover_pares_ja_em_c1(alertas_c1, scored_c4)

    # Camada 5 — Refinamento IA
    # Apenas os pares da camada 4: alertas da camada 1 (nome/núcleo idêntico)
    # já estão juridicamente decididos (art. 124, XIX LPI) — enviá-los à IA
    # gastaria orçamento e permitiria que uma resposta "NENHUMA" removesse
    # silenciosamente um alerta certo do relatório.
    custo_lote = 0.0
    if usar_ia and scored_c4:
        def _ia_progress(msg: str) -> None:
            progress(f"Camada 5: {msg}", pct)

        scored_c4, custo_lote = camada5(
            scored_c4, _ia_progress, custo_inicial=custo_inicial
        )

    contadores = {
        "camada1_count": len(alertas_c1),
        "camada2_count": len(candidatos_c2),
        "camada3_count": len(candidatos_c3),
        "camada4_count": len(scored_c4),
        "removidos_titular": rem_t1 + rem_t4,
    }
    return alertas_c1 + scored_c4, custo_lote, contadores


def executar_pipeline(
    path_carteira: str,
    path_rpi: str,
    despachos_selecionados: list[str] | None = None,
    progress_cb: Callable[[str, int], None] | None = None,
    usar_ia: bool = True,
    checkpoint_path: str | None = None,
) -> dict:
    """
    Executa o pipeline completo de colidência.

    A RPI é processada em lotes de TAMANHO_LOTE_RPI marcas (C1→C5 por lote);
    após cada lote os resultados acumulados são gravados em checkpoint e o
    progresso é logado por % de lotes concluídos.

    Parâmetros:
        path_carteira: caminho para o Excel da carteira
        path_rpi: caminho para o XML da RPI
        despachos_selecionados: lista de códigos de despacho a considerar
                                (None = todos os relevantes)
        progress_cb: callback(mensagem: str, pct: int) para atualizar progresso
        usar_ia: se True e OPENAI_API_KEY configurada, executa camada 5
        checkpoint_path: arquivo JSON de resultados parciais
                         (None = OUTPUT_DIR/checkpoint_execucao.json)

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
    # Roda sobre o conjunto COMPLETO, antes do processamento em lotes.
    # -----------------------------------------------------------------------
    _corpus_termos: Counter[tuple[int, str]] = Counter()
    _corpus_classes: Counter[int] = Counter()
    for _m in carteira + rpi:
        _ncl = _m.get("ncl", 0)
        if _ncl <= 0:
            continue
        _toks = set(t for t in (_m.get("nome_normalizado", "") or "").split() if len(t) >= 3)
        for _tok in _toks:
            _corpus_termos[(_ncl, _tok)] += 1
        _corpus_classes[_ncl] += 1

    # -----------------------------------------------------------------------
    # Filtro de titular — definido UMA vez, antes do loop de lotes, para que
    # o cache rapidfuzz por titular persista entre os lotes.
    # Filtra pares onde o titular da RPI bate com QUALQUER cliente da carteira:
    # cobre o caso "cliente A da carteira × marca nova do cliente A na RPI"
    # que o filtro de processo não pegou (processo ainda não está na carteira).
    # -----------------------------------------------------------------------
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz

    # Cache por titular_rpi único — evita O(n_pares × n_titulares) com rapidfuzz.
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

    def _filtrar_titular(pares: list[dict]) -> tuple[list[dict], int]:
        antes = len(pares)
        pares = [
            r for r in pares
            if not _titular_rpi_eh_cliente(r.get("titular_rpi", ""))
        ]
        return pares, antes - len(pares)

    # -----------------------------------------------------------------------
    # Processamento em lotes — C1→C5 por grupo de TAMANHO_LOTE_RPI marcas.
    # Checkpoint após cada lote; progresso por % de lotes concluídos.
    # -----------------------------------------------------------------------
    if checkpoint_path is None:
        checkpoint_path = os.path.join(OUTPUT_DIR, "checkpoint_execucao.json")

    total_lotes = math.ceil(len(rpi) / TAMANHO_LOTE_RPI) if rpi else 0
    _progress(
        f"Processando {len(rpi)} marcas em {total_lotes} lote(s) "
        f"de até {TAMANHO_LOTE_RPI}...",
        25,
    )

    acumulado: list[dict] = []
    custo_ia = 0.0
    contadores_totais: defaultdict[str, int] = defaultdict(int)

    for i in range(total_lotes):
        chunk = rpi[i * TAMANHO_LOTE_RPI:(i + 1) * TAMANHO_LOTE_RPI]
        # Mapeia o avanço dos lotes na faixa 25..95 do progresso global
        pct = 25 + int(70 * (i + 1) / total_lotes)
        resultados_lote, custo_lote, cont = _processar_lote(
            carteira=carteira,
            rpi_chunk=chunk,
            usar_ia=usar_ia,
            custo_inicial=custo_ia,
            filtrar_titular=_filtrar_titular,
            progress=_progress,
            pct=pct,
        )
        custo_ia += custo_lote
        acumulado.extend(resultados_lote)
        for k, v in cont.items():
            contadores_totais[k] += v

        _gravar_checkpoint(
            checkpoint_path, acumulado, i + 1, total_lotes, custo_ia, rpi_numero
        )
        _progress(
            f"Lote {i + 1}/{total_lotes} concluído — "
            f"{int(100 * (i + 1) / total_lotes)}% "
            f"({len(acumulado)} alertas acumulados, custo IA ${custo_ia:.4f})",
            pct,
        )

    if contadores_totais.get("removidos_titular"):
        _progress(
            f"Pré-IA: {contadores_totais['removidos_titular']} par(es) "
            f"removido(s) — titular da RPI é cliente",
            95,
        )

    todos_resultados = acumulado

    # -----------------------------------------------------------------------
    # Pós-processamento
    # -----------------------------------------------------------------------
    _progress("Gerando relatório...", 95)

    # Filtrar "NENHUMA" que podem ter vindo da IA
    todos_resultados = [r for r in todos_resultados if r.get("classificacao") != "NENHUMA"]

    # Dedup cruzado C1×C4 GLOBAL (entre lotes): _remover_pares_ja_em_c1 já
    # roda por lote em _processar_lote, mas um par pode teoricamente colidir
    # entre lotes diferentes (mesmo marca_base/marca_rpi/ncl em registros
    # processados em lotes distintos). O alerta C1 (camada_deteccao == 1)
    # sempre vence — repete-se aqui para não depender apenas do score no
    # dedup global logo abaixo, que ordena só por score_final.
    alertas_c1_todos = [r for r in todos_resultados if r.get("camada_deteccao") == 1]
    demais = [r for r in todos_resultados if r.get("camada_deteccao") != 1]
    demais = _remover_pares_ja_em_c1(alertas_c1_todos, demais)
    todos_resultados = alertas_c1_todos + demais

    # Dedup global final (ordena por score DESC e remove duplicatas) — cobre
    # também duplicatas entre lotes (mesma marca da RPI em registros por
    # classe distribuídos em lotes diferentes).
    dedup = _dedup_pares(todos_resultados)

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
        "camada1_count": contadores_totais.get("camada1_count", 0),
        "camada2_count": contadores_totais.get("camada2_count", 0),
        "camada3_count": contadores_totais.get("camada3_count", 0),
        "camada4_count": contadores_totais.get("camada4_count", 0),
        "total_lotes": total_lotes,
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
