"""
Endpoint de execução do pipeline de colidência.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import DESPACHOS_RELEVANTES, OUTPUT_DIR
from ..database import get_db
from ..models import Execucao, Resultado
from ..pipeline.executor import executar_pipeline
from ..pipeline.relatorio import gerar_xlsx
from ..utils.log_buffer import add_log
from .upload import get_upload_path

router = APIRouter(prefix="/api", tags=["pipeline"])
logger = logging.getLogger(__name__)

# Estado de progresso por execucao_id (em memória)
_progresso: dict[int, dict] = {}


class ExecutarRequest(BaseModel):
    carteira_upload_id: str
    rpi_upload_id: str
    despachos_selecionados: list[str] = []


@router.post("/executar")
async def executar(req: ExecutarRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Inicia o pipeline de colidência em background.
    Retorna {execucao_id} imediatamente.
    """
    path_carteira = get_upload_path(req.carteira_upload_id)
    path_rpi = get_upload_path(req.rpi_upload_id)

    if not path_carteira or not os.path.exists(path_carteira):
        raise HTTPException(400, "Arquivo da carteira não encontrado. Faça o upload novamente.")
    if not path_rpi or not os.path.exists(path_rpi):
        raise HTTPException(400, "Arquivo da RPI não encontrado. Faça o upload novamente.")

    despachos = req.despachos_selecionados or list(DESPACHOS_RELEVANTES)
    despachos_invalidos = [d for d in despachos if d not in DESPACHOS_RELEVANTES]
    if despachos_invalidos:
        raise HTTPException(400, f"Despachos inválidos: {despachos_invalidos}")

    # Criar registro de execução
    execucao = Execucao(
        status="em_andamento",
        despachos_selecionados=json.dumps(despachos),
        arquivo_carteira=path_carteira,
        arquivo_rpi=path_rpi,
    )
    db.add(execucao)
    await db.commit()
    await db.refresh(execucao)

    execucao_id = execucao.id
    _progresso[execucao_id] = {"mensagem": "Iniciando...", "percentual": 0}
    add_log("INFO", f"🚀 Pipeline #{execucao_id} iniciado — {len(despachos)} despacho(s) selecionado(s)", "pipeline")

    # Executar em thread background (pipeline é síncrono)
    def _run():
        import asyncio
        asyncio.run(_executar_async(execucao_id, path_carteira, path_rpi, despachos))

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return JSONResponse({"execucao_id": execucao_id})


async def _executar_async(
    execucao_id: int,
    path_carteira: str,
    path_rpi: str,
    despachos: list[str],
) -> None:
    """Executa o pipeline e persiste os resultados."""
    from ..database import AsyncSessionLocal

    def _progress(msg: str, pct: int) -> None:
        _progresso[execucao_id] = {"mensagem": msg, "percentual": pct}

    try:
        output = executar_pipeline(
            path_carteira=path_carteira,
            path_rpi=path_rpi,
            despachos_selecionados=despachos,
            progress_cb=_progress,
            usar_ia=True,
        )
    except Exception as e:
        logger.exception("Erro no pipeline execucao_id=%d", execucao_id)
        add_log("ERROR", f"❌ Pipeline #{execucao_id} falhou: {e}", "pipeline")
        async with AsyncSessionLocal() as db:
            execucao = await db.get(Execucao, execucao_id)
            if execucao:
                execucao.status = "erro"
                execucao.erro_msg = str(e)
                await db.commit()
        _progresso[execucao_id] = {"mensagem": f"Erro: {e}", "percentual": -1}
        return

    resultados = output["resultados"]
    stats = output["stats"]

    # Gerar relatório Excel
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rpi_num = stats.get("rpi_numero", "0")
    safe_date = (stats.get("rpi_data", "") or "").replace("/", "-")
    filename = f"Colidencia_RPI{rpi_num}_{safe_date}_{execucao_id}.xlsx"
    path_xlsx = os.path.join(OUTPUT_DIR, filename)
    try:
        gerar_xlsx(resultados, stats, path_xlsx)
    except Exception as e:
        logger.warning("Falha ao gerar XLSX: %s", e)
        path_xlsx = ""

    # Persistir no banco
    async with AsyncSessionLocal() as db:
        execucao = await db.get(Execucao, execucao_id)
        if not execucao:
            return

        execucao.status = "concluido"
        execucao.numero_rpi = stats.get("rpi_numero")
        execucao.data_rpi = stats.get("rpi_data")
        execucao.total_carteira = stats.get("total_carteira")
        execucao.total_rpi = stats.get("total_rpi")
        execucao.total_rpi_oposicao = stats.get("total_rpi_oposicao")
        execucao.total_rpi_pan = stats.get("total_rpi_pan")
        execucao.alertas_alta = stats.get("alertas_alta")
        execucao.alertas_media = stats.get("alertas_media")
        execucao.alertas_baixa = stats.get("alertas_baixa")
        execucao.alertas_total = stats.get("alertas_total")
        execucao.alertas_oposicao = stats.get("alertas_oposicao")
        execucao.alertas_pan = stats.get("alertas_pan")
        execucao.tempo_execucao_seg = output.get("tempo_seg")
        execucao.custo_ia_usd = output.get("custo_ia_usd")
        execucao.arquivo_resultado = path_xlsx if path_xlsx else None

        # Inserir resultados em lote
        for r in resultados:
            resultado = Resultado(
                execucao_id=execucao_id,
                tipo_acao=r.get("tipo_acao"),
                despacho_codigo=r.get("despacho_codigo"),
                despacho_nome=r.get("despacho_nome"),
                marca_base=r.get("marca_base"),
                ncl_base=r.get("ncl_base"),
                spec_base=(r.get("spec_base") or "")[:2000],
                marca_rpi=r.get("marca_rpi"),
                ncl_rpi=r.get("ncl_rpi"),
                spec_rpi=(r.get("spec_rpi") or "")[:2000],
                processo_rpi=r.get("processo_rpi"),
                titular_rpi=r.get("titular_rpi"),
                classificacao=r.get("classificacao"),
                score_final=r.get("score_final"),
                score_nome=r.get("score_nome"),
                score_fonetico=r.get("score_fonetico"),
                score_spec=r.get("score_spec"),
                score_nucleo=r.get("score_nucleo"),
                score_ia=r.get("score_ia"),
                camada_deteccao=r.get("camada_deteccao"),
                justificativa_ia=r.get("justificativa_ia"),
                nucleo_base=r.get("nucleo_base"),
                nucleo_rpi=r.get("nucleo_rpi"),
                classes_colidem=r.get("classes_colidem_flag"),
                is_sigla=r.get("is_sigla"),
                is_desgastado=r.get("is_desgastado"),
                aspecto_grafico=r.get("aspecto_grafico"),
                aspecto_fonetico=r.get("aspecto_fonetico"),
                aspecto_ideologico=r.get("aspecto_ideologico"),
                afinidade_mercadologica=r.get("afinidade_mercadologica"),
            )
            db.add(resultado)

        await db.commit()

    _progresso[execucao_id] = {"mensagem": "Concluído", "percentual": 100}
    add_log("INFO",
        f"✅ Pipeline #{execucao_id} concluído — {len(resultados)} alertas "
        f"(Alta: {stats.get('alertas_alta',0)}, Média: {stats.get('alertas_media',0)}, "
        f"Baixa: {stats.get('alertas_baixa',0)}) em {output.get('tempo_seg',0):.1f}s",
        "pipeline")
    logger.info("Pipeline execucao_id=%d concluído: %d alertas", execucao_id, len(resultados))


@router.get("/status/{execucao_id}")
async def status(execucao_id: int, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Retorna status + progresso da execução."""
    execucao = await db.get(Execucao, execucao_id)
    if not execucao:
        raise HTTPException(404, "Execução não encontrada")

    prog = _progresso.get(execucao_id, {"mensagem": "", "percentual": 0})

    return JSONResponse({
        "execucao_id": execucao_id,
        "status": execucao.status,
        "mensagem": prog["mensagem"],
        "percentual": prog["percentual"],
        "alertas_total": execucao.alertas_total,
        "alertas_alta": execucao.alertas_alta,
        "alertas_media": execucao.alertas_media,
        "alertas_baixa": execucao.alertas_baixa,
        "alertas_oposicao": execucao.alertas_oposicao,
        "alertas_pan": execucao.alertas_pan,
        "tempo_execucao_seg": execucao.tempo_execucao_seg,
        "custo_ia_usd": execucao.custo_ia_usd,
        "erro_msg": execucao.erro_msg,
    })
