"""
Constrói (ou atualiza) o artefato vocab_descritivo_corpus.json a partir de
arquivos da carteira + RPI sem precisar rodar o pipeline completo.

Uso:
    python -m app.scripts.build_vocab_corpus \
        --carteira <path.xlsx> \
        --rpi <path.xml> [--rpi <path2.xml> ...]

O artefato é salvo em app/data/vocab_descritivo_corpus.json e lido
automaticamente por tokens_distintivos() (via _vocab_corpus).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import (
    CORPUS_LIMIAR_ABS,
    CORPUS_LIMIAR_FREQ,
    CORPUS_MIN_AMOSTRA_CLASSE,
    DATA_DIR,
)
from app.parsers.parse_excel import parse_excel
from app.parsers.parse_xml import parse_rpi_xml
from app.utils.normalizacao import normalizar_base


def _nome(m: dict) -> str:
    return m.get("marca") or m.get("nome_marca") or ""


def construir(carteira_paths: list[str], rpi_paths: list[str]) -> None:
    marcas: list[dict] = []
    for p in carteira_paths:
        print(f"  carteira: {os.path.basename(p)}", flush=True)
        marcas.extend(parse_excel(p))
    for p in rpi_paths:
        print(f"  rpi: {os.path.basename(p)}", flush=True)
        raw, num, dt = parse_rpi_xml(p)
        print(f"    RPI {num} ({dt}): {len(raw)} marcas", flush=True)
        marcas.extend(raw)

    print(f"  total de marcas lidas: {len(marcas)}", flush=True)

    termos: collections.Counter[tuple[int, str]] = collections.Counter()
    classes: collections.Counter[int] = collections.Counter()
    for m in marcas:
        ncl = int(m.get("ncl") or 0)
        if ncl <= 0:
            continue
        toks = {t for t in normalizar_base(_nome(m)).split() if len(t) >= 3}
        for t in toks:
            termos[(ncl, t)] += 1
        classes[ncl] += 1

    print(f"  classes com marcas: {len(classes)}", flush=True)

    vocab: dict[str, list[str]] = {}
    for ncl, total in classes.items():
        if total < CORPUS_MIN_AMOSTRA_CLASSE:
            continue
        min_abs = max(CORPUS_LIMIAR_ABS, int(total * CORPUS_LIMIAR_FREQ))
        terms = sorted(
            [t for (n, t), c in termos.items() if n == ncl and c >= min_abs],
            key=lambda t: -termos[(ncl, t)],
        )
        if terms:
            vocab[str(ncl)] = terms

    path = os.path.join(DATA_DIR, "vocab_descritivo_corpus.json")
    json.dump(vocab, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\nartefato gerado: {path}")
    print(f"  classes: {len(vocab)}  |  total termos: {sum(len(v) for v in vocab.values())}")
    for c in sorted(vocab, key=lambda x: -len(vocab[x]))[:8]:
        print(f"  classe {c} ({len(vocab[c])} termos): {vocab[c][:20]}")

    # Invalida caches do processo atual (útil quando importado via Python)
    try:
        from app.utils.distintividade import _vocab_corpus, _vocab_descritivo
        _vocab_corpus.cache_clear()
        _vocab_descritivo.cache_clear()
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--carteira", required=True, nargs="+")
    parser.add_argument("--rpi", required=True, nargs="+")
    args = parser.parse_args()
    construir(args.carteira, args.rpi)
