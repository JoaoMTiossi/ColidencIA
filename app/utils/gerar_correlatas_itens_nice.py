"""
Gera afinidade classe x classe a partir de similaridade ITEM x ITEM da Lista
Nice oficial (Nível 1 exaustivo — 10.449 itens em app/data/nice_classificacao.csv).

Uso:
    python -m app.utils.gerar_correlatas_itens_nice

Por que não reaproveitar app/utils/gerar_correlatas_nice.py:
    Aquele gerador agrega TODAS as descrições de uma classe em um único
    "documento por classe" antes de vetorizar (bag-of-words por classe).
    Isso dilui o sinal: uma classe com centenas de itens heterogêneos (ex.
    classe 9, "aparelhos científicos") produz um documento genérico que não
    captura afinidade pontual real entre um item específico de A e um item
    específico de B. Aqui a similaridade é calculada ITEM a ITEM — se existe
    UM item da classe A genuinamente afim de UM item da classe B, isso deve
    aparecer no sinal, e a curadoria manual (que é sub-inclusiva por natureza)
    é expandida para cobrir esse caso.

Estratégia:
    1. Carrega os 10.449 itens oficiais; normaliza texto (reaproveita
       ``_normalizar`` do gerador antigo).
    2. Tenta embeddings semânticos (app.utils.embeddings.encode_textos).
       Se indisponíveis (ex.: proxy bloqueia download do modelo), cai para
       TF-IDF (ngram 1-2, min_df=2, stop-words PT) fitado sobre TODOS os
       itens de uma vez só — o fit único garante um espaço vetorial comum
       para todos os pares de classe e usa IDF do corpus real.
    3. Para cada par de classes (a < b), monta o bloco esparso item×item
       ``X_a @ X_b.T`` (produto escalar = cosseno, pois a matriz é
       L2-normalizada) e deriva:
         - sim_top5 = média dos 5 maiores valores do bloco (zeros implícitos
           contam — um único par de itens outlier não basta para inflar o
           sinal da classe inteira).
         - sim_max + o par de itens (numero_base) que o realizou, para
           auditoria humana.
    4. Grava app/data/nice_itens_topk.csv com todo par cujo sim_top5 > 0.05.
    5. Calibra um mapeamento conservador sim_top5 -> afinidade [0.60, 0.95]:
       escolhe o maior corte possível tal que no máximo MAX_PARES_NOVOS pares
       de classe que hoje têm afinidade < 0.60 (ou não existem no CSV)
       cruzem para >= 0.60. Aplica ainda um piso absoluto MIN_SIM_TOP5_FLOOR:
       abaixo de sim_top5≈0.45 a lista de pares deixa de refletir afinidade de
       categoria e passa a ser dominada por coincidência lexical em palavras
       estruturais curtas (ex.: "líquidos de limpeza de para-brisa" [cl. 3] x
       "limpadores de para-brisa" [cl. 12] — mesmo radical "para-brisa", mas
       um é insumo químico e o outro é peça mecânica; ou o homógrafo
       "pensão" em "fundos de pensão" [previdência, cl. 36] x "serviços de
       pensão" [hospedagem, cl. 43]). Descoberto via regressão em
       app/tests/test_pipeline.py::TestBypassClasse — o piso corta esse
       ruído sem tocar no teste.
    6. Mescla no CSV final (afinidade_final = max(atual, gerado)). Linhas
       existentes que não mudam ficam byte-a-byte idênticas (mesma posição,
       mesmo fonte/descrição); só a coluna afinidade é tocada quando o valor
       gerado supera o atual. Pares totalmente novos são anexados ao final
       com fonte="nice_itens" e descrição citando o par de itens argmax.
    7. Preserva CRLF (formato original do arquivo).
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from ..config import DATA_DIR
from .embeddings import encode_textos
from .gerar_correlatas_nice import _STOP, _normalizar

TOPK = 5
SIM_AUDIT_MIN = 0.05
AFINIDADE_MIN = 0.60
AFINIDADE_MAX = 0.95
MAX_PARES_NOVOS = 100
MIN_FEATURES_TFIDF = 2
MIN_SIM_TOP5_FLOOR = 0.45

NICE_PATH = os.path.join(DATA_DIR, "nice_classificacao.csv")
TOPK_PATH = os.path.join(DATA_DIR, "nice_itens_topk.csv")
CORRELATAS_PATH = os.path.join(DATA_DIR, "especificacoes_correlatas.csv")


@dataclass
class Item:
    classe: int
    numero_base: str
    texto_norm: str
    texto_original: str


@dataclass
class ParClasse:
    a: int
    b: int
    sim_top5: float
    sim_max: float
    item_a_max: str
    item_b_max: str


# ---------------------------------------------------------------------------
# Carregamento e vetorização
# ---------------------------------------------------------------------------

def _carregar_itens() -> list[Item]:
    if not os.path.exists(NICE_PATH):
        raise FileNotFoundError(f"Lista NICE oficial não encontrada: {NICE_PATH}")
    itens: list[Item] = []
    with open(NICE_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            classe = int(row["classe"])
            desc_norm = _normalizar(row["descricao"])
            if desc_norm:
                itens.append(Item(classe, row["numero_base"], desc_norm, row["descricao"]))
    return itens


def _vetorizar(itens: list[Item]):
    """Retorna (matriz N×D L2-normalizada, nome_da_estratégia).

    Tenta embeddings semânticos primeiro; se o modelo não estiver disponível
    (offline/proxy), cai para TF-IDF fitado sobre todos os itens de uma vez.
    """
    textos = [it.texto_norm for it in itens]

    emb = encode_textos(textos)
    if emb is not None:
        return emb, "embeddings"

    from sklearn.feature_extraction.text import TfidfVectorizer

    vect = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.85,
        stop_words=list(_STOP),
    )
    mat = vect.fit_transform(textos)
    return mat, "tfidf"


# ---------------------------------------------------------------------------
# Bloco item x item por par de classes
# ---------------------------------------------------------------------------

def _rotulo_item(it: Item) -> str:
    return f"{it.numero_base} {it.texto_original}".strip()


def _mascara_itens_informativos(X) -> np.ndarray:
    """True para itens com sinal suficiente para participar do bloco item×item.

    Descrições Nice são curtas (2-6 palavras). Depois de stop-words e do
    corte min_df=2 do TF-IDF, ~21% dos itens ficam com 0-1 feature restante
    — quase sempre um substantivo estrutural genérico ("serviços",
    "aparelhos", "máquinas", "uso"...) compartilhado por dezenas de classes
    diferentes. Dois itens assim colapsam para o MESMO vetor de 1 dimensão e
    saem com cosseno 1.0 mesmo sendo semanticamente não relacionados (ex.:
    "Serviços atuariais" x "Serviços de vestiário" == 1.0, pois só resta o
    termo "serviços" em ambos). Exigir >= 2 features restantes filtra esse
    artefato sem tocar na lista de stop-words nem no min_df pedidos.
    Não se aplica ao caminho de embeddings (matriz densa) — lá o vetor
    carrega sentido mesmo para textos curtos.
    """
    if not hasattr(X, "getnnz"):
        return np.ones(X.shape[0], dtype=bool)
    return X.getnnz(axis=1) >= MIN_FEATURES_TFIDF


def _top5_media(valores: np.ndarray, tamanho_bloco: int) -> float:
    """Média dos 5 maiores valores do bloco, com zeros implícitos.

    ``valores`` contém apenas os valores NÃO-ZERO do bloco esparso. Se o
    bloco tiver menos de 5 entradas não-nulas, os slots restantes até 5 são
    zero — é isso que torna a média robusta contra um único par outlier.
    """
    if valores.size == 0:
        return 0.0
    maiores = np.sort(valores)[::-1][:TOPK]
    soma = float(maiores.sum())
    return soma / TOPK


def _calcular_pares_classe(itens: list[Item], X) -> list[ParClasse]:
    informativo = _mascara_itens_informativos(X)
    n_descartados = int((~informativo).sum())
    if n_descartados:
        print(
            f"Itens sem sinal suficiente (< {MIN_FEATURES_TFIDF} features) "
            f"excluídos do bloco item×item: {n_descartados}/{len(itens)}"
        )

    idx_por_classe: dict[int, list[int]] = defaultdict(list)
    for i, it in enumerate(itens):
        if informativo[i]:
            idx_por_classe[it.classe].append(i)

    classes = sorted(idx_por_classe.keys())
    pares: list[ParClasse] = []

    for i, a in enumerate(classes):
        rows_a = idx_por_classe[a]
        Xa = X[rows_a]
        for b in classes[i + 1:]:
            rows_b = idx_por_classe[b]
            Xb = X[rows_b]
            bloco = Xa @ Xb.T

            if hasattr(bloco, "tocoo"):
                coo = bloco.tocoo()
                if coo.nnz == 0:
                    continue
                dados = coo.data
                sim_top5 = _top5_media(dados, len(rows_a) * len(rows_b))
                if sim_top5 <= SIM_AUDIT_MIN:
                    continue
                pos_max = int(np.argmax(dados))
                sim_max = float(dados[pos_max])
                row_local = int(coo.row[pos_max])
                col_local = int(coo.col[pos_max])
            else:
                # matriz densa (caminho de embeddings)
                bloco = np.asarray(bloco)
                dados = bloco.ravel()
                sim_top5 = _top5_media(dados, dados.size)
                if sim_top5 <= SIM_AUDIT_MIN:
                    continue
                pos_max = int(np.argmax(bloco))
                row_local, col_local = np.unravel_index(pos_max, bloco.shape)
                sim_max = float(bloco[row_local, col_local])

            item_a = itens[rows_a[row_local]]
            item_b = itens[rows_b[col_local]]
            pares.append(
                ParClasse(
                    a=a,
                    b=b,
                    sim_top5=round(sim_top5, 6),
                    sim_max=round(sim_max, 6),
                    item_a_max=_rotulo_item(item_a),
                    item_b_max=_rotulo_item(item_b),
                )
            )

    return pares


def _gravar_topk(pares: list[ParClasse]) -> None:
    pares_ordenados = sorted(pares, key=lambda p: (p.a, p.b))
    with open(TOPK_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ncl_a", "ncl_b", "sim_top5", "sim_max", "item_a_max", "item_b_max"])
        for p in pares_ordenados:
            w.writerow([p.a, p.b, p.sim_top5, p.sim_max, p.item_a_max, p.item_b_max])


# ---------------------------------------------------------------------------
# CSV atual (para saber o que já é elegível e mesclar depois)
# ---------------------------------------------------------------------------

def _carregar_csv_atual() -> tuple[list[dict], dict[tuple[int, int], float]]:
    """Retorna (linhas na ordem original, dict {(a,b): afinidade})."""
    linhas: list[dict] = []
    afinidades: dict[tuple[int, int], float] = {}
    if not os.path.exists(CORRELATAS_PATH):
        return linhas, afinidades
    with open(CORRELATAS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            a, b = int(row["ncl_a"]), int(row["ncl_b"])
            af = float(row["afinidade"])
            linhas.append(row)
            afinidades[(a, b)] = af
    return linhas, afinidades


# ---------------------------------------------------------------------------
# Calibração conservadora do corte sim_top5 -> afinidade
# ---------------------------------------------------------------------------

def _calibrar_corte(
    pares: list[ParClasse], afinidades_atuais: dict[tuple[int, int], float]
) -> tuple[float, float, int]:
    """Escolhe o maior corte de sim_top5 tal que no máximo MAX_PARES_NOVOS
    pares "novos" (afinidade atual < 0.60 ou par ausente) cruzem para >= 0.60,
    respeitando também o piso absoluto MIN_SIM_TOP5_FLOOR (ver docstring do
    módulo — abaixo dele o sinal deixa de ser confiável mesmo que ainda haja
    "vagas" no orçamento de 100 pares novos).

    Retorna (corte, sim_max_global, n_pares_novos).
    """
    if not pares:
        return 1.0, 0.0, 0

    pares_desc = sorted(pares, key=lambda p: p.sim_top5, reverse=True)
    sim_max_global = pares_desc[0].sim_top5

    novos = 0
    incluidos: list[ParClasse] = []
    for p in pares_desc:
        atual = afinidades_atuais.get((p.a, p.b), 0.0)
        eh_novo = atual < AFINIDADE_MIN
        if eh_novo and novos >= MAX_PARES_NOVOS:
            break
        if eh_novo:
            novos += 1
        incluidos.append(p)

    corte_por_cap = incluidos[-1].sim_top5 if incluidos else sim_max_global
    corte = max(corte_por_cap, MIN_SIM_TOP5_FLOOR)

    novos_apos_piso = sum(
        1
        for p in pares_desc
        if p.sim_top5 >= corte and afinidades_atuais.get((p.a, p.b), 0.0) < AFINIDADE_MIN
    )
    return corte, sim_max_global, novos_apos_piso


def _mapear_afinidade(sim_top5: float, corte: float, sim_max_global: float) -> float:
    if sim_top5 < corte:
        return 0.0
    if sim_max_global <= corte:
        return AFINIDADE_MAX
    frac = (sim_top5 - corte) / (sim_max_global - corte)
    valor = AFINIDADE_MIN + frac * (AFINIDADE_MAX - AFINIDADE_MIN)
    return round(min(AFINIDADE_MAX, max(AFINIDADE_MIN, valor)), 4)


# ---------------------------------------------------------------------------
# Mesclagem final
# ---------------------------------------------------------------------------

def _descricao_novo_par(p: ParClasse) -> str:
    texto = f"Itens Nice mais afins: {p.item_a_max} × {p.item_b_max}"
    if len(texto) > 120:
        texto = texto[:117].rstrip() + "..."
    return texto


def _mesclar(
    linhas_atuais: list[dict],
    afinidades_atuais: dict[tuple[int, int], float],
    pares: list[ParClasse],
    corte: float,
    sim_max_global: float,
) -> tuple[list[dict], int, int]:
    """Retorna (linhas finais na ordem certa, n_elegiveis_antes, n_elegiveis_depois)."""
    gerado_por_par: dict[tuple[int, int], tuple[float, ParClasse]] = {}
    for p in pares:
        af_gerada = _mapear_afinidade(p.sim_top5, corte, sim_max_global)
        if af_gerada > 0:
            gerado_por_par[(p.a, p.b)] = (af_gerada, p)

    n_elegiveis_antes = sum(1 for v in afinidades_atuais.values() if v >= AFINIDADE_MIN)

    linhas_finais: list[dict] = []
    pares_vistos: set[tuple[int, int]] = set()
    for row in linhas_atuais:
        a, b = int(row["ncl_a"]), int(row["ncl_b"])
        pares_vistos.add((a, b))
        af_atual = float(row["afinidade"])
        af_gerada, _ = gerado_por_par.get((a, b), (0.0, None))
        af_final = max(af_atual, af_gerada)
        if af_final != af_atual:
            nova = dict(row)
            nova["afinidade"] = af_final
            linhas_finais.append(nova)
        else:
            linhas_finais.append(row)

    novas_linhas: list[dict] = []
    for (a, b), (af_gerada, p) in sorted(gerado_por_par.items()):
        if (a, b) in pares_vistos:
            continue
        novas_linhas.append(
            {
                "ncl_a": a,
                "ncl_b": b,
                "afinidade": af_gerada,
                "fonte": "nice_itens",
                "descricao": _descricao_novo_par(p),
            }
        )

    linhas_finais.extend(novas_linhas)

    afinidades_finais = dict(afinidades_atuais)
    for (a, b), (af_gerada, _) in gerado_por_par.items():
        afinidades_finais[(a, b)] = max(afinidades_finais.get((a, b), 0.0), af_gerada)
    n_elegiveis_depois = sum(1 for v in afinidades_finais.values() if v >= AFINIDADE_MIN)

    return linhas_finais, n_elegiveis_antes, n_elegiveis_depois


def _gravar_correlatas(linhas: list[dict]) -> None:
    with open(CORRELATAS_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["ncl_a", "ncl_b", "afinidade", "fonte", "descricao"])
        for row in linhas:
            w.writerow(
                [row["ncl_a"], row["ncl_b"], row["afinidade"], row["fonte"], row["descricao"]]
            )


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def gerar() -> None:
    itens = _carregar_itens()
    print(f"Itens Nice carregados: {len(itens)}")

    X, estrategia = _vetorizar(itens)
    print(f"Vetorização: {estrategia} (shape={getattr(X, 'shape', None)})")

    pares = _calcular_pares_classe(itens, X)
    print(f"Pares de classe com sim_top5 > {SIM_AUDIT_MIN}: {len(pares)}")

    _gravar_topk(pares)
    print(f"Auditoria gravada em: {TOPK_PATH}")

    linhas_atuais, afinidades_atuais = _carregar_csv_atual()

    corte, sim_max_global, n_novos = _calibrar_corte(pares, afinidades_atuais)
    print(
        f"Corte calibrado: sim_top5 >= {corte:.4f} "
        f"(sim_max_global={sim_max_global:.4f}, pares novos={n_novos}/{MAX_PARES_NOVOS})"
    )

    linhas_finais, n_antes, n_depois = _mesclar(
        linhas_atuais, afinidades_atuais, pares, corte, sim_max_global
    )
    print(f"Pares elegíveis (afinidade >= {AFINIDADE_MIN}) ANTES:  {n_antes}")
    print(f"Pares elegíveis (afinidade >= {AFINIDADE_MIN}) DEPOIS: {n_depois}")

    novos_pares = sorted(
        (
            p
            for p in pares
            if _mapear_afinidade(p.sim_top5, corte, sim_max_global) >= AFINIDADE_MIN
            and afinidades_atuais.get((p.a, p.b), 0.0) < AFINIDADE_MIN
        ),
        key=lambda p: p.sim_top5,
        reverse=True,
    )
    print(f"\nLista dos {len(novos_pares)} pares novos (classe A x classe B — itens argmax):")
    for p in novos_pares:
        af = _mapear_afinidade(p.sim_top5, corte, sim_max_global)
        print(
            f"  {p.a:>2} x {p.b:<2}  sim_top5={p.sim_top5:.4f}  afinidade={af:.4f}  "
            f"[{p.item_a_max}] x [{p.item_b_max}]"
        )

    _gravar_correlatas(linhas_finais)
    print(f"\nCSV mesclado gravado em: {CORRELATAS_PATH} ({len(linhas_finais)} pares)")


if __name__ == "__main__":
    gerar()
