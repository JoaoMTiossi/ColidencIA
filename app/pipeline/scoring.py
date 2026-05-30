"""
Camada 4 — Scoring composto.
Calcula o score final ponderado e aplica overrides.

Modelo de decisão multicriterio: blend de SAW (Simple Additive Weighting)
com superfície 2D (similaridade × afinidade) que implementa explicitamente
a Regra Inversa do INPI: menor semelhança entre sinais exige maior afinidade
mercadológica para configurar colidência (LPI art. 124, XIX).
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
    PESO_REGRA_INVERSA,
    PESO_SIMILARIDADE_NOME,
    PESO_TIPO_MARCA,
    THRESHOLD_SCORE_FINAL,
)
from ..utils.distintividade import match_distintivo
from ..utils.normalizacao import normalizar_base
from .especificacao import _afinidade_classes, _afinidade_correlatas


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


def _af_minima(s_sim: float) -> float:
    """
    Afinidade mercadológica mínima requerida para colidência, dado o nível
    de similaridade entre os sinais.

    Implementa a Regra Inversa do INPI: quanto menor a semelhança, maior
    deve ser a afinidade para configurar risco de confusão.

    Retorna 1.01 quando nenhuma afinidade pode compensar a baixíssima
    semelhança (s_sim < 0.55) — funcionando como gate de descarte.
    """
    if s_sim >= 0.92:
        return 0.20   # Quase idênticos: afinidade mínima basta
    if s_sim >= 0.85:
        return 0.30   # Alta similaridade
    if s_sim >= 0.75:
        return 0.50   # Similaridade média-alta
    if s_sim >= 0.65:
        return 0.68   # Similaridade média-baixa
    if s_sim >= 0.55:
        return 0.85   # Baixa similaridade: precisa de afinidade muito alta
    return 1.01        # Impossível — descarta


def _score_superficie_2d(s_sim: float, s_af: float) -> float:
    """
    Score 0-1 que mede a posição do par na superfície de decisão
    (similaridade × afinidade mercadológica).

    Captura a Regra Inversa de forma contínua: pares que estão bem acima
    do limiar de afinidade requerido recebem score mais alto.
    """
    af_req = _af_minima(s_sim)
    if s_af < af_req:
        return 0.0
    # Excesso de afinidade acima do mínimo requerido, normalizado para [0, 1]
    excesso = (s_af - af_req) / max(1.0 - af_req, 0.01)
    return min(1.0, 0.40 + 0.35 * s_sim + 0.25 * excesso)


def camada4(candidatos: list[dict]) -> list[dict]:
    """
    Aplica scoring composto e filtra por THRESHOLD_SCORE_FINAL.

    Score final = blend de:
      - SAW (pesos lineares sobre dimensões de similaridade e afinidade)
      - Superfície 2D (Regra Inversa LPI): score baseado na posição do par
        no plano (similaridade_sinal × afinidade_mercadologica)

    O gate da Regra Inversa filtra pares onde a afinidade disponível é
    insuficiente para o nível de similaridade observado — prevenindo a
    compensação indevida que o SAW puro permitia.
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
        # Usa _afinidade_classes (inclui COLLISIONS) para consistência com C3.
        # _afinidade_correlatas sozinha retorna 0 para pares em COLLISIONS mas
        # fora do CSV de correlatas, causando penalidade cross-class indevida.
        af_classes = _afinidade_classes(ncl_a, ncl_b)
        bonus = 0.8 * af_classes

        # Gate: termo desgastado em classes sem relação — descarta sem score
        if par.get("is_desgastado") and af_classes == 0.0 and ncl_a != ncl_b:
            continue

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

        # ── Gate: Regra Inversa LPI ────────────────────────────────────────
        # Melhor evidência de similaridade entre os sinais
        s_sim = max(s_nome, s_nucleo, s_fon_adj)
        # Melhor evidência de afinidade mercadológica
        s_af = max(s_spec, af_classes)

        # Se a afinidade disponível não alcança o mínimo para este nível de
        # similaridade, o par não configura risco de colidência.
        if s_af < _af_minima(s_sim):
            continue
        # ──────────────────────────────────────────────────────────────────

        score = (
            s_nome    * peso_nome_adj +
            s_spec    * peso_spec +
            s_nucleo  * PESO_NUCLEO_MARCARIO +
            s_fon_adj * PESO_FONETICA +
            s_tipo    * PESO_TIPO_MARCA +
            bonus     * PESO_BONUS
        )
        score = min(1.0, score)

        # Gate: ambos núcleos triviais — só passa se quase idêntico ou
        # mesma classe com núcleo quase igual
        ambos_genericos = par.get("nucleo_base_generico") and par.get("nucleo_rpi_generico")
        if ambos_genericos:
            if s_nome < 0.92 and not (ncl_a == ncl_b and s_nucleo >= 0.95):
                continue

        # Gate de distintividade: a colidência exige que o ELEMENTO DISTINTIVO
        # das marcas seja semelhante. Palavras descritivas/setoriais comuns
        # ("BARBEARIA", "IGREJA", "ODONTOLOGIA", "VEÍCULOS") inflam a similaridade
        # do nome completo sem refletir risco real. Comparamos apenas os tokens
        # distintivos (orto OU fonética); se eles divergem e o nome completo não
        # é quase idêntico, descarta antes da IA.
        md = match_distintivo(par.get("marca_base", ""), par.get("marca_rpi", ""), ncl_a, ncl_b)
        if md is None:
            # Marca puramente descritiva — sem sinal próprio. Só passa se o
            # nome completo for quase idêntico (variação ortográfica evidente).
            if s_nome < 0.92:
                continue
        elif ncl_a == ncl_b:
            # Mesma classe: exige sinal distintivo sólido.
            if md < 0.80 and s_nome < 0.90:
                if s_fon < 0.85:
                    continue
            if md < 0.90:
                score *= 0.85
        else:
            # Cross-class: o sinal distintivo precisa ser forte E é necessária
            # evidência real de afinidade (spec semântica ou correlatas acima do
            # piso de colisão). Evita que afinidade de matriz (piso 0.60) resgate
            # marcas cujos produtos/serviços são genuinamente distintos.
            s_sem = par.get("score_spec_semantico", 0.0) or 0.0
            afinidade_real = s_sem >= 0.25 or af_classes >= 0.85
            if md < 0.90 and s_nome < 0.92:
                continue
            if not afinidade_real:
                continue
            if md < 0.95:
                score *= 0.85

        # ── Superfície 2D — score da Regra Inversa ────────────────────────
        # Blend: (1 - w) * SAW + w * score_2D
        # O score_2D corrige a compensação indevida do SAW puro (ex.: alta
        # afinidade não deve resgatar marcas com sinais muito diferentes).
        score_ri = _score_superficie_2d(s_sim, s_af)
        score = (1.0 - PESO_REGRA_INVERSA) * score + PESO_REGRA_INVERSA * score_ri
        # ──────────────────────────────────────────────────────────────────

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
            updated["score_ri"] = round(score_ri, 4)
            updated["af_classes"] = round(af_classes, 4)
            updated["classificacao"] = _classificar(score)
            updated["camada_deteccao"] = par.get("camada_deteccao", 4)
            aprovados.append(updated)

    return aprovados
