"""
Parseia o XML da RPI (Revista de Propriedade Industrial) do INPI.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def _safe_int(val: str) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def load_rpi_records(path: str) -> tuple[list[dict], str, str]:
    """
    Parseia o XML da RPI e retorna:
        (records, rpi_numero, rpi_data)

    records: lista de dicts com as chaves:
        processo, data_deposito, nome, apresentacao,
        titulares, classes, despachos, especificacoes

    Apenas processos com <nome> de marca são incluídos.
    Figurativas são descartadas.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    rpi_numero = root.get('numero', '')
    rpi_data = root.get('data', '')

    records: list[dict] = []

    for p in root.findall('processo'):
        marca_el = p.find('marca')
        if marca_el is None:
            continue

        nome_el = marca_el.find('nome')
        if nome_el is None or not (nome_el.text or '').strip():
            continue

        apresentacao = marca_el.get('apresentacao', '')
        if apresentacao == 'Figurativa':
            continue

        titulares = [
            t.get('nome-razao-social', '')
            for t in p.findall('.//titular')
        ]

        classes: list[int] = []
        especificacoes: dict[str, str] = {}
        for c in p.findall('.//classe-nice'):
            cod = c.get('codigo', '')
            n = _safe_int(cod)
            if n is not None and 1 <= n <= 45:
                classes.append(n)
                especificacoes[cod] = c.findtext('especificacao', '')

        despachos = [
            (d.get('codigo', ''), d.get('nome', ''))
            for d in p.findall('.//despacho')
        ]

        records.append({
            'processo': p.get('numero', ''),
            'data_deposito': p.get('data-deposito', ''),
            'nome': nome_el.text.strip(),
            'apresentacao': apresentacao,
            'titulares': titulares,
            'classes': classes,
            'despachos': despachos,
            'especificacoes': especificacoes,
        })

    return records, rpi_numero, rpi_data
