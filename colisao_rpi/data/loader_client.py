"""
Carrega e filtra a base de marcas dos clientes da A Província a partir do XLSX.
"""

from __future__ import annotations

import re

import pandas as pd


def _extract_class(val) -> int | None:
    """Extrai o número da classe Nice do campo CLASSE ('Ncl(13) 35' → 35)."""
    if pd.isna(val):
        return None
    m = re.search(r'\b(\d{1,2})\s*$', str(val).strip())
    if m:
        num = int(m.group(1))
        return num if num <= 45 else None
    return None


def load_client_brands(path: str) -> pd.DataFrame:
    """
    Carrega o arquivo XLSX de marcas e aplica os filtros definidos no spec:
    - STATUS != 'Arquivo Morto'
    - APRESENTAÇÃO != 'Figurativa'
    - MARCA preenchida
    - CLASSE_NUM válida (1–45)

    Retorna DataFrame com as colunas relevantes mais a coluna derivada CLASSE_NUM.
    """
    try:
        df = pd.read_excel(path, sheet_name='Planilha1', dtype=str)
    except Exception:
        # Fallback: ler a primeira sheet disponível
        df = pd.read_excel(path, dtype=str)

    # Normalizar nomes de colunas (strip)
    df.columns = [c.strip() for c in df.columns]

    # Filtros obrigatórios
    df = df[df['STATUS'] != 'Arquivo Morto']
    df = df[df['APRESENTAÇÃO'] != 'Figurativa']
    df = df[df['MARCA'].notna()]
    df = df[df['MARCA'].astype(str).str.strip() != '']

    # Derivar número de classe
    df = df.copy()
    df['CLASSE_NUM'] = df['CLASSE'].apply(_extract_class)
    df = df[df['CLASSE_NUM'].notna()]
    df['CLASSE_NUM'] = df['CLASSE_NUM'].astype(int)

    return df.reset_index(drop=True)
