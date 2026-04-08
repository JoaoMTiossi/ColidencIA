"""
Camada 4 — Scoring composto.
Calcula o score final ponderado e aplica overrides.
"""
from __future__ import annotations

from ..config import (
    CLASSES_CAUTELA_ALTA,
    FATOR_CAUTELA,
    PESO_AFINIDADE_SPEC,
    PESO_BONUS,
    PESO_FONETICA,
    PESO_NUCLEO_MARCARIO,
    PESO_SIMILARIDADE_NOME,
    PESO_TIPO_MARCA,
    THRESHOLD_SCORE_FINAL,
)


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

        # Bonus para classes na mesma NCL ou colidentes
        ncl_a = par.get("ncl_base", 0)
        ncl_b = par.get("ncl_rpi", 0)
        bonus = 0.8 if (ncl_a == ncl_b and ncl_a > 0) else (0.5 if par.get("classes_colidem_flag") else 0.0)

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
