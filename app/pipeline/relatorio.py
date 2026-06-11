"""
Gerador de relatórios Excel e CSV de saída.

Aba 1 "Relatório" — formato de entrega ao cliente (igual ao padrão das agências):
    PROCESSO CLIENTE | MARCA CLIENTE | CLASSE CLIENTE | TITULAR CLIENTE |
    PROCESSO TERCEIRO | MARCA TERCEIRO | CLASSE TERCEIRO |
    TIPO DESPACHO | PRAZO DESPACHO | DESC. DESPACHO

Aba 2 "Análise Técnica" — scores e detalhes internos do algoritmo.
Aba 3 "Resumo" — estatísticas do pipeline.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timedelta

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Paleta e estilos
# ---------------------------------------------------------------------------
_COR_HEADER_BG = "1F3864"   # azul escuro (cabeçalho das colunas)
_COR_HEADER_FG = "FFFFFF"   # branco
_COR_TITULO_BG = "2E75B6"   # azul médio (título do relatório)
_COR_META_BG = "D6E4F0"    # azul muito claro (linhas de metadados)
_COR_OPOSICAO = "FDECEA"   # vermelho claro
_COR_PAN = "FFF3CD"        # amarelo claro

_BORDA_FINA = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Classificação (aba técnica)
_COR_ALTA = "FFCCCC"
_COR_MEDIA = "FFF2CC"
_COR_BAIXA = "CCFFCC"

# ---------------------------------------------------------------------------
# Colunas da aba de entrega ao cliente
# ---------------------------------------------------------------------------
_HEADERS_RELATORIO = [
    "PROCESSO CLIENTE",
    "MARCA CLIENTE",
    "CLASSE CLIENTE",
    "TITULAR CLIENTE",
    "PROCESSO TERCEIRO",
    "MARCA TERCEIRO",
    "CLASSE TERCEIRO",
    "TIPO DESPACHO",
    "PRAZO DESPACHO",
    "DESC. DESPACHO",
]

# Colunas da aba técnica (para uso interno)
_HEADERS_TECNICO = [
    "ID",
    "Tipo Ação",
    "Classificação",
    "Score Final",
    "Marca Base",
    "NCL Base",
    "Especificação Base",
    "Marca RPI",
    "NCL RPI",
    "Especificação RPI",
    "Processo RPI",
    "Despacho",
    "Titular RPI",
    "Camada",
    "Score Nome",
    "Score Fonético",
    "Score Spec",
    "Score Núcleo",
    "Score IA",
    "Justificativa IA",
    "Núcleo Base",
    "Núcleo RPI",
    "Classes Colidem",
    "Sigla?",
    "Desgastado?",
    "Apresent. Base",
    "Apresent. RPI",
    "Nome Próprio?",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ncl_label(ncl: int, versao: int = 12) -> str:
    """Formata a classe NCL como 'NCL(12) 35'."""
    return f"NCL({versao}) {ncl}" if ncl else ""


def _tipo_label(tipo_acao: str) -> str:
    return "OPOSIÇÃO" if tipo_acao == "OPOSICAO" else "PAN"


def _prazo(rpi_data: str, tipo_acao: str) -> str:
    """
    Calcula o prazo legal:
    - OPOSIÇÃO: +60 dias corridos a partir da publicação da RPI
    - PAN: +180 dias corridos a partir da publicação da RPI
    """
    if not rpi_data:
        return ""
    dias = 60 if tipo_acao == "OPOSICAO" else 180
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            base = datetime.strptime(rpi_data.strip(), fmt)
            return (base + timedelta(days=dias)).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return ""


def _despacho_label(codigo: str, nome: str) -> str:
    if codigo and nome:
        return f"{codigo} — {nome}"
    return codigo or nome or ""


def _cor_classificacao(classificacao: str | None) -> PatternFill | None:
    mapa = {
        "ALTA": PatternFill(start_color=_COR_ALTA, end_color=_COR_ALTA, fill_type="solid"),
        "MEDIA": PatternFill(start_color=_COR_MEDIA, end_color=_COR_MEDIA, fill_type="solid"),
        "BAIXA": PatternFill(start_color=_COR_BAIXA, end_color=_COR_BAIXA, fill_type="solid"),
    }
    return mapa.get(classificacao or "")


def _aplicar_estilo_header_col(ws, row_num: int, headers: list[str], bg: str, fg: str = "FFFFFF") -> None:
    fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
    font = Font(bold=True, color=fg, size=10)
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDA_FINA


# ---------------------------------------------------------------------------
# Aba 1 — Relatório (formato de entrega ao cliente)
# ---------------------------------------------------------------------------

def _build_aba_relatorio(
    wb: openpyxl.Workbook,
    resultados: list[dict],
    stats: dict,
) -> None:
    ws = wb.active
    ws.title = "Relatório"

    rpi_num = stats.get("rpi_numero", "")
    rpi_data = stats.get("rpi_data", "")
    total_carteira = stats.get("total_carteira", 0)
    total_rpi = stats.get("total_rpi", 0)
    n_alertas = len(resultados)

    # --- Bloco de cabeçalho (linhas 1–6) ---
    titulo_fill = PatternFill(start_color=_COR_TITULO_BG, end_color=_COR_TITULO_BG, fill_type="solid")
    meta_fill = PatternFill(start_color=_COR_META_BG, end_color=_COR_META_BG, fill_type="solid")
    n_cols = len(_HEADERS_RELATORIO)

    # Linha 1: título
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(row=1, column=1, value="RELATÓRIO DE COLIDÊNCIA DE MARCAS")
    c.fill = titulo_fill
    c.font = Font(bold=True, size=14, color="FFFFFF")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # Linha 2: RPI e data
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    c = ws.cell(row=2, column=1,
                value=f"RPI Nº {rpi_num}  |  Data de publicação: {rpi_data}  |  Emitido em: {datetime.now().strftime('%d/%m/%Y')}")
    c.fill = meta_fill
    c.font = Font(bold=False, size=10)
    c.alignment = Alignment(horizontal="center")

    # Linha 3: volumes
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n_cols)
    c = ws.cell(row=3, column=1,
                value=f"Marcas monitoradas: {total_carteira:,}  |  Marcas verificadas na RPI: {total_rpi:,}  |  Colisões selecionadas: {n_alertas:,}")
    c.fill = meta_fill
    c.font = Font(bold=False, size=10)
    c.alignment = Alignment(horizontal="center")

    # Linha 4: legenda de tipo
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=n_cols)
    c = ws.cell(row=4, column=1,
                value="OPOSIÇÃO = prazo 60 dias  |  PAN (Pedido Administrativo de Nulidade) = prazo 180 dias")
    c.fill = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
    c.font = Font(italic=True, size=9, color="7B6000")
    c.alignment = Alignment(horizontal="center")

    # Linhas 5–6: vazias (separador)
    ws.row_dimensions[5].height = 6
    ws.row_dimensions[6].height = 6

    # --- Cabeçalho das colunas (linha 7) ---
    for col, h in enumerate(_HEADERS_RELATORIO, start=1):
        ws.cell(row=7, column=col, value=h)
    _aplicar_estilo_header_col(ws, 7, _HEADERS_RELATORIO, _COR_HEADER_BG)
    ws.row_dimensions[7].height = 22

    # --- Dados (a partir da linha 8) ---
    fill_oposicao = PatternFill(start_color=_COR_OPOSICAO, end_color=_COR_OPOSICAO, fill_type="solid")
    fill_pan = PatternFill(start_color=_COR_PAN, end_color=_COR_PAN, fill_type="solid")
    font_data = Font(size=10)
    align_centro = Alignment(horizontal="center", vertical="center")
    align_esq = Alignment(horizontal="left", vertical="center")

    for i, r in enumerate(resultados, start=8):
        tipo_acao = r.get("tipo_acao", "")
        tipo = _tipo_label(tipo_acao)
        prazo = _prazo(rpi_data, tipo_acao)

        row_fill = fill_oposicao if tipo_acao == "OPOSICAO" else fill_pan

        valores = [
            r.get("processo_base", ""),
            r.get("marca_base", ""),
            _ncl_label(r.get("ncl_base", 0), r.get("ncl_versao_base", 12)),
            r.get("titular_base", ""),
            r.get("processo_rpi", ""),
            r.get("marca_rpi", ""),
            _ncl_label(r.get("ncl_rpi", 0), 12),
            tipo,
            prazo,
            r.get("despacho_nome", r.get("despacho_codigo", "")),
        ]

        for col, val in enumerate(valores, start=1):
            cell = ws.cell(row=i, column=col, value=val)
            cell.fill = row_fill
            cell.font = font_data
            cell.border = _BORDA_FINA
            # Colunas de texto longo: alinhamento esquerda
            cell.alignment = align_esq if col in (2, 4, 6, 10) else align_centro

    # --- Formatação final ---
    ws.freeze_panes = "A8"
    ws.auto_filter.ref = f"A7:{get_column_letter(n_cols)}{max(7, 7 + len(resultados))}"

    larguras = [18, 35, 14, 35, 18, 35, 14, 12, 14, 45]
    for col, w in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(col)].width = w


# ---------------------------------------------------------------------------
# Aba 2 — Análise Técnica (scores internos)
# ---------------------------------------------------------------------------

def _build_aba_tecnica(
    wb: openpyxl.Workbook,
    resultados: list[dict],
) -> None:
    ws = wb.create_sheet("Análise Técnica")

    ws.append(_HEADERS_TECNICO)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for i, r in enumerate(resultados, start=1):
        tipo_acao = r.get("tipo_acao", "")
        classificacao = r.get("classificacao", "")

        ws.append([
            i,
            _tipo_label(tipo_acao),
            classificacao,
            r.get("score_final") or r.get("score_nome", 0),
            r.get("marca_base", ""),
            r.get("ncl_base", ""),
            (r.get("spec_base", "") or "")[:300],
            r.get("marca_rpi", ""),
            r.get("ncl_rpi", ""),
            (r.get("spec_rpi", "") or "")[:300],
            r.get("processo_rpi", ""),
            _despacho_label(r.get("despacho_codigo", ""), r.get("despacho_nome", "")),
            r.get("titular_rpi", ""),
            r.get("camada_deteccao", ""),
            r.get("score_nome", ""),
            r.get("score_fonetico", ""),
            r.get("score_spec", ""),
            r.get("score_nucleo", ""),
            r.get("score_ia", ""),
            r.get("justificativa_ia", ""),
            r.get("nucleo_base", ""),
            r.get("nucleo_rpi", ""),
            "Sim" if r.get("classes_colidem_flag") else "Não",
            "Sim" if r.get("is_sigla") else "Não",
            "Sim" if r.get("is_desgastado") else "Não",
            r.get("apresentacao_base", ""),
            r.get("apresentacao_rpi", ""),
            "Sim" if r.get("is_nome_proprio_base") or r.get("is_nome_proprio_rpi") else "Não",
        ])

        fill = _cor_classificacao(classificacao)
        if fill:
            ws.cell(row=i + 1, column=3).fill = fill

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"

    larguras = [5, 12, 14, 10, 40, 8, 50, 40, 8, 50, 15, 40, 40, 8,
                10, 10, 10, 10, 10, 60, 30, 30, 12, 8, 10, 14, 14, 12]
    for i, w in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ---------------------------------------------------------------------------
# Aba 3 — Resumo
# ---------------------------------------------------------------------------

def _build_aba_resumo(
    wb: openpyxl.Workbook,
    stats: dict,
) -> None:
    ws = wb.create_sheet("Resumo")

    resumo_data = [
        ["Relatório de Colidência de Marcas"],
        [],
        ["Data de execução", datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Número da RPI", stats.get("rpi_numero", "")],
        ["Data da RPI", stats.get("rpi_data", "")],
        [],
        ["VOLUMES"],
        ["Total carteira de clientes", stats.get("total_carteira", 0)],
        ["Total RPI analisada", stats.get("total_rpi", 0)],
        ["  → Marcas para OPOSIÇÃO", stats.get("total_rpi_oposicao", 0)],
        ["  → Marcas para PAN", stats.get("total_rpi_pan", 0)],
        [],
        ["ALERTAS POR TIPO DE AÇÃO"],
        ["OPOSIÇÃO (prazo 60 dias) — total", stats.get("alertas_oposicao", 0)],
        ["PAN (prazo 180 dias) — total", stats.get("alertas_pan", 0)],
        [],
        ["ALERTAS POR CLASSIFICAÇÃO"],
        ["ALTA", stats.get("alertas_alta", 0)],
        ["MÉDIA", stats.get("alertas_media", 0)],
        ["BAIXA", stats.get("alertas_baixa", 0)],
        ["TOTAL", stats.get("alertas_total", 0)],
        [],
        ["PIPELINE — VOLUME POR CAMADA"],
        ["Camada 1 (Nome idêntico)", stats.get("camada1_count", 0)],
        ["Camada 2 (Fonético)", stats.get("camada2_count", 0)],
        ["Camada 3 (Especificação)", stats.get("camada3_count", 0)],
        ["Camada 4 (Scoring)", stats.get("camada4_count", 0)],
    ]

    for row in resumo_data:
        ws.append(row)

    ws["A1"].font = Font(bold=True, size=14)
    bold_rows = {3, 7, 13, 17, 23}
    for row in ws.iter_rows():
        for cell in row:
            if cell.row in bold_rows and cell.column == 1:
                cell.font = Font(bold=True)

    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 20


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def gerar_xlsx(
    resultados: list[dict],
    stats: dict,
    output_path: str,
) -> str:
    """
    Gera o relatório Excel com três abas.
    Retorna o caminho do arquivo gerado.
    """
    wb = openpyxl.Workbook()
    _build_aba_relatorio(wb, resultados, stats)
    _build_aba_tecnica(wb, resultados)
    _build_aba_resumo(wb, stats)
    wb.save(output_path)
    return output_path


def gerar_csv_bytes(resultados: list[dict], stats: dict | None = None) -> bytes:
    """Gera o CSV de entrega ao cliente como bytes."""
    rpi_data = (stats or {}).get("rpi_data", "")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_HEADERS_RELATORIO)

    for r in resultados:
        tipo_acao = r.get("tipo_acao", "")
        writer.writerow([
            r.get("processo_base", ""),
            r.get("marca_base", ""),
            _ncl_label(r.get("ncl_base", 0), r.get("ncl_versao_base", 12)),
            r.get("titular_base", ""),
            r.get("processo_rpi", ""),
            r.get("marca_rpi", ""),
            _ncl_label(r.get("ncl_rpi", 0), 12),
            _tipo_label(tipo_acao),
            _prazo(rpi_data, tipo_acao),
            r.get("despacho_nome", r.get("despacho_codigo", "")),
        ])

    return output.getvalue().encode("utf-8-sig")
