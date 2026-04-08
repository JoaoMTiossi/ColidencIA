"""
Funções de normalização textual para o pipeline de colidência.
"""
from __future__ import annotations

import re
import unicodedata


def remover_acentos(text: str) -> str:
    """Remove acentos e diacríticos."""
    norm = unicodedata.normalize("NFD", text)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def normalizar_base(text: str) -> str:
    """
    Normalização base:
    - lowercase
    - sem acentos
    - sem pontuação (exceto hífens que separam palavras → espaço)
    - sem espaços duplos
    """
    if not text:
        return ""
    t = text.lower()
    t = remover_acentos(t)
    # Hífen entre palavras → espaço
    t = re.sub(r"(?<=\w)-(?=\w)", " ", t)
    # Remover demais pontuações
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalizar_para_hash(text: str) -> str:
    """
    Normalização para comparação hash (nome idêntico):
    lowercase, sem acentos, sem espaços, sem pontuação.
    """
    return re.sub(r"\s+", "", normalizar_base(text))


def bigramas(text: str) -> set[str]:
    """Gera bigramas de caracteres do texto normalizado."""
    norm = normalizar_base(text).replace(" ", "")
    if len(norm) < 2:
        return {norm} if norm else set()
    return {norm[i : i + 2] for i in range(len(norm) - 1)}


def jaccard_bigramas(a: str, b: str) -> float:
    """Similaridade de Jaccard sobre bigramas."""
    bg_a = bigramas(a)
    bg_b = bigramas(b)
    if not bg_a and not bg_b:
        return 1.0
    if not bg_a or not bg_b:
        return 0.0
    inter = len(bg_a & bg_b)
    union = len(bg_a | bg_b)
    return inter / union if union else 0.0
