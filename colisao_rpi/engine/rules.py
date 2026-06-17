"""
Motor de detecção de colidências.

Implementa check_collision() e run_collision_detection() conforme o spec.
"""

from __future__ import annotations

import re

import pandas as pd
from tqdm import tqdm

from rapidfuzz import fuzz as _fuzz

from ..config import MIN_CHARS_SOFT_MATCH, THRESHOLD_IDENTICO, THRESHOLD_NUCLEO, THRESHOLD_SIMILAR
from ..data.nice_matrix import classes_collide
from ..data.term_common import EXCLUIR_R4C as _EXCLUIR_R4C
from .normalize import apply_phonetic, normalize, phonetic_key
from .nucleus import ALL_STOPWORDS, extract_nucleus, is_common_mark
from .similarity import similarity_score, weighted_similarity

# Override de conjunto: score bruto acima disto colide independente de tokens.
# Calibrado para capturar "CHINES FACIL × CHINES MUITO FACIL" (sc ~0.93)
# sem disparar em "NIU SUSHI × HIRO RESTAURANTE" (sc ~0.90 por token_sort).
_CONJUNTO_OVERRIDE: float = 0.93

# Threshold do score PONDERADO — diferente por proximidade de classe.
_THRESHOLD_PONDERADO_MESMA:    float = 0.68   # mesma classe NCL: mais permissivo
_THRESHOLD_PONDERADO_CORRELATA: float = 0.76  # classes correlatas: mais estrito

# Score bruto acima do qual R0 (spec gate) é contornado:
# marcas quasi-idênticas (>=0.95) sempre alertam o advogado.
_BRUTO_BYPASS_SPEC: float = 0.95

# Minimum token length to participate in cross-token matching (R4c).
# 4 chars elimina tokens curtos genéricos: VIA, NET, APP, ANA, ALE, etc.
_MIN_TOKEN_LEN = 4

# Threshold específico para R4c — mais alto que o geral pois compara token isolado.
_THRESHOLD_TOKEN = 0.85

# ---------------------------------------------------------------------------
# Portão de especificação
# ---------------------------------------------------------------------------

# Palavras muito genéricas que aparecem em qualquer spec — ignoradas no overlap.
_SPEC_STOPWORDS: frozenset[str] = frozenset({
    'DE', 'DO', 'DA', 'DOS', 'DAS', 'E', 'EM', 'COM', 'PARA', 'POR', 'NO', 'NA',
    'OS', 'AS', 'OU', 'SE', 'QUE', 'AO', 'AOS', 'UM', 'UMA',
    'SERVICOS', 'SERVICO', 'PRODUTO', 'PRODUTOS', 'INCLUSIVE', 'EXCETO',
    'TODOS', 'TODAS', 'GERAL', 'GERAIS', 'OUTROS', 'OUTRAS',
    'FORMAS', 'FORMA', 'ATIVIDADES', 'ATIVIDADE', 'NESTE', 'ITEM',
    'RELACIONADOS', 'RELACIONADAS', 'ENTRE', 'MEDIANTE', 'ATRAVES',
})

# Sobreposição mínima de tokens para considerar specs compatíveis.
# Abaixo disto — quando ambas as specs estão disponíveis — a colidência é bloqueada.
_SPEC_OVERLAP_MIN: float = 0.05

# Mínimo de tokens significativos para a spec ser considerada válida.
_SPEC_MIN_TOKENS: int = 2


def _spec_tokens(spec: str) -> set[str]:
    """Tokens normalizados da especificação, sem stopwords de baixo valor."""
    if not spec or not str(spec).strip():
        return set()
    norm = normalize(str(spec))
    return {t for t in norm.split() if len(t) >= 4 and t not in _SPEC_STOPWORDS}


def _spec_overlap(spec_a: str, spec_b: str) -> float:
    """
    Coeficiente de sobreposição entre duas especificações:
        overlap = |A ∩ B| / min(|A|, |B|)

    Retorna -1.0 quando uma das specs não tem tokens suficientes
    (portão não aplicável — não bloquear a análise fonética).
    """
    ta = _spec_tokens(spec_a)
    tb = _spec_tokens(spec_b)
    if len(ta) < _SPEC_MIN_TOKENS or len(tb) < _SPEC_MIN_TOKENS:
        return -1.0
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb))


# ---------------------------------------------------------------------------
# Tokens descritivos de segmento que não constituem elemento distintivo sozinhos.
# Ex: MOTORS, DELIVERY, SEGUROS — compartilhados por centenas de marcas na mesma classe.
_TOKENS_DESCRITORES: frozenset[str] = frozenset({
    # Automotivo
    'MOTORS', 'MOTOR', 'MOTO', 'AUTO', 'AUTOMOVEL', 'VEICULOS', 'VEICULO', 'AUTOMOTIVO',
    # Logística / delivery
    'DELIVERY', 'ENTREGA', 'EXPRESS', 'EXPRESSO',
    # Financeiro / seguros
    'SEGUROS', 'SEGURO', 'CORRETORA', 'FINANCEIRA', 'CREDITO', 'INVESTIMENTOS',
    # Moda / vestuário
    'MODA', 'MODAS', 'FASHION', 'ROUPAS', 'VESTUARIO',
    # Alimentação
    'PIZZA', 'PIZZARIA', 'BURGER', 'FOOD', 'LANCHE', 'SUSHI', 'PADARIA', 'RESTAURANTE',
    # Varejo genérico
    'SHOP', 'STORE', 'MERCADO', 'MARKET', 'COMERCIO', 'LOJA',
    # Tech / digital
    'TECH', 'DIGITAL', 'ONLINE', 'SISTEMAS', 'SOLUCOES',
    # Qualificadores genéricos
    'TUDO', 'GERAL', 'CLEAN', 'NOVO', 'NOVA', 'TOTAL',
    # Cores (tokens fonéticos pós-normalização)
    'PINK', 'ROSA', 'VERDE', 'AZUL', 'BRANCO', 'PRETO', 'DOURADO', 'PRATA',
})


def clean_titular(titular: str) -> str:
    """Remove sufixo '(BR/XX)' do nome do titular."""
    return re.sub(r'\s*\([A-Z]{2}/[A-Z]{2,}\)\s*$', '', titular).strip()


def _too_short(text: str) -> bool:
    """Marca com ≤ MIN_CHARS_SOFT_MATCH–1 caracteres (sem espaços): só match idêntico."""
    return len(text.replace(' ', '')) < MIN_CHARS_SOFT_MATCH


def _token_keys(text: str) -> list[str]:
    """
    Retorna chaves fonéticas dos tokens DISTINTIVOS da marca para R4c.
    Usa EXCLUIR_R4C de term_common (737 termos) como filtro único.
    """
    return [
        apply_phonetic(t)
        for t in normalize(text).split()
        if len(t) >= _MIN_TOKEN_LEN
        and t not in _EXCLUIR_R4C
    ]


def _best_token_similarity(nome_a: str, nome_b: str) -> float:
    """
    Máxima similaridade fonética entre qualquer par de tokens dos dois nomes.
    Usado como Regra 4c para detectar núcleos similares em marcas compostas.
    """
    toks_a = _token_keys(nome_a)
    toks_b = _token_keys(nome_b)
    if not toks_a or not toks_b:
        return 0.0
    best = 0.0
    for ta in toks_a:
        for tb in toks_b:
            s = _fuzz.ratio(ta, tb) / 100.0
            if s > best:
                best = s
    return best


def check_collision(
    nome_cli: str,
    nucleo_cli: str,
    cls_cli: int,
    nome_rpi: str,
    nucleo_rpi: str,
    classes_rpi: list[int],
    classe_match: bool,
    spec_cli: str = '',
    spec_rpi: str = '',
    corpus: dict | None = None,
) -> tuple[bool, str | None, float]:
    """
    Avalia colidência entre uma marca do cliente e uma da RPI.

    Retorna: (colide: bool, regra: str | None, score: float)

    Ordem de avaliação:
        R0   — Portão de especificação (specs incompatíveis bloqueiam tudo)
        R1   — Chaves fonéticas idênticas (independente de classe)
        R2   — Score PONDERADO por distintividade ≥ threshold (novo — camada híbrida)
        R2b  — Override de conjunto marcário (score bruto ≥ 0.90)
        R3   — Núcleo idêntico/muito próximo, classes correlatas (herdado, fallback)
        R4c  — Melhor token DISTINTIVO similar (herdado, fallback)
    """
    _corpus = corpus or {}

    # --- R1: chaves fonéticas idênticas — prioridade sobre spec gate ---
    # Marcas idênticas sempre alertam o advogado, mesmo com specs divergentes.
    if phonetic_key(nome_cli) == phonetic_key(nome_rpi):
        return True, 'R1-IDENTICA', 1.0

    # Pré-calcular score bruto (usado em R0 bypass e R2b)
    sc_bruto = similarity_score(nome_cli, nome_rpi)

    # --- R0: portão de especificação ---
    # Bypass quando as marcas são quasi-idênticas (>=_BRUTO_BYPASS_SPEC):
    # risco de confusão é alto independente do wording da spec.
    sc_spec = _spec_overlap(spec_cli, spec_rpi)
    if sc_spec != -1.0 and sc_spec < _SPEC_OVERLAP_MIN:
        if sc_bruto < _BRUTO_BYPASS_SPEC:
            return False, None, 0.0
        # sc_bruto >= 0.95: não bloqueia, segue análise

    if not classe_match:
        return False, None, 0.0

    if _too_short(nome_cli) or _too_short(nome_rpi):
        return False, None, 0.0

    # Threshold do score ponderado varia por proximidade de classe
    mesma_classe = any(c == cls_cli for c in classes_rpi)
    threshold_pond = (_THRESHOLD_PONDERADO_MESMA if mesma_classe
                      else _THRESHOLD_PONDERADO_CORRELATA)

    # --- R2: score PONDERADO por distintividade ---
    sc_pond = weighted_similarity(nome_cli, nome_rpi, cls_cli, _corpus)
    if sc_pond >= threshold_pond:
        return True, 'R2-PONDERADO', sc_pond

    # --- R2b: override de conjunto marcário ---
    # Score bruto >= 0.93: conjunto tão similar que advogado deve revisar.
    if sc_bruto >= _CONJUNTO_OVERRIDE:
        return True, 'R2b-CONJUNTO', sc_bruto

    # --- R3: núcleo idêntico (fallback para siglas/marcas curtas) ---
    sc_nucleo = similarity_score(nucleo_cli, nucleo_rpi)
    if sc_nucleo >= THRESHOLD_NUCLEO:
        return True, 'R3-NUCLEO-IDENTICO', sc_nucleo

    # --- R4c: token distintivo isolado (fallback estrito) ---
    if sc_bruto >= 0.50:
        score_token = _best_token_similarity(nome_cli, nome_rpi)
        if score_token >= _THRESHOLD_TOKEN:
            return True, 'R4c-TOKEN-SIMILAR', score_token

    return False, None, 0.0


def run_collision_detection(
    df_client: pd.DataFrame,
    rpi_records: list[dict],
    rpi_numero: str,
    rpi_data: str,
    verbose: bool = False,
    debug_pair: str | None = None,
    update_corpus: bool = True,
) -> list[dict]:
    """
    Executa a detecção de colidências entre a base de clientes e os registros da RPI.

    Parâmetros:
        update_corpus: se True, atualiza corpus_freq.json com os dados desta RPI
                       antes de processar (melhora sinal de genericidade).

    Retorna lista de dicts com campos para o relatório.
    """
    from .corpus import load_corpus, update_corpus as _update_corpus
    import os as _os

    _corpus_path = _os.path.join(
        _os.path.dirname(__file__), '..', 'data', 'corpus_freq.json'
    )

    from .corpus import load_spec_corpus, update_spec_corpus

    _spec_corpus_path = _os.path.join(
        _os.path.dirname(__file__), '..', 'data', 'corpus_spec_freq.json'
    )

    if update_corpus:
        corpus = update_spec_corpus(rpi_records, _spec_corpus_path)
    else:
        corpus = load_spec_corpus(_spec_corpus_path)
    # Pré-processar clientes
    client_rows = []
    for _, row in df_client.iterrows():
        nome = str(row['MARCA'])
        nucleo = extract_nucleus(nome)
        client_rows.append({
            'processo': str(row['PROCESSO']),
            'marca': nome,
            'nucleo': nucleo,
            'classe': int(row['CLASSE_NUM']),
            'titular': clean_titular(str(row.get('TITULAR', ''))),
            'situacao': str(row.get('SITUACAO', '')),
            'pasta': str(row.get('PASTA', '')),
            'spec': str(row.get('ESPECIFICAÇÃO', '') or ''),
        })

    # Parsear debug_pair
    debug_names: tuple[str, str] | None = None
    if debug_pair:
        parts = debug_pair.split(',', 1)
        if len(parts) == 2:
            debug_names = (parts[0].strip().upper(), parts[1].strip().upper())

    results: list[dict] = []

    for rpi in tqdm(rpi_records, desc='Processando RPI', unit='marca'):
        nome_rpi   = rpi['nome']
        nucleo_rpi = extract_nucleus(nome_rpi)
        classes_rpi: list[int] = rpi['classes']
        titulares_rpi: set[str] = {t.upper().strip() for t in rpi['titulares']}

        for cli in client_rows:
            nome_cli   = cli['marca']
            nucleo_cli = cli['nucleo']
            cls_cli    = cli['classe']

            # Debug mode: mostrar info do par específico
            if debug_names:
                a_norm = nome_cli.upper()
                b_norm = nome_rpi.upper()
                if debug_names[0] in a_norm and debug_names[1] in b_norm:
                    sc = similarity_score(nome_cli, nome_rpi)
                    sn = similarity_score(nucleo_cli, nucleo_rpi)
                    print(f"[DEBUG] CLI={nome_cli!r} (núcleo={nucleo_cli!r}, cl={cls_cli})")
                    print(f"        RPI={nome_rpi!r} (núcleo={nucleo_rpi!r}, cls={classes_rpi})")
                    print(f"        score_completo={sc:.3f}  score_nucleo={sn:.3f}")

            # Regra 4, nota 4: mesmo titular não é colidência
            if cli['titular'].upper() in titulares_rpi:
                continue

            # Verificar se ao menos uma classe da RPI colide com a do cliente
            classe_match = any(classes_collide(cls_cli, c) for c in classes_rpi)

            # Recuperar especificação da RPI para a classe que efetivamente colide
            spec_rpi = ''
            for c in classes_rpi:
                if classes_collide(cls_cli, c):
                    spec_rpi = rpi['especificacoes'].get(str(c), '')
                    if spec_rpi:
                        break

            colide, regra, score = check_collision(
                nome_cli, nucleo_cli, cls_cli,
                nome_rpi, nucleo_rpi, classes_rpi,
                classe_match,
                spec_cli=cli['spec'],
                spec_rpi=spec_rpi,
                corpus=corpus,
            )

            if colide:
                if verbose:
                    print(
                        f"[{regra}] score={score:.3f} | "
                        f"{nome_cli!r} (cl {cls_cli}) × "
                        f"{nome_rpi!r} (cls {classes_rpi})"
                    )

                classes_rpi_str = ','.join(str(c) for c in classes_rpi)
                results.append({
                    'PROCESSO CLIENTE':  cli['processo'],
                    'MARCA CLIENTE':     nome_cli,
                    'CLASSE CLIENTE':    f"NCL(13) {cls_cli}",
                    'TITULAR CLIENTE':   cli['titular'],
                    'PROCESSO TERCEIRO': rpi['processo'],
                    'MARCA TERCEIRO':    nome_rpi,
                    'CLASSE TERCEIRO':   f"NCL(13) {classes_rpi_str}",
                    # Campos internos (prefixo _ — não exportados no template final)
                    '_REGRA':       regra,
                    '_SCORE':       round(score, 3),
                    '_DESPACHOS':   '; '.join(f"{d[0]}-{d[1]}" for d in rpi['despachos']),
                    '_SITUACAO_CLI': cli['situacao'],
                    '_PASTA':       cli['pasta'],
                })

    return results
