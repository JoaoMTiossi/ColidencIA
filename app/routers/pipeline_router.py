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

from ..config import (
    CORPUS_LIMIAR_ABS, CORPUS_LIMIAR_FREQ, CORPUS_MIN_AMOSTRA_CLASSE,
    DATA_DIR, DESPACHOS_RELEVANTES, OUTPUT_DIR,
)
from ..database import get_db
from ..models import ClasseCorpusStat, Execucao, Resultado, TermoClasseFreq
from ..pipeline.executor import executar_pipeline
from ..pipeline.relatorio import gerar_xlsx
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
    _progresso[execucao_id] = {"mensagem": "Iniciando...", "percentual": 0, "logs": []}

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
        entry = {"ts": datetime.utcnow().strftime("%H:%M:%S"), "msg": msg, "pct": max(0, pct)}
        prog = _progresso.setdefault(execucao_id, {"mensagem": "", "percentual": 0, "logs": []})
        prog["mensagem"] = msg
        prog["percentual"] = pct
        prog["logs"].append(entry)

    checkpoint_path = os.path.join(OUTPUT_DIR, f"checkpoint_execucao_{execucao_id}.json")

    try:
        output = executar_pipeline(
            path_carteira=path_carteira,
            path_rpi=path_rpi,
            despachos_selecionados=despachos,
            progress_cb=_progress,
            usar_ia=True,
            checkpoint_path=checkpoint_path,
        )
    except Exception as e:
        logger.exception("Erro no pipeline execucao_id=%d", execucao_id)
        async with AsyncSessionLocal() as db:
            execucao = await db.get(Execucao, execucao_id)
            if execucao:
                execucao.status = "erro"
                execucao.erro_msg = str(e)
                await db.commit()
        _progress(f"❌ Erro: {e}", 0)
        _progresso[execucao_id]["percentual"] = -1
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
                processo_base=r.get("processo_base"),
                marca_base=r.get("marca_base"),
                ncl_base=r.get("ncl_base"),
                ncl_versao_base=r.get("ncl_versao_base", 12),
                spec_base=(r.get("spec_base") or "")[:2000],
                titular_base=r.get("titular_base"),
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

    # Resultados persistidos — o checkpoint parcial não é mais necessário
    try:
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
    except Exception as exc:
        logger.warning("Falha ao remover checkpoint (não crítico): %s", exc)

    # Atualizar corpus de vocabulário por classe e recompilar artefato.
    # Guard: se esta MESMA RPI já foi processada antes (re-execução), pular o
    # upsert — senão as contagens de termo/classe seriam infladas a cada
    # re-execução, cruzando o limiar absoluto do vocab artificialmente.
    corpus_update = output.get("corpus_update")
    if corpus_update:
        try:
            async with AsyncSessionLocal() as db:
                ja_processada = await db.scalar(
                    select(Execucao.id).where(
                        Execucao.numero_rpi == stats.get("rpi_numero"),
                        Execucao.status == "concluido",
                        Execucao.id != execucao_id,
                    ).limit(1)
                )
                if ja_processada:
                    logger.info(
                        "RPI %s já processada (execucao_id=%d) — corpus não atualizado",
                        stats.get("rpi_numero"), ja_processada,
                    )
                else:
                    await _atualizar_corpus(db, corpus_update)
            if not ja_processada:
                await _recompilar_vocab_corpus()
                logger.info("Corpus de vocabulário atualizado e recompilado")
        except Exception as exc:
            logger.warning("Falha ao atualizar corpus (não crítico): %s", exc)

    prog = _progresso.get(execucao_id, {})
    prog.update({"mensagem": "Concluído", "percentual": 100})
    _progresso[execucao_id] = prog
    logger.info("Pipeline execucao_id=%d concluído: %d alertas", execucao_id, len(resultados))


async def _atualizar_corpus(db: AsyncSession, corpus_update: dict) -> None:
    """Upsert acumulado de TermoClasseFreq e ClasseCorpusStat."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    termos = corpus_update.get("termos", {})   # "ncl:tok" → count
    classes = corpus_update.get("classes", {})  # "ncl" → count

    # Upsert de estatísticas de classe (total de marcas por NCL)
    for ncl_str, cnt in classes.items():
        ncl = int(ncl_str)
        stmt = (
            sqlite_insert(ClasseCorpusStat)
            .values(ncl=ncl, total_marcas=cnt)
            .on_conflict_do_update(
                index_elements=["ncl"],
                set_={"total_marcas": ClasseCorpusStat.total_marcas + cnt},
            )
        )
        await db.execute(stmt)

    # Upsert de frequência por termo+classe (em lotes para não abrir transação gigante)
    BATCH = 500
    items = list(termos.items())
    for start in range(0, len(items), BATCH):
        for key, cnt in items[start:start + BATCH]:
            ncl_str, tok = key.split(":", 1)
            ncl = int(ncl_str)
            stmt = (
                sqlite_insert(TermoClasseFreq)
                .values(ncl=ncl, termo=tok, num_marcas=cnt)
                .on_conflict_do_update(
                    index_elements=["ncl", "termo"],
                    set_={"num_marcas": TermoClasseFreq.num_marcas + cnt},
                )
            )
            await db.execute(stmt)

    await db.commit()


async def _recompilar_vocab_corpus() -> None:
    """Recompila vocab_descritivo_corpus.json a partir do banco e invalida caches."""
    import json as _json
    from sqlalchemy import text as _text
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # Buscar classes com amostra suficiente
        result = await db.execute(
            _text("SELECT ncl, total_marcas FROM classe_corpus_stat WHERE total_marcas >= :min_amostra"),
            {"min_amostra": CORPUS_MIN_AMOSTRA_CLASSE},
        )
        classes_ok = {row.ncl: row.total_marcas for row in result}

        if not classes_ok:
            return

        vocab: dict[str, list[str]] = {}
        for ncl, total in classes_ok.items():
            min_abs = max(CORPUS_LIMIAR_ABS, int(total * CORPUS_LIMIAR_FREQ))
            result = await db.execute(
                _text(
                    "SELECT termo FROM termo_classe_freq "
                    "WHERE ncl = :ncl AND num_marcas >= :min_abs "
                    "ORDER BY num_marcas DESC"
                ),
                {"ncl": ncl, "min_abs": min_abs},
            )
            termos = [row.termo for row in result]
            if termos:
                vocab[str(ncl)] = termos

    path = os.path.join(DATA_DIR, "vocab_descritivo_corpus.json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(vocab, f, ensure_ascii=False, indent=2)

    # Invalidar caches para que a próxima execução use o vocab atualizado
    try:
        from ..utils.distintividade import _vocab_corpus, _vocab_descritivo
        _vocab_corpus.cache_clear()
        _vocab_descritivo.cache_clear()
    except Exception:
        pass


@router.get("/status/{execucao_id}")
async def status(execucao_id: int, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Retorna status + progresso da execução."""
    execucao = await db.get(Execucao, execucao_id)
    if not execucao:
        raise HTTPException(404, "Execução não encontrada")

    prog = _progresso.get(execucao_id, {"mensagem": "", "percentual": 0, "logs": []})

    return JSONResponse({
        "execucao_id": execucao_id,
        "status": execucao.status,
        "mensagem": prog["mensagem"],
        "percentual": prog["percentual"],
        "logs": prog.get("logs", []),
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
