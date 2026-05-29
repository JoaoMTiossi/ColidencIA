"""
Calibração de thresholds do pipeline de colidência.

Dois modos de uso:

  # Recall-only usando gold-set de Excel (pares que DEVEM ser detectados)
  python -m app.tests.calibrar --excel /caminho/para/rpis/

  # Precision+Recall+F1 usando CSV com labels
  python -m app.tests.calibrar --csv gold_labels.csv

Formato do CSV com labels:
  marca_base,ncl_base,spec_base,marca_rpi,ncl_rpi,spec_rpi,rotulo
  rotulo: ENTRAR | MONITORAR | NAO_ENTRAR

Thresholds varridos (via --sweep):
  - THRESHOLD_FONETICO: 0.55–0.75 (step 0.05)
  - gate_dist (md mínimo): 0.55–0.80 (step 0.05)
  - THRESHOLD_SCORE_FINAL: 0.45–0.65 (step 0.05)
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from collections import defaultdict
from itertools import product
from typing import Any

# ---------------------------------------------------------------------------
# Importações do pipeline
# ---------------------------------------------------------------------------
from ..config import (
    CLASSES_CAUTELA_ALTA, ELEMENTOS_DESGASTADOS, FATOR_CAUTELA,
    PESO_AFINIDADE_SPEC, PESO_BONUS, PESO_FONETICA, PESO_NUCLEO_MARCARIO,
    PESO_REGRA_INVERSA, PESO_SIMILARIDADE_NOME, PESO_TIPO_MARCA,
    THRESHOLD_ESPECIFICACAO, THRESHOLD_FONETICO, THRESHOLD_SCORE_FINAL,
)
from ..pipeline.especificacao import _afinidade_classes, _afinidade_correlatas
from ..pipeline.fonetica import _classes_elegiveis, _levenshtein_1, _score_fonetico
from ..pipeline.preprocessor import preprocessar
from ..pipeline.scoring import _af_minima, _score_superficie_2d
from ..utils.distintividade import match_distintivo, tokens_distintivos
from ..utils.metaphone_ptbr import metaphone_ptbr
from ..utils.normalizacao import normalizar_base, normalizar_para_hash
from ..utils.similaridade import jaro_winkler


# ---------------------------------------------------------------------------
# Carregadores
# ---------------------------------------------------------------------------

def _parse_ncl(v: Any) -> int:
    if v is None:
        return 0
    m = re.search(r"(\d+)\s*$", str(v).strip())
    return int(m.group(1)) if m else 0


def carregar_excel(pasta: str) -> list[dict]:
    """Carrega pares positivos (gold-set) de arquivos Excel de RPI."""
    import openpyxl
    arquivos = sorted(glob.glob(f"{pasta}/*.xlsx") + glob.glob(f"{pasta}/*.XLSX"))
    if not arquivos:
        sys.exit(f"Nenhum .xlsx encontrado em {pasta!r}")
    pares, vistos = [], set()
    for f in arquivos:
        wb = openpyxl.load_workbook(f, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        hdr = next(
            (i for i, r in enumerate(rows[:12]) if r and r[0] == "PROCESSO CLIENTE"),
            7,
        )
        for r in rows[hdr + 1:]:
            if not r[1]:
                continue
            mc = str(r[1]).strip()
            ncl_c = _parse_ncl(r[2])
            mt = str(r[5]).strip() if r[5] else ""
            ncl_t = _parse_ncl(r[6])
            if not mc or not mt:
                continue
            key = (mc.lower(), ncl_c, mt.lower(), ncl_t)
            if key in vistos:
                continue
            vistos.add(key)
            pares.append({
                "marca_base": mc, "ncl_base": ncl_c, "spec_base": "",
                "marca_rpi": mt, "ncl_rpi": ncl_t, "spec_rpi": "",
                "rotulo": "ENTRAR",
            })
    return pares


def carregar_csv(path: str) -> list[dict]:
    """Carrega pares com labels de um CSV."""
    pares = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rotulo = row.get("rotulo", "").strip().upper()
            if rotulo not in ("ENTRAR", "MONITORAR", "NAO_ENTRAR"):
                continue
            pares.append({
                "marca_base": row.get("marca_base", ""),
                "ncl_base": int(row.get("ncl_base", 0) or 0),
                "spec_base": row.get("spec_base", ""),
                "marca_rpi": row.get("marca_rpi", ""),
                "ncl_rpi": int(row.get("ncl_rpi", 0) or 0),
                "spec_rpi": row.get("spec_rpi", ""),
                "rotulo": rotulo,
            })
    return pares


# ---------------------------------------------------------------------------
# Simulador de pipeline
# ---------------------------------------------------------------------------

def _blocking_ok(base: dict, rpi_p: dict) -> bool:
    """Simula blocking C2 (full-code, bigrama, token distintivo, token desgastado)."""
    pa = (base.get("codigo_fonetico") or "")[:4]
    pb = (rpi_p.get("codigo_fonetico") or "")[:4]
    if pa and pb and (_levenshtein_1(pa, pb) or pa == pb):
        return True
    bg_a: set = base.get("bigrams_set", set())
    bg_b: set = rpi_p.get("bigrams_set", set())
    union = bg_a | bg_b
    if union and len(bg_a & bg_b) / len(union) >= 0.30:
        return True
    ncl_a, ncl_b = base.get("ncl", 0), rpi_p.get("ncl", 0)
    nm_a, nm_b = base.get("nome_normalizado", ""), rpi_p.get("nome_normalizado", "")
    tok_a = {metaphone_ptbr(t) for t in tokens_distintivos(nm_a, ncl_a) if t}
    tok_b = {metaphone_ptbr(t) for t in tokens_distintivos(nm_b, ncl_b) if t}
    if tok_a & tok_b:
        return True
    des_a = {
        metaphone_ptbr(t) for t in normalizar_base(nm_a).split()
        if len(t) >= 2 and t in ELEMENTOS_DESGASTADOS and metaphone_ptbr(t)
    }
    des_b = {
        metaphone_ptbr(t) for t in normalizar_base(nm_b).split()
        if len(t) >= 2 and t in ELEMENTOS_DESGASTADOS and metaphone_ptbr(t)
    }
    if des_a & des_b:
        return True
    return False


def simular(
    par: dict,
    thr_fonetico: float = THRESHOLD_FONETICO,
    gate_dist: float = 0.70,
    thr_score: float = THRESHOLD_SCORE_FINAL,
) -> tuple[bool, str]:
    """Simula o pipeline completo e retorna (encontrado, motivo_falha)."""
    base = preprocessar({"marca": par["marca_base"], "ncl": par["ncl_base"],
                         "especificacao": par.get("spec_base", "")})
    rpi_p = preprocessar({"nome_marca": par["marca_rpi"], "ncl": par["ncl_rpi"],
                           "especificacao": par.get("spec_rpi", "")})
    ncl_a, ncl_b = par["ncl_base"], par["ncl_rpi"]

    # C1 — nome/núcleo idêntico
    if normalizar_para_hash(base["nome_normalizado"]) == normalizar_para_hash(rpi_p["nome_normalizado"]):
        return True, ""
    nuc_a = normalizar_para_hash(base["nucleo"])
    nuc_b = normalizar_para_hash(rpi_p["nucleo"])
    if nuc_a and nuc_a == nuc_b and not base["is_marca_generica"] and not rpi_p["is_marca_generica"]:
        return True, ""

    # C2 — classe elegível
    if ncl_a not in _classes_elegiveis(ncl_b):
        return False, f"C2:classe_inelegivel({ncl_a}x{ncl_b})"

    # C2 — blocking
    if not _blocking_ok(base, rpi_p):
        return False, "C2:blocking"

    # C2 — score fonético
    s_fon = _score_fonetico(base, rpi_p)
    if s_fon < thr_fonetico:
        return False, f"C2:fon={s_fon:.3f}"

    # C3 — afinidade de especificação
    s_spec = _afinidade_classes(ncl_a, ncl_b)
    if s_spec < THRESHOLD_ESPECIFICACAO:
        return False, f"C3:spec={s_spec:.3f}"

    # C4 — scoring composto
    s_nome = jaro_winkler(base["nome_normalizado"], rpi_p["nome_normalizado"])
    s_nucleo = jaro_winkler(
        base.get("nucleo_distintivo") or base["nucleo"],
        rpi_p.get("nucleo_distintivo") or rpi_p["nucleo"],
    )
    af_classes = (
        _afinidade_correlatas(ncl_a, ncl_b) if ncl_a != ncl_b else (0.95 if ncl_a > 0 else 0.0)
    )
    bonus = 0.8 * af_classes

    if base.get("is_desgastado") and rpi_p.get("is_desgastado") and af_classes == 0.0 and ncl_a != ncl_b:
        return False, "C4:desgastado_sem_afinidade"

    peso_nome, peso_spec = PESO_SIMILARIDADE_NOME, PESO_AFINIDADE_SPEC
    if base.get("is_marca_generica") or rpi_p.get("is_marca_generica"):
        peso_nome -= 0.10
        peso_spec += 0.10
    if base.get("is_sigla") or rpi_p.get("is_sigla"):
        s_fon_adj = 0.0
        peso_nome += 0.10
    else:
        s_fon_adj = s_fon

    s_sim = max(s_nome, s_nucleo, s_fon_adj)
    s_af = max(s_spec, af_classes)
    if s_af < _af_minima(s_sim):
        return False, f"C4:regra_inversa(sim={s_sim:.2f},af={s_af:.2f})"

    score = min(
        1.0,
        s_nome * peso_nome + s_spec * peso_spec + s_nucleo * PESO_NUCLEO_MARCARIO
        + s_fon_adj * PESO_FONETICA + 0.7 * PESO_TIPO_MARCA + bonus * PESO_BONUS,
    )

    if (base.get("is_marca_generica") and rpi_p.get("is_marca_generica")
            and s_nome < 0.92 and not (ncl_a == ncl_b and s_nucleo >= 0.95)):
        return False, "C4:ambos_genericos"

    md = match_distintivo(par["marca_base"], par["marca_rpi"], ncl_a, ncl_b)
    if md is None:
        if s_nome < 0.80 and s_fon < 0.85:
            return False, f"C4:dist_none(s_nome={s_nome:.2f})"
    elif md < gate_dist and s_nome < 0.90:
        if s_fon < 0.85:
            return False, f"C4:dist_low(md={md:.2f})"
    elif md < 0.85:
        score *= 0.85

    score_ri = _score_superficie_2d(s_sim, s_af)
    score = (1.0 - PESO_REGRA_INVERSA) * score + PESO_REGRA_INVERSA * score_ri

    threshold = thr_score
    if ncl_a in CLASSES_CAUTELA_ALTA or ncl_b in CLASSES_CAUTELA_ALTA:
        threshold *= FATOR_CAUTELA

    if score >= threshold:
        return True, ""
    return False, f"C4:score={score:.3f}<{threshold:.3f}"


# ---------------------------------------------------------------------------
# Análise e varredura
# ---------------------------------------------------------------------------

def analisar(pares: list[dict], thr_fonetico: float, gate_dist: float, thr_score: float) -> dict:
    """Roda o simulador e retorna métricas."""
    tp = fp = tn = fn = 0
    misses_por_causa: dict[str, int] = defaultdict(int)

    for par in pares:
        positivo = par["rotulo"] in ("ENTRAR", "MONITORAR")
        encontrou, motivo = simular(par, thr_fonetico, gate_dist, thr_score)

        if positivo and encontrou:
            tp += 1
        elif positivo and not encontrou:
            fn += 1
            chave = motivo.split("(")[0].split("=")[0]
            misses_por_causa[chave] += 1
        elif not positivo and encontrou:
            fp += 1
        else:
            tn += 1

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "recall": recall, "precision": precision, "f1": f1,
        "misses_por_causa": dict(misses_por_causa),
    }


def varrer(pares: list[dict]) -> None:
    """Varredura de thresholds e exibição dos melhores resultados."""
    thrs_fon = [0.55, 0.60, 0.65, 0.70]
    gates_dist = [0.60, 0.65, 0.70, 0.75, 0.80]
    thrs_score = [0.45, 0.50, 0.55, 0.60, 0.65]

    tem_labels = any(p["rotulo"] == "NAO_ENTRAR" for p in pares)

    resultados = []
    combos = list(product(thrs_fon, gates_dist, thrs_score))
    print(f"Varrendo {len(combos)} combinações de threshold...")

    for tf, gd, ts in combos:
        m = analisar(pares, tf, gd, ts)
        resultados.append((tf, gd, ts, m))

    if tem_labels:
        # Ordenar por F1 decrescente
        resultados.sort(key=lambda x: x[3]["f1"], reverse=True)
        print(f"\n{'Fon':>5} {'Dist':>5} {'Score':>6}  {'Recall':>7} {'Prec':>7} {'F1':>7}  {'TP':>5} {'FP':>5} {'FN':>5}")
        print("-" * 65)
        for tf, gd, ts, m in resultados[:15]:
            print(
                f"{tf:>5.2f} {gd:>5.2f} {ts:>6.2f}  "
                f"{m['recall']:>7.1%} {m['precision']:>7.1%} {m['f1']:>7.1%}  "
                f"{m['tp']:>5} {m['fp']:>5} {m['fn']:>5}"
            )
        best = resultados[0]
        print(f"\n>>> Melhor F1: fon={best[0]}, gate_dist={best[1]}, score={best[2]} → F1={best[3]['f1']:.1%}")
    else:
        # Sem labels: ordenar por recall
        resultados.sort(key=lambda x: x[3]["recall"], reverse=True)
        print(f"\n{'Fon':>5} {'Dist':>5} {'Score':>6}  {'Recall':>7}  {'TP':>5} {'FN':>5}")
        print("-" * 50)
        for tf, gd, ts, m in resultados[:15]:
            print(
                f"{tf:>5.2f} {gd:>5.2f} {ts:>6.2f}  "
                f"{m['recall']:>7.1%}  "
                f"{m['tp']:>5} {m['fn']:>5}"
            )
        best = resultados[0]
        print(f"\n>>> Melhor recall: fon={best[0]}, gate_dist={best[1]}, score={best[2]} → recall={best[3]['recall']:.1%}")

    # Distribuição de causas com thresholds padrão
    print("\n--- Distribuição de misses (thresholds padrão) ---")
    m_default = analisar(pares, THRESHOLD_FONETICO, 0.70, THRESHOLD_SCORE_FINAL)
    for causa, cnt in sorted(m_default["misses_por_causa"].items(), key=lambda x: -x[1]):
        print(f"  {causa}: {cnt}")


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Calibrar thresholds do pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--excel", metavar="PASTA",
                       help="Pasta com arquivos .xlsx do gold-set (pares positivos)")
    group.add_argument("--csv", metavar="ARQUIVO",
                       help="CSV com labels (ENTRAR|MONITORAR|NAO_ENTRAR)")
    parser.add_argument("--sweep", action="store_true",
                        help="Varrer combinações de threshold e reportar melhores")
    args = parser.parse_args(argv)

    if args.excel:
        pares = carregar_excel(args.excel)
    else:
        pares = carregar_csv(args.csv)

    print(f"Pares carregados: {len(pares)}")
    positivos = sum(1 for p in pares if p["rotulo"] in ("ENTRAR", "MONITORAR"))
    negativos = sum(1 for p in pares if p["rotulo"] == "NAO_ENTRAR")
    print(f"  Positivos: {positivos}  |  Negativos: {negativos}\n")

    if args.sweep:
        varrer(pares)
    else:
        m = analisar(pares, THRESHOLD_FONETICO, 0.70, THRESHOLD_SCORE_FINAL)
        print("=== Métricas com thresholds atuais ===")
        print(f"  THRESHOLD_FONETICO   = {THRESHOLD_FONETICO}")
        print(f"  gate_dist            = 0.70")
        print(f"  THRESHOLD_SCORE_FINAL = {THRESHOLD_SCORE_FINAL}")
        print(f"\n  Recall   : {m['recall']:.1%}  ({m['tp']} acertos / {m['tp']+m['fn']} positivos)")
        if negativos:
            print(f"  Precision: {m['precision']:.1%}  ({m['tp']} acertos / {m['tp']+m['fp']} detectados)")
            print(f"  F1       : {m['f1']:.1%}")
        print(f"\n  Falsos negativos: {m['fn']}")
        if negativos:
            print(f"  Falsos positivos: {m['fp']}")
        print("\n  Misses por causa:")
        for causa, cnt in sorted(m["misses_por_causa"].items(), key=lambda x: -x[1]):
            print(f"    {causa}: {cnt}")


if __name__ == "__main__":
    main()
