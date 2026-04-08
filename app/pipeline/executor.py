"""
Orquestrador do pipeline de colidência (Camadas 0–5).
"""
from __future__ import annotations

import logging
import time
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

    carteira = preprocessar_lote(carteira_raw)

    _progress("Carregando RPI...", 15)
    rpi_raw, rpi_numero, rpi_data = parse_rpi_xml(path_rpi)

    # Filtrar por despachos selecionados
    if despachos_selecionados:
        rpi_raw = [r for r in rpi_raw if r["despacho_codigo"] in despachos_selecionados]

    total_rpi_oposicao = sum(1 for r in rpi_raw if r["despacho_codigo"] in DESPACHOS_OPOSICAO)
    total_rpi_pan = sum(1 for r in rpi_raw if r["despacho_codigo"] in DESPACHOS_PAN)

    _progress(f"RPI {rpi_numero} ({rpi_data}): {len(rpi_raw)} marcas filtradas", 20)
    rpi = preprocessar_lote(rpi_raw)

    # -----------------------------------------------------------------------
    # Camada 1 — Nome idêntico
    # -----------------------------------------------------------------------
    _progress("Camada 1: Verificando nomes idênticos...", 30)
    alertas_c1, rpi_restante = camada1(carteira, rpi)
    _progress(f"Camada 1: {len(alertas_c1)} colidências automáticas encontradas", 35)

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
    }
