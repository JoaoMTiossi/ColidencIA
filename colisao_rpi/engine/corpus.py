"""
FASE 1 — Corpus de frequência por classe.

Constrói e persiste a contagem de tokens por classe Nice a partir de registros RPI.
Acumula a cada nova RPI processada para fortalecer o sinal de genericidade.

Formato corpus_freq.json:
{
  "_N": {"35": 4821, "36": 312, ...},   # nº de marcas por classe
  "35": {"TECNOLOGIA": 68, "SISTEMAS": 12, ...},
  "36": {"SEGUROS": 45, "CORRETORA": 27, ...},
  ...
}
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

from .normalize import normalize

_DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'corpus_freq.json'
)


def build_corpus(rpi_records: list[dict]) -> dict:
    """
    Constrói corpus de frequência a partir de uma lista de registros RPI.
    Retorna dict no formato descrito no módulo docstring.
    """
    N: dict[str, int] = defaultdict(int)       # classe → nº marcas
    freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in rpi_records:
        nome    = r.get('nome', '')
        classes = r.get('classes', [])
        if not nome or not classes:
            continue

        tokens = {t for t in normalize(nome).split() if len(t) >= 3}

        for cls in set(classes):
            key = str(cls)
            N[key] += 1
            for tok in tokens:
                freq[key][tok] += 1

    result: dict = {'_N': dict(N)}
    for cls, counts in freq.items():
        result[cls] = dict(counts)
    return result


def load_corpus(path: str = _DEFAULT_PATH) -> dict:
    """Carrega corpus do disco; retorna dict vazio se arquivo não existir."""
    if not os.path.exists(path):
        return {'_N': {}}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def update_corpus(rpi_records: list[dict], path: str = _DEFAULT_PATH) -> dict:
    """
    Soma os dados de rpi_records ao corpus existente e persiste.
    Retorna o corpus atualizado.
    """
    existing = load_corpus(path)
    new      = build_corpus(rpi_records)

    merged: dict = {'_N': {}}

    all_classes = set(existing.keys()) | set(new.keys()) - {'_N'}
    for cls in all_classes:
        merged[cls] = {}
        for tok, cnt in existing.get(cls, {}).items():
            merged[cls][tok] = cnt
        for tok, cnt in new.get(cls, {}).items():
            merged[cls][tok] = merged[cls].get(tok, 0) + cnt

    # Mesclar contagens _N
    for cls, n in existing.get('_N', {}).items():
        merged['_N'][cls] = n
    for cls, n in new.get('_N', {}).items():
        merged['_N'][cls] = merged['_N'].get(cls, 0) + n

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, separators=(',', ':'))

    return merged


def corpus_stats(corpus: dict) -> None:
    """Imprime estatísticas resumidas do corpus."""
    N = corpus.get('_N', {})
    total_marcas = sum(N.values())
    total_tokens = sum(len(v) for k, v in corpus.items() if k != '_N')
    print(f'Corpus: {len(N)} classes, {total_marcas} marcas, {total_tokens} tokens únicos')
    print('Top classes:', sorted(N.items(), key=lambda x: -x[1])[:10])
