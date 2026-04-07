"""
Normalização textual e aplicação de equivalências fonéticas PT/EN/ES.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Regras fonéticas (padrão → substituição), aplicadas em sequência
# ---------------------------------------------------------------------------
_PHONETIC_RULES: list[tuple[str, str]] = [
    # Inglês → Português
    (r'PH',                         'F'),
    (r'\bY(?=[AEIOU])',             'I'),
    (r'(?<=[AEIOU])Y\b',            'I'),
    (r'\bW',                        'V'),
    (r'TH',                         'T'),
    (r'SH',                         'X'),
    (r'(?<=[AEIOU])X(?=[AEIOU])',   'Z'),
    (r'CK',                         'C'),
    (r'IE\b',                       'I'),
    (r'OE\b',                       'E'),
    (r'([A-Z])\1',                  r'\1'),   # letras duplas: COFFEE → COFE
    # Espanhol → Português
    (r'LL',                         'LI'),
    (r'Ñ',                          'NI'),
    (r'Z(?=[EI])',                  'S'),
    # Português
    (r'QU(?=[EI])',                 'K'),
    (r'GU(?=[EI])',                 'G'),
    (r'SS',                         'S'),
    (r'Ç',                          'S'),
    (r'\bH',                        ''),      # H inicial silencioso
    (r'LH',                         'LI'),
    (r'NH',                         'NI'),
    (r'(?<=[AEIOU])S(?=[AEIOU])',   'Z'),
    (r'X(?=[CSPT])',                'S'),
    (r'(?<=[AEIOU])X\b',            'S'),
    (r'K',                          'C'),
    (r'W',                          'V'),
    (r'Y(?=[BCDFGHJKLMNPQRSTVWXZ])','I'),
]

# Compilar padrões uma única vez
_COMPILED_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(pat), repl) for pat, repl in _PHONETIC_RULES
]


def normalize(text: str) -> str:
    """
    Normalização base:
    - Caixa alta
    - Remove acentos (NFD → filtro de combining marks)
    - Remove pontuação (exceto espaço)
    - Colapsa espaços
    """
    if not text:
        return ''
    text = text.upper()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def apply_phonetic(text: str) -> str:
    """Aplica as regras fonéticas PT/EN/ES em sequência."""
    for pattern, replacement in _COMPILED_RULES:
        text = pattern.sub(replacement, text)
    return text


def phonetic_key(text: str) -> str:
    """Normaliza e aplica fonética — chave canônica para comparação."""
    return apply_phonetic(normalize(text))
