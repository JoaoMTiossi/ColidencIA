"""
Gera a matriz de afinidade NCL x NCL a partir da Lista NICE 13 oficial.

Uso:
    python -m app.utils.gerar_correlatas_nice

Entrada: app/data/nice_classificacao.csv (10.448 descrições oficiais)
Saída:   app/data/especificacoes_correlatas.csv  (usado pela Camada 3)
         app/data/correlatas_nice.csv             (matriz crua, para auditoria)

Estratégia:
1. Agrupa descrições oficiais por classe NCL (1-45).
2. Concatena descrições de cada classe em um "documento por classe".
3. Vetoriza com TF-IDF (ngram 1-2, stop-words PT mínimas).
4. Calcula matriz 45x45 de cosseno entre documentos.
5. Renormaliza cossenos para a escala [0.40, 0.95] usada pelo pipeline.
6. Aplica corte mais rígido entre classes de serviço (35-45) para
   compensar ruído vocabular ("serviços de", "consultoria", etc).

Para resultado mais preciso, substitua o TF-IDF por embeddings
semânticos (sentence-transformers) quando disponível.
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..config import DATA_DIR


_STOP = set("""a o e de da do das dos para com por em na no nas nos um uma uns umas
ao aos as os que se sua seu suas seus ou ate ate sob sobre entre como mais menos
todo toda todos todas este esta estes estas esse essa esses essas isto isso aquilo
exceto outros outras outro outra inclusive incluindo principalmente especialmente
sendo nao nem ja tambem tipo tipos forma formas conforme respectivamente""".split())


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _renormalizar(a: int, b: int, cos: float) -> float:
    """Mapeia cosseno bruto para afinidade na escala do pipeline.

    Classes de serviço (35-45) compartilham vocabulário genérico, então
    aplicamos piso de cosseno maior para reduzir falsos positivos.
    """
    ambos_servico = a >= 35 and b >= 35
    cos_min = 0.30 if ambos_servico else 0.10
    cos_max = 0.55 if ambos_servico else 0.50

    if cos < cos_min:
        return 0.0
    if cos >= cos_max:
        return 0.95
    return round(0.40 + (cos - cos_min) * (0.95 - 0.40) / (cos_max - cos_min), 4)


def gerar() -> tuple[int, str]:
    """Gera os CSVs de correlação. Retorna (n_pares, caminho_principal)."""
    fonte = os.path.join(DATA_DIR, "nice_classificacao.csv")
    if not os.path.exists(fonte):
        raise FileNotFoundError(f"Lista NICE oficial não encontrada: {fonte}")

    por_classe: dict[int, list[str]] = defaultdict(list)
    with open(fonte, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cls = int(row["classe"])
            desc = _normalizar(row["descricao"])
            if desc:
                por_classe[cls].append(desc)

    classes = sorted(por_classe.keys())
    docs = [" ".join(por_classe[c]) for c in classes]

    vect = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.85,
        stop_words=list(_STOP),
    )
    mat = vect.fit_transform(docs)
    sim = cosine_similarity(mat)

    pares_crus: list[tuple[int, int, float]] = []
    pares_norm: list[tuple[int, int, float, float]] = []

    for i, ca in enumerate(classes):
        for j, cb in enumerate(classes):
            if ca >= cb:
                continue
            cos = float(sim[i, j])
            if cos >= 0.05:
                pares_crus.append((ca, cb, cos))
            af = _renormalizar(ca, cb, cos)
            if af > 0:
                pares_norm.append((ca, cb, af, cos))

    # Matriz crua para auditoria
    crus_path = os.path.join(DATA_DIR, "correlatas_nice.csv")
    with open(crus_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ncl_a", "ncl_b", "afinidade", "fonte"])
        for a, b, cos in pares_crus:
            w.writerow([a, b, round(cos, 4), "nice_tfidf"])

    # Tabela definitiva usada pela Camada 3
    final_path = os.path.join(DATA_DIR, "especificacoes_correlatas.csv")
    with open(final_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ncl_a", "ncl_b", "afinidade", "descricao"])
        for a, b, af, cos in sorted(pares_norm, key=lambda x: (x[0], x[1])):
            w.writerow([a, b, af, f"Derivado NICE 13/2026 (cos={cos:.3f})"])

    return len(pares_norm), final_path


if __name__ == "__main__":
    n, path = gerar()
    print(f"Gerados {n} pares de correlação em: {path}")
