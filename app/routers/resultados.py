"""
Endpoints de consulta, download e histórico de resultados.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import RETENTION_DAYS
from ..database import get_db
from ..models import Execucao, Resultado
from ..pipeline.relatorio import gerar_csv_bytes, gerar_xlsx

router = APIRouter(prefix="/api", tags=["resultados"])


@router.get("/resultados/{execucao_id}")
async def listar_resultados(
    execucao_id: int,
    tipo_acao: str | None = Query(None, description="OPOSICAO ou PAN"),
    classificacao: str | None = Query(None, description="ALTA, MEDIA ou BAIXA"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Retorna resultados paginados com filtros opcionais."""
    execucao = await db.get(Execucao, execucao_id)
    if not execucao:
        raise HTTPException(404, "Execução não encontrada")

    stmt = select(Resultado).where(Resultado.execucao_id == execucao_id)

    if tipo_acao:
        stmt = stmt.where(Resultado.tipo_acao == tipo_acao.upper())
    if classificacao:
        stmt = stmt.where(Resultado.classificacao == classificacao.upper())

    # Ordenar por score_final DESC
    stmt = stmt.order_by(Resultado.score_final.desc().nullslast())

    # Total para paginação
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(
        stmt.subquery()
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginação
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return JSONResponse({
        "execucao_id": execucao_id,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "resultados": [_resultado_to_dict(r) for r in rows],
        "resumo": {
            "alertas_alta": execucao.alertas_alta,
            "alertas_media": execucao.alertas_media,
            "alertas_baixa": execucao.alertas_baixa,
            "alertas_oposicao": execucao.alertas_oposicao,
            "alertas_pan": execucao.alertas_pan,
            "alertas_total": execucao.alertas_total,
        },
    })


@router.get("/resultados/{execucao_id}/download/xlsx")
async def download_xlsx(
    execucao_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Baixa o relatório Excel da execução."""
    execucao = await db.get(Execucao, execucao_id)
    if not execucao:
        raise HTTPException(404, "Execução não encontrada")

    # Se arquivo já existe no disco, servir direto
    if execucao.arquivo_resultado and os.path.exists(execucao.arquivo_resultado):
        with open(execucao.arquivo_resultado, "rb") as f:
            content = f.read()
        filename = os.path.basename(execucao.arquivo_resultado)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Gerar on-the-fly a partir do banco
    stmt = select(Resultado).where(Resultado.execucao_id == execucao_id).order_by(
        Resultado.score_final.desc().nullslast()
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    resultados = [_resultado_to_dict(r) for r in rows]
    stats = {
        "rpi_numero": execucao.numero_rpi or "",
        "rpi_data": execucao.data_rpi or "",
        "total_carteira": execucao.total_carteira or 0,
        "total_rpi": execucao.total_rpi or 0,
        "total_rpi_oposicao": execucao.total_rpi_oposicao or 0,
        "total_rpi_pan": execucao.total_rpi_pan or 0,
        "alertas_alta": execucao.alertas_alta or 0,
        "alertas_media": execucao.alertas_media or 0,
        "alertas_baixa": execucao.alertas_baixa or 0,
        "alertas_total": execucao.alertas_total or 0,
        "alertas_oposicao": execucao.alertas_oposicao or 0,
        "alertas_pan": execucao.alertas_pan or 0,
    }

    # Gerar em memória
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        gerar_xlsx(resultados, stats, tmp_path)
        with open(tmp_path, "rb") as f:
            content = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    filename = f"Colidencia_RPI{execucao.numero_rpi}_{execucao_id}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/resultados/{execucao_id}/download/csv")
async def download_csv(
    execucao_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Baixa o relatório CSV da execução."""
    execucao = await db.get(Execucao, execucao_id)
    if not execucao:
        raise HTTPException(404, "Execução não encontrada")

    stmt = select(Resultado).where(Resultado.execucao_id == execucao_id).order_by(
        Resultado.score_final.desc().nullslast()
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    resultados = [_resultado_to_dict(r) for r in rows]

    csv_bytes = gerar_csv_bytes(resultados)
    filename = f"Colidencia_RPI{execucao.numero_rpi}_{execucao_id}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/historico")
async def historico(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Lista execuções dos últimos RETENTION_DAYS dias."""
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    stmt = (
        select(Execucao)
        .where(Execucao.data_execucao >= cutoff)
        .order_by(Execucao.data_execucao.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    execucoes = result.scalars().all()

    return JSONResponse({
        "execucoes": [
            {
                "id": e.id,
                "data_execucao": e.data_execucao.isoformat() if e.data_execucao else None,
                "numero_rpi": e.numero_rpi,
                "data_rpi": e.data_rpi,
                "status": e.status,
                "alertas_total": e.alertas_total,
                "alertas_oposicao": e.alertas_oposicao,
                "alertas_pan": e.alertas_pan,
                "alertas_alta": e.alertas_alta,
                "tempo_execucao_seg": e.tempo_execucao_seg,
            }
            for e in execucoes
        ]
    })


@router.delete("/execucao/{execucao_id}")
async def deletar_execucao(
    execucao_id: int,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Remove uma execução e seus dados."""
    execucao = await db.get(Execucao, execucao_id)
    if not execucao:
        raise HTTPException(404, "Execução não encontrada")

    # Remover arquivo de resultado
    if execucao.arquivo_resultado and os.path.exists(execucao.arquivo_resultado):
        try:
            os.unlink(execucao.arquivo_resultado)
        except OSError:
            pass

    await db.delete(execucao)
    await db.commit()

    return JSONResponse({"ok": True, "execucao_id": execucao_id})


async def limpar_execucoes_antigas(db: AsyncSession) -> int:
    """Remove execuções com mais de RETENTION_DAYS dias. Retorna quantidade removida."""
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)

    # Buscar para pegar paths dos arquivos
    stmt = select(Execucao).where(Execucao.data_execucao < cutoff)
    result = await db.execute(stmt)
    antigas = result.scalars().all()

    count = 0
    for execucao in antigas:
        if execucao.arquivo_resultado and os.path.exists(execucao.arquivo_resultado):
            try:
                os.unlink(execucao.arquivo_resultado)
            except OSError:
                pass
        await db.delete(execucao)
        count += 1

    if count:
        await db.commit()

    return count


def _resultado_to_dict(r: Resultado) -> dict:
    return {
        "id": r.id,
        "tipo_acao": r.tipo_acao,
        "despacho_codigo": r.despacho_codigo,
        "despacho_nome": r.despacho_nome,
        "marca_base": r.marca_base,
        "ncl_base": r.ncl_base,
        "spec_base": r.spec_base,
        "marca_rpi": r.marca_rpi,
        "ncl_rpi": r.ncl_rpi,
        "spec_rpi": r.spec_rpi,
        "processo_rpi": r.processo_rpi,
        "titular_rpi": r.titular_rpi,
        "classificacao": r.classificacao,
        "score_final": r.score_final,
        "score_nome": r.score_nome,
        "score_fonetico": r.score_fonetico,
        "score_spec": r.score_spec,
        "score_nucleo": r.score_nucleo,
        "score_ia": r.score_ia,
        "camada_deteccao": r.camada_deteccao,
        "justificativa_ia": r.justificativa_ia,
        "nucleo_base": r.nucleo_base,
        "nucleo_rpi": r.nucleo_rpi,
        "classes_colidem": r.classes_colidem,
        "is_sigla": r.is_sigla,
        "is_desgastado": r.is_desgastado,
        "aspecto_grafico": r.aspecto_grafico,
        "aspecto_fonetico": r.aspecto_fonetico,
        "aspecto_ideologico": r.aspecto_ideologico,
        "afinidade_mercadologica": r.afinidade_mercadologica,
    }
