"""
Metaphone adaptado para português brasileiro.
Produz uma chave fonética de até 6 caracteres.
"""
from __future__ import annotations

import re
import unicodedata


def _remove_acentos(text: str) -> str:
    """Remove acentos e diacríticos via NFD decomposition."""
    norm = unicodedata.normalize("NFD", text)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def metaphone_ptbr(palavra: str) -> str:
    """
    Gera a chave fonética Metaphone para PT-BR.

    Transformações aplicadas em sequência sobre a palavra em MAIÚSCULAS,
    sem acentos.
    """
    if not palavra:
        return ""

    # Normalizar: maiúsculas, sem acentos
    w = _remove_acentos(palavra.upper().strip())

    # Remover caracteres não-alfabéticos
    w = re.sub(r"[^A-Z]", "", w)
    if not w:
        return ""

    # --- Substituições iniciais ---

    # H inicial silencioso
    if w.startswith("H"):
        w = w[1:]
    if not w:
        return ""

    # PH → F
    w = w.replace("PH", "F")

    # GU + E/I → G
    w = re.sub(r"GU(?=[EI])", "G", w)

    # QU + E/I → K
    w = re.sub(r"QU(?=[EI])", "K", w)

    # CH → X
    w = w.replace("CH", "X")

    # LH → LI
    w = w.replace("LH", "LI")

    # NH → NI
    w = w.replace("NH", "NI")

    # SS → S
    w = w.replace("SS", "S")

    # Ç → S
    w = w.replace("Ç", "S")

    # RR → R
    w = w.replace("RR", "R")

    # TH → T
    w = w.replace("TH", "T")

    # W → V
    w = w.replace("W", "V")

    # Consoantes duplas → simples
    w = re.sub(r"([BCDFGHJKLMNPQRSTVXYZ])\1+", r"\1", w)

    # --- Construção caractere a caractere ---
    result: list[str] = []
    n = len(w)

    for i, c in enumerate(w):
        if not result and c in "AEIOU":
            result.append(c)
            continue

        if c in "AEIOU":
            # Vogais não-iniciais são descartadas (Metaphone clássico)
            continue

        # Y em posição não-inicial é tratado como vogal → descartado
        if c == "Y" and result:
            continue

        next_c = w[i + 1] if i + 1 < n else ""
        prev_c = w[i - 1] if i > 0 else ""

        if c == "C":
            if next_c in "EI":
                result.append("S")
            else:
                result.append("K")
        elif c == "G":
            if next_c in "EI":
                result.append("J")
            else:
                result.append("G")
        elif c == "K":
            result.append("K")
        elif c == "Q":
            result.append("K")
        elif c == "S":
            # S intervocálico → Z (mas entre consoantes → S)
            if prev_c in "AEIOU" and next_c in "AEIOU":
                result.append("Z")
            else:
                result.append("S")
        elif c == "X":
            result.append("X")
        elif c == "Z":
            # Z final → S
            if i == n - 1:
                result.append("S")
            else:
                result.append("Z")
        elif c == "Y":
            result.append("I")
        elif c == "J":
            result.append("J")
        elif c == "R":
            result.append("R")
        elif c == "L":
            result.append("L")
        elif c == "M":
            result.append("M")
        elif c == "N":
            result.append("N")
        elif c == "P":
            if next_c == "H":
                result.append("F")
            else:
                result.append("P")
        elif c == "B":
            result.append("B")
        elif c == "D":
            result.append("D")
        elif c == "F":
            result.append("F")
        elif c == "H":
            pass  # H intervocálico silencioso
        elif c == "T":
            result.append("T")
        elif c == "V":
            result.append("V")
        else:
            result.append(c)

    key = "".join(result)

    # Limitar a 6 caracteres
    return key[:6]
