"""
Gold set — pares rotulados pelo especialista para medir precisão/recall.

O arquivo app/data/gold_set.csv deve conter:
    marca_base,ncl_base,spec_base,marca_rpi,ncl_rpi,spec_rpi,colide
onde colide ∈ {S, N} (aceita também sim/nao/1/0/true/false).

O teste é pulado enquanto o arquivo estiver vazio. Quando o especialista
preencher o gold set, ele passa a medir o pipeline (C1–C4, sem IA) a cada
mudança — pré-requisito para calibrar thresholds e fatores (ex.: a lenidade
de homônimos em scoring.py) com segurança.

Thresholds mínimos provisórios via env: GOLD_SET_MIN_PRECISAO e
GOLD_SET_MIN_RECALL (default 0.80).
"""
import csv
import os

import pytest

from app.config import DATA_DIR
from app.pipeline.especificacao import camada3
from app.pipeline.nome_identico import camada1, reclassificar_pos_c3
from app.pipeline.fonetica import camada2
from app.pipeline.scoring import camada4
from app.tests.test_pipeline import _marca

GOLD_SET_PATH = os.path.join(DATA_DIR, "gold_set.csv")

_VERDADEIRO = {"s", "sim", "1", "true", "y", "yes"}


def _carregar_gold_set() -> list[dict]:
    if not os.path.exists(GOLD_SET_PATH):
        return []
    with open(GOLD_SET_PATH, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if (row.get("marca_base") or "").strip()]


def _prever_colisao(row: dict) -> bool:
    """
    Roda C1–C4 para um par do gold set, espelhando o executor: alertas C1
    também passam pelo filtro de afinidade da C3 (decisão de design R1).
    """
    carteira = [_marca(row["marca_base"], int(row["ncl_base"]), row.get("spec_base", ""))]
    rpi = [_marca(row["marca_rpi"], int(row["ncl_rpi"]), row.get("spec_rpi", ""))]

    alertas_c1, rpi_restante = camada1(carteira, rpi)
    if alertas_c1:
        alertas_c1 = camada3(alertas_c1)
        for a in alertas_c1:
            a["camada_deteccao"] = 1
            reclassificar_pos_c3(a)
        return bool(alertas_c1)

    cands_c2, _ = camada2(carteira, rpi_restante)
    cands_c3 = camada3(cands_c2)
    scored = camada4(cands_c3)
    return bool(scored)


def test_gold_set_precisao_recall():
    rows = _carregar_gold_set()
    if not rows:
        pytest.skip("gold set ausente/vazio — aguardando lista rotulada do especialista")

    tp = fp = fn = tn = 0
    erros: list[str] = []

    for row in rows:
        esperado = (row.get("colide") or "").strip().lower() in _VERDADEIRO
        previsto = _prever_colisao(row)
        if previsto and esperado:
            tp += 1
        elif previsto and not esperado:
            fp += 1
            erros.append(f"FALSO POSITIVO: {row['marca_base']} × {row['marca_rpi']}")
        elif not previsto and esperado:
            fn += 1
            erros.append(f"FALSO NEGATIVO: {row['marca_base']} × {row['marca_rpi']}")
        else:
            tn += 1

    precisao = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    matriz = f"TP={tp} FP={fp} FN={fn} TN={tn} precisão={precisao:.2f} recall={recall:.2f}"
    detalhes = "\n".join(erros)
    print(f"\nGold set ({len(rows)} pares): {matriz}\n{detalhes}")

    min_precisao = float(os.getenv("GOLD_SET_MIN_PRECISAO", "0.80"))
    min_recall = float(os.getenv("GOLD_SET_MIN_RECALL", "0.80"))
    assert precisao >= min_precisao, f"Precisão abaixo do mínimo — {matriz}\n{detalhes}"
    assert recall >= min_recall, f"Recall abaixo do mínimo — {matriz}\n{detalhes}"
