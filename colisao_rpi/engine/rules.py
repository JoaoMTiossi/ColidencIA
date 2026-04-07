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
from .normalize import apply_phonetic, normalize, phonetic_key
from .nucleus import ALL_STOPWORDS, extract_nucleus, is_common_mark
from .similarity import similarity_score

# Minimum token length to participate in cross-token matching (R4c)
_MIN_TOKEN_LEN = 3


def clean_titular(titular: str) -> str:
    """Remove sufixo '(BR/XX)' do nome do titular."""
    return re.sub(r'\s*\([A-Z]{2}/[A-Z]{2,}\)\s*$', '', titular).strip()


def _too_short(text: str) -> bool:
    """Marca com ≤ MIN_CHARS_SOFT_MATCH–1 caracteres (sem espaços): só match idêntico."""
    return len(text.replace(' ', '')) < MIN_CHARS_SOFT_MATCH


def _token_keys(text: str) -> list[str]:
    """
    Retorna a lista de chaves fonéticas dos tokens significativos da marca
    (comprimento >= _MIN_TOKEN_LEN e não stopword).
    """
    return [
        apply_phonetic(t)
        for t in normalize(text).split()
        if len(t) >= _MIN_TOKEN_LEN and t not in ALL_STOPWORDS
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
) -> tuple[bool, str | None, float]:
    """
    Avalia colidência entre uma marca do cliente e uma da RPI.

    Retorna: (colide: bool, regra: str | None, score: float)

    Ordem de avaliação das regras:
        R1   — Chaves fonéticas idênticas (independente de classe)
        R3   — Núcleo idêntico ou muito próximo, classes correlatas
        R4   — Nome completo similar fonético, classes correlatas
        R4b  — Núcleo similar fonético, classes correlatas
        R4c  — Melhor token similar fonético, classes correlatas

    Marcas muito curtas (< MIN_CHARS_SOFT_MATCH chars) só colidem por identidade.
    Marcas com núcleo genérico exigem threshold mais alto (THRESHOLD_NUCLEO).
    """
    # --- Regra 1: chaves fonéticas idênticas — independente de classe ---
    # Usa igualdade exata de phonetic_key para evitar falsos positivos causados
    # pelo token_set_ratio (que dá 1.0 quando uma marca é subconjunto da outra).
    if phonetic_key(nome_cli) == phonetic_key(nome_rpi):
        return True, 'R1-IDENTICA', 1.0

    # Daqui em diante exige classes correlatas
    if not classe_match:
        return False, None, 0.0

    # Marcas muito curtas: apenas identidade (já avaliada acima)
    if _too_short(nome_cli) or _too_short(nome_rpi):
        return False, None, 0.0

    score_completo = similarity_score(nome_cli, nome_rpi)
    score_nucleo   = similarity_score(nucleo_cli, nucleo_rpi)

    # --- Regra 3/7: núcleo idêntico ou muito próximo ---
    if score_nucleo >= THRESHOLD_NUCLEO:
        return True, 'R3-NUCLEO-IDENTICO', score_nucleo

    # Marcas com núcleo genérico (Regra 5): threshold mais alto apenas quando
    # AMBOS os núcleos são palavras comuns — um único lado genérico vs. marca
    # derivada (ex: TROPICAL × TROPI) ainda usa o threshold padrão.
    threshold_sim = THRESHOLD_NUCLEO if (
        is_common_mark(nucleo_cli) and is_common_mark(nucleo_rpi)
    ) else THRESHOLD_SIMILAR

    # --- Regra 4: nome completo similar ---
    if score_completo >= threshold_sim:
        return True, 'R4-SIMILAR-FONETICO', score_completo

    # --- Regra 4b: núcleo similar ---
    if score_nucleo >= threshold_sim:
        return True, 'R4b-NUCLEO-SIMILAR', score_nucleo

    # --- Regra 4c: melhor par de tokens similares ---
    # Detecta casos como ROTTAS × ROTA CALHAS, FORTY × AVE FORTE,
    # TEATRO FACES × FACES TEAM CONGRESS (tokens cruzados).
    score_token = _best_token_similarity(nome_cli, nome_rpi)
    if score_token >= threshold_sim:
        return True, 'R4c-TOKEN-SIMILAR', score_token

    return False, None, 0.0


def run_collision_detection(
    df_client: pd.DataFrame,
    rpi_records: list[dict],
    rpi_numero: str,
    rpi_data: str,
    verbose: bool = False,
    debug_pair: str | None = None,
) -> list[dict]:
    """
    Executa a detecção de colidências entre a base de clientes e os registros da RPI.

    Otimizações:
    1. Pré-filtro por classe: só calcula similaridade para pares com classes afins.
    2. Blocking por prefixo fonético: pré-filtra por primeiras 3 letras do núcleo.
       (desativado quando debug_pair está ativo)

    Retorna lista de dicts com campos para o relatório.
    """
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

            colide, regra, score = check_collision(
                nome_cli, nucleo_cli, cls_cli,
                nome_rpi, nucleo_rpi, classes_rpi,
                classe_match,
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
