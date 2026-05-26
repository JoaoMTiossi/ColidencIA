"""
FastAPI application — Sistema de Colidência de Marcas (RPI).
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import HOST, PORT, UPLOAD_DIR, OUTPUT_DIR
from .database import init_db
from .routers import upload as upload_module
from .routers.pipeline_router import router as pipeline_router
from .routers.resultados import limpar_execucoes_antigas, router as resultados_router
from .routers.upload import router as upload_router
from .utils.alertas import alerta_shutdown, alerta_startup, enviar_alerta_async

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ColidencIA — Detecção de Colidência de Marcas",
    description="Sistema de análise de colidência de marcas da RPI/INPI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(upload_router)
app.include_router(pipeline_router)
app.include_router(resultados_router)

# Servir arquivos estáticos
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Templates Jinja2
_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@app.on_event("startup")
async def startup() -> None:
    """Inicialização: banco de dados + limpeza de dados antigos."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    await init_db()
    logger.info("Banco de dados inicializado")

    # Limpar execuções antigas
    from .database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        removidas = await limpar_execucoes_antigas(db)
    if removidas:
        logger.info("%d execuções antigas removidas", removidas)

    # Pré-carrega o modelo de embeddings em background para evitar
    # latência na primeira execução do pipeline.
    import asyncio

    def _warmup_embeddings() -> None:
        try:
            from .utils.embeddings import embeddings_disponivel
            if embeddings_disponivel():
                logger.info("Modelo de embeddings pré-carregado")
        except Exception as e:
            logger.warning("Pré-carga de embeddings falhou: %s", e)

    asyncio.get_event_loop().run_in_executor(None, _warmup_embeddings)

    await enviar_alerta_async(alerta_startup())


@app.on_event("shutdown")
async def shutdown() -> None:
    """Notifica quando o serviço é encerrado (graceful shutdown)."""
    await enviar_alerta_async(alerta_shutdown())


from fastapi import Request
from fastapi.responses import HTMLResponse


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve a interface web principal."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health() -> dict:
    import time
    from .config import ALERT_SERVICE_NAME
    return {
        "status": "ok",
        "service": ALERT_SERVICE_NAME,
        "timestamp": int(time.time()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
