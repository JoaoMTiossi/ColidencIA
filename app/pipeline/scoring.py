"""
Camada 4 — Scoring composto.
Calcula o score final ponderado e aplica overrides.
"""
from __future__ import annotations

from ..config import (
    CLASSES_CAUTELA_ALTA,
    ELEMENTOS_DESGASTADOS,
    FATOR_CAUTELA,
    PESO_AFINIDADE_SPEC,
    PESO_BONUS,
    PESO_FONETICA,
    PESO_NUCLEO_MARCARIO,
    PESO_SIMILARIDADE_NOME,
    PESO_TIPO_MARCA,
    THRESHOLD_SCORE_FINAL,
)
from ..utils.normalizacao import normalizar_base
from ..utils.similaridade import jaro_winkler
from .especificacao import _afinidade_correlatas


def _fator_distintividade(nucleo: str) -> float:
    """Fator 0.3–1.0 baseado na força distintiva do núcleo."""
    toks = normalizar_base(nucleo).split()
    if not toks:
        return 0.7
    desg = sum(t in ELEMENTOS_DESGASTADOS for t in toks)
    base = 1.0 - 0.5 * (desg / len(toks))
    if len("".join(toks)) <= 3:
        base *= 0.7
    return max(0.3, base)


def _classificar(score: float) -> str:
    if score >= 0.80:
        return "ALTA"
    if score >= 0.65:
        return "MEDIA"
    if score >= 0.55:
        return "BAIXA"
    return "NENHUMA"


def _score_tipo_marca(par: dict) -> float:
    """Ajuste pelo tipo de marca (apresentação)."""
    if par.get("is_sigla"):
        return 0.5  # siglas — peso neutro
    return 0.7  # padrão


def camada4(candidatos: list[dict]) -> list[dict]:
    """
    Aplica scoring composto e filtra por THRESHOLD_SCORE_FINAL.

    Score = (
        score_nome       * PESO_SIMILARIDADE_NOME +
        score_spec       * PESO_AFINIDADE_SPEC +
        score_nucleo     * PESO_NUCLEO_MARCARIO +
        score_fonetico   * PESO_FONETICA +
        tipo_marca       * PESO_TIPO_MARCA +
        bonus_classe     * PESO_BONUS
    )
    """
    aprovados: list[dict] = []

    for par in candidatos:
        s_nome = par.get("score_nome", 0.0)
        s_spec = par.get("score_spec", 0.0)
        s_nucleo = par.get("score_nucleo", 0.0)
        s_fon = par.get("score_fonetico", 0.0)
        s_tipo = _score_tipo_marca(par)

        # Bonus contínuo baseado na afinidade de classes
        ncl_a = par.get("ncl_base", 0)
        ncl_b = par.get("ncl_rpi", 0)
        if ncl_a == ncl_b and ncl_a > 0:
            af_classes = 1.0
        else:
            af_classes = _afinidade_correlatas(ncl_a, ncl_b)
        bonus = 0.8 * af_classes

        # Ajustes por tipo de marca
        peso_nome = PESO_SIMILARIDADE_NOME
        peso_spec = PESO_AFINIDADE_SPEC
        if par.get("is_marca_generica"):
            peso_nome -= 0.10
            peso_spec += 0.10
        if par.get("is_sigla"):
            s_fon_adj = 0.0
            peso_nome_adj = peso_nome + 0.10
        else:
            s_fon_adj = s_fon
            peso_nome_adj = peso_nome

        score = (
            s_nome   * peso_nome_adj +
            s_spec   * peso_spec +
            s_nucleo * PESO_NUCLEO_MARCARIO +
            s_fon_adj * PESO_FONETICA +
            s_tipo   * PESO_TIPO_MARCA +
            bonus    * PESO_BONUS
        )
        score = min(1.0, score)

        # Gate: nome deve ter similaridade mínima.
        # Para classes pouco correlatas (af < 0.65) exigimos nome mais próximo.
        nome_min = 0.90 if af_classes < 0.65 else 0.72
        if s_nome < nome_min and s_nucleo < 0.82:
            continue

        # Gate: ambos núcleos triviais — só passa se quase idêntico ou
        # mesma classe com núcleo quase igual
        ambos_genericos = par.get("nucleo_base_generico") and par.get("nucleo_rpi_generico")
        if ambos_genericos:
            if s_nome < 0.92 and not (ncl_a == ncl_b and s_nucleo >= 0.95):
                continue

        # Gate: prefixo genérico compartilhado com partes distintivas muito diferentes.
        # Ex: "CAFÉ JOAO" vs "CAFÉ MARIA" — "cafe" inflacionou score_nome, mas as
        # partes distintivas "joao" e "maria" são completamente diferentes.
        nd_base = par.get("nucleo_distintivo_base", "")
        nd_rpi = par.get("nucleo_distintivo_rpi", "")
        if nd_base and nd_rpi:
            sim_distintos = jaro_winkler(nd_base, nd_rpi)
            if sim_distintos < 0.65 and s_nome < 0.88:
                continue

        # Penalidade cross-class: marcas frágeis em classes sem correlação
        if af_classes == 0.0 and ncl_a != ncl_b:
            fator = _fator_distintividade(par.get("nucleo_base", "")) * _fator_distintividade(par.get("nucleo_rpi", ""))
            score = score * fator

        # Override: nome idêntico → mínimo 0.85
        if par.get("camada_deteccao") == 1 and "nome_identico" in str(par.get("motivo", "")):
            score = max(score, 0.85)

        # Override: núcleo idêntico → mínimo 0.70
        if s_nucleo >= 0.99:
            score = max(score, 0.70)

        # Threshold mais baixo para classes de saúde
        threshold = THRESHOLD_SCORE_FINAL
        if ncl_a in CLASSES_CAUTELA_ALTA or ncl_b in CLASSES_CAUTELA_ALTA:
            threshold = threshold * FATOR_CAUTELA

        if score >= threshold:
            updated = dict(par)
            updated["score_final"] = round(score, 4)
            updated["classificacao"] = _classificar(score)
            updated["camada_deteccao"] = par.get("camada_deteccao", 4)
            aprovados.append(updated)

    return aprovados
