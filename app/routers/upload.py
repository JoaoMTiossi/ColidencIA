"""
Endpoints de upload de arquivos (carteira Excel e RPI XML).
"""
from __future__ import annotations

import os
import shutil
import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..config import DESPACHOS_NOMES, DESPACHOS_OPOSICAO, DESPACHOS_PAN, UPLOAD_DIR
from ..parsers.parse_xml import parse_rpi_summary

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Estado em memória para arquivos enviados (suficiente para uso single-user)
_uploads: dict[str, dict] = {}


def _salvar_arquivo(upload: UploadFile, subdir: str, extensao: str) -> str:
    """Salva o arquivo no diretório de uploads e retorna o caminho."""
    os.makedirs(os.path.join(UPLOAD_DIR, subdir), exist_ok=True)
    uid = uuid.uuid4().hex
    filename = f"{uid}{extensao}"
    path = os.path.join(UPLOAD_DIR, subdir, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return path


@router.post("/carteira")
async def upload_carteira(file: UploadFile) -> JSONResponse:
    """
    Recebe o Excel da carteira de clientes.
    Retorna {upload_id, filename, tamanho_bytes}.
    A contagem de registros é feita na execução (pesado para 49k linhas).
    """
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Apenas arquivos .xlsx são aceitos para a carteira")

    path = _salvar_arquivo(file, "carteira", ".xlsx")
    upload_id = os.path.basename(path).replace(".xlsx", "")
    tamanho = os.path.getsize(path)

    _uploads[upload_id] = {"tipo": "carteira", "path": path, "filename": file.filename}

    return JSONResponse({
        "upload_id": upload_id,
        "filename": file.filename,
        "tamanho_bytes": tamanho,
    })


@router.post("/rpi")
async def upload_rpi(file: UploadFile) -> JSONResponse:
    """
    Recebe o XML da RPI.
    Retorna número/data da RPI + resumo dos despachos disponíveis.
    """
    if not (file.filename or "").lower().endswith(".xml"):
        raise HTTPException(400, "Apenas arquivos .xml são aceitos para a RPI")

    path = _salvar_arquivo(file, "rpi", ".xml")
    upload_id = os.path.basename(path).replace(".xml", "")
    tamanho = os.path.getsize(path)

    # Parsear resumo dos despachos
    try:
        summary, rpi_numero, rpi_data = parse_rpi_summary(path)
    except Exception as e:
        raise HTTPException(422, f"Erro ao parsear XML: {e}") from e

    # Montar lista de despachos disponíveis com metadados
    despachos_disponiveis = []
    for codigo, contagens in sorted(summary.items()):
        total = contagens.get("total", 0)
        com_nome = contagens.get("com_nome", 0)
        nome = DESPACHOS_NOMES.get(codigo, codigo)

        if codigo in DESPACHOS_OPOSICAO:
            tipo_acao = "OPOSICAO"
        elif codigo in DESPACHOS_PAN:
            tipo_acao = "PAN"
        else:
            tipo_acao = "OUTRO"

        despachos_disponiveis.append({
            "codigo": codigo,
            "nome": nome,
            "total": total,
            "com_nome": com_nome,
            "tipo_acao": tipo_acao,
            "relevante": codigo in (DESPACHOS_OPOSICAO | DESPACHOS_PAN),
        })

    # Ordenar: relevantes primeiro, por volume
    despachos_disponiveis.sort(key=lambda d: (-int(d["relevante"]), -d["total"]))

    _uploads[upload_id] = {
        "tipo": "rpi",
        "path": path,
        "filename": file.filename,
        "rpi_numero": rpi_numero,
        "rpi_data": rpi_data,
    }

    return JSONResponse({
        "upload_id": upload_id,
        "filename": file.filename,
        "tamanho_bytes": tamanho,
        "rpi_numero": rpi_numero,
        "rpi_data": rpi_data,
        "despachos_disponiveis": despachos_disponiveis,
    })


def get_upload_path(upload_id: str) -> str | None:
    """Retorna o caminho do arquivo para um upload_id."""
    info = _uploads.get(upload_id)
    return info["path"] if info else None
