"""
FastAPI application — Sistema de Colidência de Marcas (RPI).
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import HOST, PORT, UPLOAD_DIR, OUTPUT_DIR
from .database import init_db
from .routers.pipeline_router import router as pipeline_router
from .routers.resultados import limpar_execucoes_antigas, router as resultados_router
from .routers.upload import router as upload_router
from .utils.log_buffer import add_log, get_logs, instalar_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
instalar_handler()
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

# Routers
app.include_router(upload_router)
app.include_router(pipeline_router)
app.include_router(resultados_router)

# Arquivos estáticos
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Templates
_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@app.on_event("startup")
async def startup() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    await init_db()
    add_log("INFO", "✅ Sistema iniciado — banco de dados pronto", "sistema")

    from .database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        removidas = await limpar_execucoes_antigas(db)
    if removidas:
        add_log("INFO", f"🗑 {removidas} execuções antigas removidas (> 60 dias)", "sistema")

    add_log("INFO", f"🚀 ColidencIA rodando em {HOST}:{PORT}", "sistema")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "colidencia"}


@app.get("/api/logs")
async def logs(limit: int = 100, since_id: int = 0) -> JSONResponse:
    """Retorna os logs recentes do sistema para exibição na interface."""
    return JSONResponse({"logs": get_logs(limit=limit, since_id=since_id)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
