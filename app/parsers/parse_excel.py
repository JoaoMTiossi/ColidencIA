"""
Parser da planilha interna de marcas dos clientes (carteira).
"""
from __future__ import annotations

import re
from typing import Iterator

import openpyxl


# ---------------------------------------------------------------------------
# Limpeza do campo MARCA
# ---------------------------------------------------------------------------

_RE_FIGURATIVA_COLON = re.compile(r'FIGURATIV[AO]\s*:\s*', re.IGNORECASE)
_RE_PARENTESES = re.compile(r'\s*\([^)]*\)\s*$')
_RE_ESPACOS = re.compile(r'\s{2,}')


def _limpar_marca(marca_raw: str | None, apresentacao: str | None = None) -> str | None:
    """
    Limpa o campo MARCA conforme as regras do spec.

    Retorna None quando a marca deve ser excluída do pipeline.
    """
    if marca_raw is None:
        return None
    texto = str(marca_raw).strip()
    if not texto:
        return None

    upper = texto.upper()

    # Regra 2: se é literalmente "FIGURATIVA" ou "FIGURATIVO" → excluir
    if upper in ("FIGURATIVA", "FIGURATIVO"):
        return None

    # Regra 7: "FIGURATIVA: NOME" → extrair nome
    m = _RE_FIGURATIVA_COLON.match(texto)
    if m:
        texto = texto[m.end():].strip()
        if not texto:
            return None

    # Regra 3 e 4: remover sufixos entre parênteses ex: "(FIGURATIVA)", "(UNIFICADOS)"
    texto = _RE_PARENTESES.sub('', texto).strip()

    # Normalizar espaços duplos
    texto = _RE_ESPACOS.sub(' ', texto).strip()

    if not texto:
        return None

    # Após limpeza, se ficou só "FIGURATIVA" ou "FIGURATIVO" → excluir
    if texto.upper() in ("FIGURATIVA", "FIGURATIVO"):
        return None

    return texto


# ---------------------------------------------------------------------------
# Parsing da CLASSE
# ---------------------------------------------------------------------------

_RE_CLASSE = re.compile(r'Ncl\(\d+\)\s*(\d+)', re.IGNORECASE)
_RE_CLASSE_FALLBACK = re.compile(r'\b(\d{1,2})\s*$')


def _parse_classe(classe_raw: str | None) -> int | None:
    """Extrai o número da classe NCL do campo CLASSE ('Ncl(13) 35' → 35)."""
    if not classe_raw:
        return None
    s = str(classe_raw).strip()
    m = _RE_CLASSE.search(s)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 45 else None
    # Fallback: último número no campo
    m2 = _RE_CLASSE_FALLBACK.search(s)
    if m2:
        n = int(m2.group(1))
        return n if 1 <= n <= 45 else None
    return None


# ---------------------------------------------------------------------------
# Parsing da ESPECIFICAÇÃO
# ---------------------------------------------------------------------------

_RE_CLASSE_PREFIX = re.compile(r'^\d+\s*[-–]\s*')


def _parse_especificacao(spec_raw: str | None) -> str:
    """
    Limpa o campo ESPECIFICAÇÃO:
    - Remove prefixo de classe ('35 - ')
    - Trata múltiplas classes separadas por '||'
    """
    if not spec_raw:
        return ""
    partes = str(spec_raw).split("||")
    resultado: list[str] = []
    for parte in partes:
        parte = parte.strip()
        parte = _RE_CLASSE_PREFIX.sub('', parte).strip()
        if parte:
            resultado.append(parte)
    return "; ".join(resultado)


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

# Índices das colunas relevantes (base 0)
_COL_MARCA = 3
_COL_CLASSE = 4
_COL_APRESENTACAO = 5
_COL_ESPECIFICACAO = 18
_COL_TITULAR = 20


def parse_excel(filepath: str) -> list[dict]:
    """
    Carrega a planilha Excel da carteira de clientes.

    Usa openpyxl read_only para eficiência com ~49k linhas.
    Retorna lista de dicts com campos normalizados.
    """
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    records: list[dict] = []
    rows: Iterator = ws.iter_rows(values_only=True)

    # Pular cabeçalho (primeira linha)
    try:
        next(rows)
    except StopIteration:
        wb.close()
        return records

    for row in rows:
        def _cell(idx: int) -> str | None:
            try:
                v = row[idx]
                return str(v).strip() if v is not None else None
            except IndexError:
                return None

        marca_raw = _cell(_COL_MARCA)
        apresentacao = _cell(_COL_APRESENTACAO)
        classe_raw = _cell(_COL_CLASSE)
        spec_raw = _cell(_COL_ESPECIFICACAO)
        titular_raw = _cell(_COL_TITULAR)

        # Filtrar apresentações figurativas puras (sem nome)
        if apresentacao and apresentacao.upper() == "FIGURATIVA":
            marca_limpa = _limpar_marca(marca_raw, apresentacao)
            if not marca_limpa or marca_limpa.upper() in ("FIGURATIVA", "FIGURATIVO"):
                continue
        else:
            marca_limpa = _limpar_marca(marca_raw, apresentacao)

        if not marca_limpa:
            continue

        ncl = _parse_classe(classe_raw)
        if ncl is None:
            continue

        records.append({
            "marca": marca_limpa,
            "ncl": ncl,
            "apresentacao": apresentacao or "",
            "especificacao": _parse_especificacao(spec_raw),
            "titular": titular_raw or "",
        })

    wb.close()
    return records
