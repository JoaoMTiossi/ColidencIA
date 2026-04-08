"""
Parser do XML da RPI (Revista de Propriedade Industrial) do INPI.
Usa iterparse para streaming — arquivo pode ter ~48 MB.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Generator

from ..config import DESPACHOS_OPOSICAO, DESPACHOS_PAN, DESPACHOS_RELEVANTES


def _safe_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _parse_tipo_acao(codigo: str) -> str:
    if codigo in DESPACHOS_OPOSICAO:
        return "OPOSICAO"
    return "PAN"


def _stream_processos(filepath: str) -> Generator[tuple[str, str, ET.Element], None, None]:
    """Yields (rpi_numero, rpi_data, processo_elem) usando iterparse."""
    rpi_numero = ""
    rpi_data = ""
    context = ET.iterparse(filepath, events=("start", "end"))

    current_processo: ET.Element | None = None
    depth = 0

    for event, elem in context:
        if event == "start" and elem.tag == "revista":
            rpi_numero = elem.get("numero", "")
            rpi_data = elem.get("data", "")
        elif event == "start" and elem.tag == "processo":
            current_processo = elem
            depth = 1
        elif current_processo is not None:
            if event == "start":
                depth += 1
            elif event == "end":
                depth -= 1
                if depth == 0 and elem.tag == "processo":
                    yield rpi_numero, rpi_data, elem
                    elem.clear()
                    current_processo = None


def parse_rpi_xml(filepath: str) -> tuple[list[dict], str, str]:
    """
    Parseia o XML da RPI e retorna (records, rpi_numero, rpi_data).

    Cada record é um dict com campos:
        processo, nome_marca, apresentacao, ncl, especificacao,
        despacho_codigo, despacho_nome, tipo_acao, titular, procurador
    """
    records: list[dict] = []
    rpi_numero_global = ""
    rpi_data_global = ""

    for rpi_numero, rpi_data, proc_elem in _stream_processos(filepath):
        if not rpi_numero_global:
            rpi_numero_global = rpi_numero
            rpi_data_global = rpi_data

        processo_num = proc_elem.get("numero", "")

        # Extrair despacho(s)
        despacho_codigo = ""
        despacho_nome = ""
        for d in proc_elem.findall(".//despacho"):
            cod = d.get("codigo", "")
            if cod in DESPACHOS_RELEVANTES:
                despacho_codigo = cod
                despacho_nome = d.get("nome", "")
                break

        if not despacho_codigo:
            continue

        # Extrair nome da marca
        marca_el = proc_elem.find("marca")
        if marca_el is None:
            continue

        nome_el = marca_el.find("nome")
        nome_marca = _safe_text(nome_el)
        if not nome_marca:
            continue

        apresentacao = marca_el.get("apresentacao", "")
        tipo_acao = _parse_tipo_acao(despacho_codigo)

        # Titular(es)
        titulares = [
            t.get("nome-razao-social", "")
            for t in proc_elem.findall(".//titular")
            if t.get("nome-razao-social")
        ]
        titular = titulares[0] if titulares else ""

        # Procurador
        proc_el = proc_elem.find("procurador")
        procurador = _safe_text(proc_el)

        # Classes NCL (pode haver múltiplas)
        classes_found: list[tuple[int, str]] = []
        for cn in proc_elem.findall(".//classe-nice"):
            cod = cn.get("codigo", "")
            try:
                ncl_num = int(cod)
            except (ValueError, TypeError):
                continue
            if 1 <= ncl_num <= 45:
                spec = _safe_text(cn.find("especificacao"))
                classes_found.append((ncl_num, spec))

        if not classes_found:
            # Processo sem classe NCL — usar class 0 (indefinida)
            classes_found = [(0, "")]

        # Criar um registro por classe
        for ncl_num, spec in classes_found:
            records.append({
                "processo": processo_num,
                "nome_marca": nome_marca,
                "apresentacao": apresentacao,
                "ncl": ncl_num,
                "especificacao": spec,
                "despacho_codigo": despacho_codigo,
                "despacho_nome": despacho_nome,
                "tipo_acao": tipo_acao,
                "titular": titular,
                "procurador": procurador,
            })

    return records, rpi_numero_global, rpi_data_global


def parse_rpi_summary(filepath: str) -> tuple[dict[str, int], str, str]:
    """
    Parseia o XML e retorna apenas o resumo de despachos encontrados.
    Muito mais rápido que parse_rpi_xml — usado para exibir no upload.

    Retorna: ({codigo: contagem}, rpi_numero, rpi_data)
    """
    summary: dict[str, int] = {}
    rpi_numero = ""
    rpi_data = ""

    context = ET.iterparse(filepath, events=("start", "end"))

    for event, elem in context:
        if event == "start" and elem.tag == "revista":
            rpi_numero = elem.get("numero", "")
            rpi_data = elem.get("data", "")
        elif event == "end" and elem.tag == "processo":
            marca_el = elem.find("marca")
            has_name = (
                marca_el is not None
                and marca_el.find("nome") is not None
                and (marca_el.find("nome").text or "").strip()
            )
            for d in elem.findall(".//despacho"):
                cod = d.get("codigo", "")
                if cod:
                    key = f"{cod}|{'1' if has_name else '0'}"
                    summary[key] = summary.get(key, 0) + 1
            elem.clear()

    # Reformatar: {codigo: {"total": N, "com_nome": M}}
    result: dict[str, dict] = {}
    for key, count in summary.items():
        cod, has = key.split("|")
        if cod not in result:
            result[cod] = {"total": 0, "com_nome": 0}
        result[cod]["total"] += count
        if has == "1":
            result[cod]["com_nome"] += count

    return result, rpi_numero, rpi_data
