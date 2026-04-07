"""
Entry point — CLI do sistema de detecção de colidência de marcas.

Uso:
    python main.py --rpi RM2882.xml --marcas Relatorio_Detalhado_Marcas.xlsx

    python main.py --rpi RM2882.xml --marcas marcas.xlsx --output ./relatorios/

    python main.py --rpi RM2882.xml --marcas marcas.xlsx \\
        --threshold 0.75 \\
        --verbose \\
        --debug-pair "INSPIRE,INSPIRE PILATES"
"""

from __future__ import annotations

import os
import sys

import click

from colisao_rpi.config import DEFAULT_OUTPUT_DIR, THRESHOLD_SIMILAR
from colisao_rpi.data.loader_client import load_client_brands
from colisao_rpi.data.loader_rpi import load_rpi_records
from colisao_rpi.engine.rules import run_collision_detection
from colisao_rpi.output.report import generate_report


@click.command()
@click.option('--rpi',      required=True, type=click.Path(exists=True), help='Arquivo XML da RPI (ex: RM2882.xml)')
@click.option('--marcas',   required=True, type=click.Path(exists=True), help='Planilha XLSX de marcas dos clientes')
@click.option('--output',   default=DEFAULT_OUTPUT_DIR, show_default=True, help='Diretório de saída do relatório')
@click.option('--threshold', default=THRESHOLD_SIMILAR, show_default=True, type=float,
              help='Threshold de similaridade (0.0–1.0). Padrão: 0.75')
@click.option('--verbose',   is_flag=True, default=False, help='Log detalhado de cada par comparado')
@click.option('--debug-pair', default=None,
              help='Testar par específico (ex: "INSPIRE,INSPIRE PILATES")')
def main(rpi, marcas, output, threshold, verbose, debug_pair):
    """Sistema de detecção de colidência de marcas — A Província Marcas e Patentes."""

    # Validar threshold
    if not (0.0 < threshold <= 1.0):
        click.echo(f"Erro: --threshold deve ser entre 0.0 e 1.0 (recebido: {threshold})", err=True)
        sys.exit(1)

    # Criar diretório de saída se necessário
    os.makedirs(output, exist_ok=True)

    # --- Injetar threshold customizado (afeta módulo de config em runtime) ---
    import colisao_rpi.config as cfg
    cfg.THRESHOLD_SIMILAR = threshold

    # --- Carregar dados ---
    click.echo(f"Carregando base de marcas: {marcas}")
    df_client = load_client_brands(marcas)
    click.echo(f"  → {len(df_client)} marcas válidas carregadas")

    click.echo(f"Carregando RPI: {rpi}")
    rpi_records, rpi_numero, rpi_data = load_rpi_records(rpi)
    click.echo(f"  → RPI {rpi_numero} ({rpi_data}) — {len(rpi_records)} marcas com nome")

    # --- Detecção ---
    click.echo("Iniciando detecção de colidências...")
    results = run_collision_detection(
        df_client=df_client,
        rpi_records=rpi_records,
        rpi_numero=rpi_numero,
        rpi_data=rpi_data,
        verbose=verbose,
        debug_pair=debug_pair,
    )
    click.echo(f"  → {len(results)} colidências encontradas")

    if not results:
        click.echo("Nenhuma colidência detectada. Relatório não gerado.")
        return

    # --- Gerar relatório ---
    output_path = generate_report(
        results=results,
        rpi_numero=rpi_numero,
        rpi_data=rpi_data,
        total_rpi=len(rpi_records),
        total_clientes=len(df_client),
        output_dir=output,
    )
    click.echo(f"Relatório salvo: {output_path}")
    click.echo(f"Total de colidências: {len(results)}")


if __name__ == '__main__':
    main()
