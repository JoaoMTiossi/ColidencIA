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

_RE_CLASSE_COMPLETA = re.compile(r'Ncl\((\d+)\)\s*(\d+)', re.IGNORECASE)
_RE_CLASSE_FALLBACK = re.compile(r'\b(\d{1,2})\s*$')


def _parse_classe(classe_raw: str | None) -> int | None:
    """Extrai o número da classe NCL do campo CLASSE ('Ncl(13) 35' → 35)."""
    if not classe_raw:
        return None
    s = str(classe_raw).strip()
    m = _RE_CLASSE_COMPLETA.search(s)
    if m:
        n = int(m.group(2))
        return n if 1 <= n <= 45 else None
    m2 = _RE_CLASSE_FALLBACK.search(s)
    if m2:
        n = int(m2.group(1))
        return n if 1 <= n <= 45 else None
    return None


def _parse_ncl_versao(classe_raw: str | None) -> int:
    """Extrai a versão da NCL ('Ncl(12) 35' → 12). Retorna 12 como default."""
    if not classe_raw:
        return 12
    m = _RE_CLASSE_COMPLETA.search(str(classe_raw))
    if m:
        return int(m.group(1))
    return 12


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
# Detecção de colunas a partir do cabeçalho
# ---------------------------------------------------------------------------

# Colunas padrão (fallback quando não há cabeçalho reconhecível)
_COL_MARCA_DEFAULT = 3
_COL_CLASSE_DEFAULT = 4
_COL_APRESENTACAO_DEFAULT = 5
_COL_ESPECIFICACAO_DEFAULT = 18
_COL_TITULAR_DEFAULT = 20
_COL_PROCESSO_DEFAULT = 2  # estimativa; detectado via header quando possível

_KEYWORDS_PROCESSO = {"processo", "número", "numero", "nro", "no.", "proc"}
_KEYWORDS_MARCA = {"marca"}
_KEYWORDS_CLASSE = {"classe", "class", "ncl"}
_KEYWORDS_APRESENTACAO = {"apresentação", "apresentacao", "tipo"}
_KEYWORDS_ESPECIFICACAO = {"especificação", "especificacao", "especif"}
_KEYWORDS_TITULAR = {"titular", "proprietário", "proprietario", "cliente"}


def _detectar_colunas(header_row: tuple) -> dict[str, int]:
    """
    Detecta índices de colunas a partir da linha de cabeçalho.
    Retorna dict com chaves: processo, marca, classe, apresentacao, especificacao, titular.
    """
    cols: dict[str, int] = {
        "processo": _COL_PROCESSO_DEFAULT,
        "marca": _COL_MARCA_DEFAULT,
        "classe": _COL_CLASSE_DEFAULT,
        "apresentacao": _COL_APRESENTACAO_DEFAULT,
        "especificacao": _COL_ESPECIFICACAO_DEFAULT,
        "titular": _COL_TITULAR_DEFAULT,
    }

    mapping = {
        "processo": _KEYWORDS_PROCESSO,
        "marca": _KEYWORDS_MARCA,
        "classe": _KEYWORDS_CLASSE,
        "apresentacao": _KEYWORDS_APRESENTACAO,
        "especificacao": _KEYWORDS_ESPECIFICACAO,
        "titular": _KEYWORDS_TITULAR,
    }

    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        val = str(cell).lower().strip()
        for field, keywords in mapping.items():
            if any(kw in val for kw in keywords):
                cols[field] = idx
                break

    return cols


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

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

    # Primeira linha: cabeçalho — detectar colunas
    try:
        header_row = next(rows)
    except StopIteration:
        wb.close()
        return records

    cols = _detectar_colunas(header_row)

    for row in rows:
        def _cell(idx: int) -> str | None:
            try:
                v = row[idx]
                return str(v).strip() if v is not None else None
            except IndexError:
                return None

        marca_raw = _cell(cols["marca"])
        apresentacao = _cell(cols["apresentacao"])
        classe_raw = _cell(cols["classe"])
        spec_raw = _cell(cols["especificacao"])
        titular_raw = _cell(cols["titular"])
        processo_raw = _cell(cols["processo"])

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

        # Número do processo: limpar e normalizar (apenas dígitos)
        processo_limpo = ""
        if processo_raw:
            digits = re.sub(r"\D", "", processo_raw)
            if len(digits) >= 6:
                processo_limpo = digits

        records.append({
            "marca": marca_limpa,
            "ncl": ncl,
            "ncl_versao": _parse_ncl_versao(classe_raw),
            "apresentacao": apresentacao or "",
            "especificacao": _parse_especificacao(spec_raw),
            "titular": titular_raw or "",
            "processo": processo_limpo,
        })

    wb.close()
    return records

