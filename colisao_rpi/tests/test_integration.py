"""
Teste de integração ponta-a-ponta usando dados sintéticos.

Simula uma execução completa: base de clientes + RPI fictícia → relatório.
"""

from __future__ import annotations

import os
import tempfile

import pandas as pd
import pytest

from colisao_rpi.engine.rules import run_collision_detection
from colisao_rpi.output.report import generate_report


def _make_client_df(rows: list[dict]) -> pd.DataFrame:
    """Cria um DataFrame mínimo de clientes para testes."""
    defaults = {
        'PROCESSO': '123456789',
        'MARCA': 'TESTE',
        'CLASSE': 'Ncl(13) 35',
        'APRESENTAÇÃO': 'Nominativa',
        'NATUREZA': 'Serviço',
        'ESPECIFICAÇÃO': '35 - servicos.',
        'TITULAR': 'EMPRESA TESTE LTDA (BR/SP)',
        'PASTA': '99999 - P1',
        'SITUACAO': 'PEDIDO',
        'STATUS': 'Controlado',
        'P / 3º': 'P',
        'CLASSE_NUM': 35,
    }
    records = []
    for i, r in enumerate(rows):
        rec = {**defaults, **r}
        rec.setdefault('PROCESSO', str(900000000 + i))
        records.append(rec)
    return pd.DataFrame(records)


def _make_rpi_record(nome: str, classes: list[int], processo: str = '999999999') -> dict:
    return {
        'processo': processo,
        'data_deposito': '01/01/2026',
        'nome': nome,
        'apresentacao': 'Nominativa',
        'titulares': ['TERCEIRO LTDA'],
        'classes': classes,
        'despachos': [('IPAS009', 'Publicação para oposição')],
        'especificacoes': {str(c): 'Especificação de teste.' for c in classes},
    }


class TestIntegration:
    def test_identica_detectada(self):
        df = _make_client_df([{'MARCA': 'NOVA GERACAO', 'CLASSE_NUM': 44}])
        rpi = [_make_rpi_record('NOVA GERACAO', [41])]
        results = run_collision_detection(df, rpi, '2882', '31/03/2026')
        assert len(results) == 1
        assert results[0]['_REGRA'] == 'R1-IDENTICA'

    def test_sem_colisao_ramos_distintos(self):
        df = _make_client_df([{'MARCA': 'MITTI', 'CLASSE_NUM': 25}])
        rpi = [_make_rpi_record('MITTI GELATO', [30])]
        results = run_collision_detection(df, rpi, '2882', '31/03/2026')
        assert len(results) == 0

    def test_nucleo_identico_classes_afins(self):
        df = _make_client_df([{'MARCA': 'INSPIRE STUDIO DE PILATES E LPF', 'CLASSE_NUM': 41}])
        rpi = [_make_rpi_record('INSPIRE PILATES', [35])]
        results = run_collision_detection(df, rpi, '2882', '31/03/2026')
        assert len(results) == 1

    def test_mesmo_titular_nao_colide(self):
        df = _make_client_df([{
            'MARCA': 'MINHA MARCA',
            'CLASSE_NUM': 35,
            'TITULAR': 'EMPRESA TESTE LTDA (BR/SP)',
        }])
        rpi = [_make_rpi_record('MINHA MARCA', [35])]
        # Ajustar titular da RPI para ser idêntico ao do cliente
        rpi[0]['titulares'] = ['EMPRESA TESTE LTDA']
        results = run_collision_detection(df, rpi, '2882', '31/03/2026')
        assert len(results) == 0

    def test_multiplos_clientes_multiplos_rpi(self):
        df = _make_client_df([
            {'MARCA': 'ROTTAS', 'CLASSE_NUM': 37},
            {'MARCA': 'INSPIRE STUDIO', 'CLASSE_NUM': 41},
            {'MARCA': 'MARCA IRRELEVANTE', 'CLASSE_NUM': 1},
        ])
        rpi = [
            _make_rpi_record('ROTA CALHAS', [37], '111'),
            _make_rpi_record('INSPIRE PILATES', [35], '222'),
            _make_rpi_record('OUTRA EMPRESA', [20], '333'),
        ]
        results = run_collision_detection(df, rpi, '2882', '31/03/2026')
        # Pelo menos ROTTAS×ROTA CALHAS e INSPIRE×INSPIRE devem colidir
        assert len(results) >= 2

    def test_generate_report_creates_file(self):
        results = [{
            'PROCESSO CLIENTE': '123',
            'MARCA CLIENTE': 'TESTE',
            'CLASSE CLIENTE': 'NCL(13) 35',
            'TITULAR CLIENTE': 'EMPRESA LTDA',
            'PROCESSO TERCEIRO': '456',
            'MARCA TERCEIRO': 'TESTE SIMILAR',
            'CLASSE TERCEIRO': 'NCL(13) 35',
            '_REGRA': 'R1-IDENTICA',
            '_SCORE': 1.0,
            '_DESPACHOS': 'IPAS009-Publicação',
            '_SITUACAO_CLI': 'PEDIDO',
            '_PASTA': '99999 - P1',
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_report(results, '2882', '31/03/2026', 100, 500, tmpdir)
            assert os.path.exists(path)
            assert path.endswith('.xlsx')
