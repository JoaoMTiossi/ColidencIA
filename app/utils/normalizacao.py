"""
Funções de normalização textual para o pipeline de colidência.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache


def remover_acentos(text: str) -> str:
    """Remove acentos e diacríticos."""
    norm = unicodedata.normalize("NFD", text)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# Tratamento de números (Camada 0)
# ---------------------------------------------------------------------------
# Regra de negócio (definida na calibração):
#   - Ano (4 dígitos em 1990-2030, havendo outro token)  → complemento (removido)
#   - Hora de serviço ("24h", "24hs", "24 horas", "12h")  → complemento (removido)
#   - Demais números                                      → grafados por extenso
#     (ex.: "STUDIO 54" → "studio cinquenta quatro"), para que o número ganhe
#     código fonético e case com marcas que o escrevem por extenso.
#
# O extenso é gerado SEM o conectivo "e" para manter os tokens do número
# contíguos — assim a extração de núcleo não quebra em "cinquenta E quatro".
_NUM_UNID = ["", "um", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito",
             "nove", "dez", "onze", "doze", "treze", "quatorze", "quinze",
             "dezesseis", "dezessete", "dezoito", "dezenove"]
_NUM_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
            "setenta", "oitenta", "noventa"]
_NUM_CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
            "seiscentos", "setecentos", "oitocentos", "novecentos"]

_RE_HORA_SERVICO = re.compile(r"\b(\d{1,2})\s*h(?:r?s|oras?)?\b", re.IGNORECASE)


def _extenso_ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    partes: list[str] = []
    centena, resto = divmod(n, 100)
    if centena:
        partes.append(_NUM_CEM[centena])
    if resto:
        if resto < 20:
            partes.append(_NUM_UNID[resto])
        else:
            dezena, unidade = divmod(resto, 10)
            partes.append(_NUM_DEZ[dezena])
            if unidade:
                partes.append(_NUM_UNID[unidade])
    return " ".join(partes)


def numero_por_extenso(n: int) -> str:
    """Converte um inteiro (0–999999) para extenso pt-BR, sem o conectivo "e"."""
    if n == 0:
        return "zero"
    if n >= 1_000_000:
        # CPF, CNPJ e outros identificadores — não são elementos de marca;
        # devolve como string para não quebrar e não poluir o extenso.
        return str(n)
    if n < 1000:
        return _extenso_ate_999(n)
    milhar, resto = divmod(n, 1000)
    prefixo = "mil" if milhar == 1 else _extenso_ate_999(milhar) + " mil"
    if resto == 0:
        return prefixo
    return prefixo + " " + _extenso_ate_999(resto)


def tratar_numeros(text: str) -> str:
    """
    Aplica as regras de número sobre texto já normalizado (minúsculo, sem acento).

    Anos e horas-de-serviço são removidos (tratados como complemento descritivo);
    os demais números são grafados por extenso.
    """
    # 1. Hora de serviço → remove
    t = _RE_HORA_SERVICO.sub(" ", text)
    tokens = t.split()
    n_tokens_texto = sum(1 for tk in tokens if not tk.isdigit())
    out: list[str] = []
    for tk in tokens:
        if tk.isdigit():
            valor = int(tk)
            # 2. Ano plausível (1990-2030, 4 dígitos) com outro token → remove
            if len(tk) == 4 and 1990 <= valor <= 2030 and n_tokens_texto >= 1:
                continue
            # 3. CPF/CNPJ/processo (≥ 7 dígitos) — identificadores, não
            #    elementos de marca; mantém como token opaco para não poluir.
            if len(tk) >= 7:
                out.append(tk)
                continue
            # 4. Número distintivo → extenso
            out.append(numero_por_extenso(valor))
        else:
            out.append(tk)
    return " ".join(out)


def _colapsar_dobras(text: str) -> str:
    """
    Simplifica letras repetidas em sequência (dobras) em tokens com ≥ 4 chars.

    O limite de 4 preserva siglas/abreviações curtas onde a dobra é a própria
    identidade ("LL", "MM"), enquanto corrige variações ortográficas em nomes
    ("MATTOS"→"matos", "BELLA"→"bela", "LARISSA"→"larisa").
    """
    return " ".join(
        re.sub(r"(.)\1+", r"\1", tok) if len(tok) >= 4 else tok
        for tok in text.split()
    )


@lru_cache(maxsize=200_000)
def normalizar_base(text: str, considerar_dobra: bool = False) -> str:
    """
    Normalização base:
    - lowercase
    - sem acentos
    - sem pontuação (exceto hífens que separam palavras → espaço)
    - números tratados (ano/hora → removidos; demais → extenso)
    - dobras simplificadas (salvo se considerar_dobra=True)
    - sem espaços duplos

    Quando ``considerar_dobra=True``, letras repetidas são preservadas — usado
    para marcas em que a dobra é elemento distintivo essencial.
    """
    if not text:
        return ""
    t = text
    # Siglas com espaço ou ponto entre letras maiúsculas (opera ANTES do lowercase
    # para não tocar em artigos/preposições minúsculos como "a", "o", "e").
    # Exemplos: "M G" → "MG", "H.O.F" → "HOF", "M. G." → "MG", "J C B" → "JCB"
    # Requer sequência de 2+ letras maiúsculas separadas só por espaços/pontos.
    # Os lookarounds incluem letras ACENTUADAS (À-ÖØ-öø-ÿ): sem isso, o "O" final
    # de "CONSTRUÇÃO" era tratado como letra isolada (Ã ∉ [A-Za-z]) e
    # "CONSTRUÇÃO E REFORMAS" colapsava para "construcaoe reformas" — corrompendo
    # o núcleo e disparando is_sigla=True em nomes longos.
    t = re.sub(
        r"(?<![A-Za-zÀ-ÖØ-öø-ÿ\d])([A-Z])(?:[. ]+[A-Z])+[. ]*(?![A-Za-zÀ-ÖØ-öø-ÿ\d])",
        lambda m: re.sub(r"[. ]", "", m.group(0)),
        t,
    )
    t = t.lower()
    t = remover_acentos(t)
    # Pontos em siglas minúsculas remanescentes (h.o.f → hof) — cobre fontes já em caixa baixa
    t = re.sub(
        r"(?<![a-z\d])([a-z])(?:\.[a-z])+\.?(?![a-z\d])",
        lambda m: m.group(0).replace(".", ""),
        t,
    )
    # Letra única + ponto + palavra: estilização de nome ("I.DEAL" → "ideal",
    # "D.CASA" → "dcasa") — o ponto é ornamental, não separador de sigla.
    t = re.sub(r"(?<![a-z\d])([a-z])\.(?=[a-z]{2,})", r"\1", t)
    # Hífen entre palavras → espaço
    t = re.sub(r"(?<=\w)-(?=\w)", " ", t)
    # & entre letras → concatena sem espaço (L&L → LL, M&M → MM, S&P → SP)
    t = re.sub(r"(?<=\w)&(?=\w)", "", t)
    # Remover demais pontuações
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Tratamento de números (ano/hora → complemento; demais → extenso)
    t = tratar_numeros(t)
    # Simplificação de dobras (a menos que a marca peça para considerá-las)
    if not considerar_dobra:
        t = _colapsar_dobras(t)
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
