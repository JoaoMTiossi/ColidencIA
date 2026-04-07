"""
Extração do núcleo de uma marca (parte distintiva, antes de stopwords/descritores).
"""

from __future__ import annotations

from .normalize import normalize

# ---------------------------------------------------------------------------
# Stopwords que indicam início do complemento descritivo
# ---------------------------------------------------------------------------
_STOPWORDS_PT: frozenset[str] = frozenset({
    'DE', 'DO', 'DA', 'DOS', 'DAS', 'E', 'EM', 'COM', 'PARA', 'POR',
    'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'SS', 'MEI',
    'COMERCIO', 'INDUSTRIA', 'SERVICOS', 'SOLUCOES', 'ASSESSORIA',
    'CONSULTORIA', 'GRUPO', 'HOLDING', 'PARTICIPACOES',
    'STUDIO', 'CLINICA', 'FARMACIA', 'SUPERMERCADO', 'RESTAURANTE',
    'ACADEMIA', 'ESCOLA', 'CENTRO', 'INSTITUTO',
})

_STOPWORDS_EN: frozenset[str] = frozenset({'AND', 'OF', 'THE', 'FOR', 'BY', 'WITH'})

_STOPWORDS_ES: frozenset[str] = frozenset({'Y', 'DEL', 'LOS', 'LAS', 'POR', 'PARA'})

ALL_STOPWORDS: frozenset[str] = _STOPWORDS_PT | _STOPWORDS_EN | _STOPWORDS_ES

# ---------------------------------------------------------------------------
# Palavras de uso comum/genérico (Regra 5)
# ---------------------------------------------------------------------------
PALAVRAS_COMUNS: frozenset[str] = frozenset({
    'SUPER', 'MEGA', 'TOP', 'PLUS', 'MAX', 'MAIS', 'BRASIL', 'NACIONAL',
    'CASA', 'MUNDO', 'CENTRO', 'GRUPO', 'REDE', 'NOVA', 'NOVO', 'GERAL',
    'IDEAL', 'TOTAL', 'GLOBAL', 'DIGITAL', 'MASTER', 'PREMIER', 'PRIME',
    'GOLD', 'SILVER', 'PRO', 'EXPRESS', 'FAST', 'SMART', 'FLEX',
    'TROPICAL', 'POLAR', 'FORTE', 'REAL', 'PREMIUM', 'QUALITY',
    'LINK', 'NET', 'WEB', 'TECH', 'MULTI', 'INTER', 'ULTRA',
})


def extract_nucleus(marca: str) -> str:
    """
    Extrai o núcleo da marca (tokens antes do primeiro stopword/descritor).

    Lógica:
    - Normaliza o texto
    - Divide em tokens
    - Retorna tokens até encontrar um stopword (exige ≥1 token acumulado antes)
    - Se nenhum stopword encontrado, retorna tudo

    Exemplos:
        "INSPIRE STUDIO DE PILATES E LPF" → "INSPIRE"
        "RAMOS E RAMOS ADVOCACIA"         → "RAMOS"   (E é stopword)
        "PRIME PARTICIPACOES"             → "PRIME"
        "NOVA GERACAO"                    → "NOVA GERACAO"  (sem stopword)
    """
    norm = normalize(marca)
    tokens = norm.split()
    nucleus: list[str] = []
    for tok in tokens:
        if tok in ALL_STOPWORDS and nucleus:
            break
        nucleus.append(tok)
    return ' '.join(nucleus) if nucleus else norm


def is_common_mark(nucleo: str) -> bool:
    """
    Retorna True se o núcleo da marca é composto por palavras de uso genérico
    (Regra 5 — requer score mais alto para colidir).
    """
    tokens = set(normalize(nucleo).split())
    return bool(tokens & PALAVRAS_COMUNS) and len(tokens) <= 2
