"""
Extração do núcleo marcário — parte distintiva da marca.
"""
from __future__ import annotations

import re

from ..config import COMPLEMENTOS_DESCRITIVOS, ELEMENTOS_DESGASTADOS
from .normalizacao import _colapsar_dobras, normalizar_base


def _augmentar_dobras(palavras: frozenset[str]) -> frozenset[str]:
    """Inclui a forma com dobra simplificada de cada palavra do vocabulário.

    Como ``normalizar_base`` colapsa dobras ("pizzaria"→"pizaria",
    "terra"→"tera"), os tokens normalizados não casariam com as entradas
    originais das listas. Augmentar com a forma colapsada mantém o
    reconhecimento de complementos/desgastados consistente.
    """
    return frozenset(palavras) | frozenset(_colapsar_dobras(p) for p in palavras)


_COMPLEMENTOS = _augmentar_dobras(COMPLEMENTOS_DESCRITIVOS)
_DESGASTADOS = _augmentar_dobras(ELEMENTOS_DESGASTADOS)

# Stopwords que indicam início do complemento descritivo
_STOPWORDS: frozenset[str] = frozenset({
    "de", "do", "da", "dos", "das", "e", "em", "com", "para", "por",
    "ltda", "me", "epp", "eireli", "sa", "ss", "mei", "s/a",
    "comercio", "industria", "servicos", "solucoes", "assessoria",
    "consultoria", "grupo", "holding", "participacoes",
    "and", "of", "the", "for", "by", "with",
    "y", "del", "los", "las",
})

# Honoríficos/apelações religiosas: "SÃO JOÃO", "SANTA MARIA", "NOSSA SENHORA",
# "BOM JESUS". O honorífico + o nome que o segue formam uma apelação comum, sem
# distintividade própria — ambos são descartados do núcleo distintivo.
_HONORIFICOS: frozenset[str] = frozenset({
    "sao", "santo", "santa", "sra", "senhora", "nossa", "nsa",
    "dom", "bom", "boa", "frei", "padre", "madre",
})

# Padrão de sigla: 2-4 letras maiúsculas, pode ter ponto separando
_RE_SIGLA = re.compile(r'^[A-Z]{2,4}\.?$')

# Sigla separada por pontos/espaços na origem: "M.S.", "M G", "H.O.F", "J.C.B".
# Exige sequência de 2+ letras isoladas separadas só por pontos/espaços.
_RE_SIGLA_SEPARADA = re.compile(
    r"(?<![A-Za-z\d])[A-Za-z](?:[. ]+[A-Za-z])+[. ]*(?![A-Za-z\d])"
)


def extrair_nucleo(marca: str) -> str:
    """
    Extrai o núcleo marcário (parte distintiva da marca).

    Quando a marca começa com complemento descritivo (tipo de negócio),
    pula-o para encontrar o elemento verdadeiramente distintivo.

    Exemplos:
        "INSPIRE STUDIO DE PILATES"         → "INSPIRE"
        "INSTITUTO DA ACÚSTICA"             → "acustica"
        "PIZZARIA DO VAQUEIRO 2022"         → "vaqueiro 2022"
        "BARBEARIA STUDIO MATTOS"           → "mattos"
        "RESTAURANTE CASA DO NORDESTINO"    → "nordestino"
        "CAVALINHO AZUL"                    → "cavalinho azul"
    """
    norm = normalizar_base(marca)
    tokens = norm.split()

    # Pular complementos descritivos do início (ex: restaurante, instituto, barbearia)
    # e stopwords sequenciais (de, do, da) antes da parte distintiva.
    start = 0
    if len(tokens) > 1:
        while start < len(tokens) and tokens[start] in _COMPLEMENTOS:
            start += 1
        while start < len(tokens) and tokens[start] in _STOPWORDS:
            start += 1

    resto = tokens[start:]
    nucleo: list[str] = []
    i = 0
    while i < len(resto):
        tok = resto[i]
        if tok in _STOPWORDS and nucleo:
            # Conector "e" entre dois elementos distintivos (padrão de razão
            # social de sociedade: "MATTOS E SILVA", "PINHEIRO E SOUZA") integra
            # o núcleo — não encerra a coleta. Só vale se o próximo token também
            # for distintivo (não stopword, não complemento).
            prox = resto[i + 1] if i + 1 < len(resto) else None
            if (
                tok == "e"
                and prox is not None
                and prox not in _STOPWORDS
                and prox not in _COMPLEMENTOS
            ):
                nucleo.append(tok)
                i += 1
                continue
            break
        if tok in _COMPLEMENTOS and nucleo:
            break
        nucleo.append(tok)
        i += 1

    nucleo_str = " ".join(nucleo) if nucleo else norm
    # PROTEÇÃO contra strip cego de complementos: se o que sobrou for fraco
    # (vazio, só termos desgastados ou só números), o recorte não revelou uma
    # âncora distintiva — mantém o nome completo como núcleo. Evita
    # "CAFE ROYAL"→"royal" e "STUDIO 54"→"54"; nesses casos a marca é fraca e
    # a barra de colisão fica alta via os gates de marca genérica.
    nucleo_tokens = nucleo_str.split()
    sobra_fraca = not nucleo_tokens or all(
        t in _DESGASTADOS or t.isdigit() for t in nucleo_tokens
    )
    if sobra_fraca:
        return norm
    # Permite siglas de 2 chars (LL, MS, LK); só rejeita núcleo de 1 char
    if len(nucleo_str.replace(" ", "")) < 2:
        return norm
    return nucleo_str


def is_sigla(texto: str) -> bool:
    """
    Retorna True quando o texto é uma sigla/abreviação — não uma palavra curta
    comum. Evidências de sigla:
      - padrão separado por pontos/espaços na origem ("M.S.", "H O F", "J.C.B");
      - forma curta (≤4 chars) sem vogais ("MS", "LK", "BMW", "JCB", "RM");
      - caractere único.

    Palavras curtas pronunciáveis ("NEXO", "CASA", "MALA", "ASIA") NÃO são
    siglas — o tratamento de sigla (fonética zerada, peso de nome elevado) só
    deve incidir sobre abreviações genuínas.
    """
    if _RE_SIGLA_SEPARADA.search(texto or ""):
        return True
    norm = normalizar_base(texto).replace(" ", "")
    if not norm.isalpha():
        return False
    if len(norm) <= 1:
        return True
    if len(norm) > 4:
        return False
    # Curto (≤4): é sigla se NÃO tiver estrutura silábica pronunciável, isto é,
    # nenhuma vogal precedida de consoante (padrão CV). "IBM"/"MS"/"BMW"/"USP"
    # não têm CV → siglas. "NEXO"/"CASA"/"MALA"/"OVOS"/"SOL" têm CV → palavras.
    tem_silaba = any(
        norm[i] in "aeiou" and norm[i - 1] not in "aeiou"
        for i in range(1, len(norm))
    )
    return not tem_silaba


def is_nome_proprio(marca: dict) -> bool:
    """
    Retorna True quando a marca corresponde ao nome do próprio titular
    (registrante) — ou seja, a marca É o nome do dono.

    Critério: todos os tokens significativos da marca (descartando stopwords e
    complementos descritivos) aparecem no nome do titular. Trabalha sobre o
    texto normalizado, sem depender de capitalização.

    Exemplos:
        marca="CARLOS MOTTA ADVOCACIA", titular="CARLOS MOTTA"   → True
        marca="NEXO", titular="NEXO INDUSTRIA LTDA"              → True
        marca="COCA COLA", titular="OUTRA EMPRESA SA"            → False
    """
    nome = normalizar_base(marca.get("marca") or marca.get("nome_marca", ""))
    titular = normalizar_base(marca.get("titular", ""))
    if not nome or not titular:
        return False
    nome_tokens = set(nome.split())
    # Tokens significativos do titular (descartando tipos societários e
    # complementos) precisam estar todos presentes na marca.
    titular_tokens = [
        t for t in titular.split()
        if t not in _STOPWORDS and t not in _COMPLEMENTOS
    ]
    if not titular_tokens:
        return False
    return all(t in nome_tokens for t in titular_tokens)


def is_marca_generica(nucleo: str) -> bool:
    """Retorna True quando o núcleo não tem elemento distintivo próprio.

    Critério primário: se a depuração das bordas (complementos, stopwords,
    desgastados e apelações honoríficas) não deixa nenhum elemento, a marca é
    inteiramente genérica. Mantém-se também o teste de proporção de desgaste
    para núcleos com sobra fraca mas não vazia.
    """
    tokens = normalizar_base(nucleo).split()
    if not tokens:
        return False
    if not extrair_nucleo_distintivo(nucleo):
        return True
    desg = sum(1 for t in tokens if t in _DESGASTADOS)
    if desg == len(tokens):
        return True
    if len(tokens) >= 3 and desg / len(tokens) >= 2 / 3:
        return True
    return False


def extrair_nucleo_distintivo(nucleo: str) -> str:
    """
    Remove tokens não-distintivos das bordas do núcleo para revelar o elemento
    verdadeiramente distintivo. São aparados das pontas: complementos setoriais,
    stopwords/conectores e termos desgastados. Apelações honoríficas ("SÃO
    JOÃO", "SANTA MARIA") são descartadas junto com o nome que as segue, por
    formarem designação comum sem distintividade própria.

    Exemplos:
        "saude jaguara"        → "jaguara"
        "cafe joao"            → "joao"
        "saude forte"          → ""   (todos desgastados)
        "churrascaria do rei"  → ""   (complemento + stopword + desgastado)
        "sao joao"             → ""   (apelação honorífica)
        "matos e silva"        → "matos e silva"  (conector interno preservado)
    """
    tokens = normalizar_base(nucleo).split()
    fraco = _STOPWORDS | _COMPLEMENTOS | _DESGASTADOS
    # Apara a borda esquerda
    while tokens:
        if tokens[0] in _HONORIFICOS and len(tokens) >= 2:
            tokens = tokens[2:]
            continue
        if tokens[0] in fraco:
            tokens.pop(0)
            continue
        break
    # Apara a borda direita
    while tokens and tokens[-1] in fraco:
        tokens.pop()
    return " ".join(tokens)


def is_desgastado(marca: str) -> bool:
    """Retorna True se qualquer token principal é um elemento desgastado."""
    tokens = set(normalizar_base(marca).split())
    return bool(tokens & _DESGASTADOS)
