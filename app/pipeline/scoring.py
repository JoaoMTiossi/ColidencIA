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
from ..utils.metaphone_ptbr import metaphone_ptbr
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


def _nivel_severidade(
    md: float | None,
    s_nome: float,
    s_fon: float,
    mesma_classe: bool,
    af_classes: float,
    s_spec: float,
) -> str:
    """
    Nível de severidade no modelo de VIGILÂNCIA DE MARCA (trademark watch).

    Diferente da classificação por score (que mede confiança no alerta), o
    nível responde "quão urgente é revisar este caso" sob a ótica do cliente
    que monitora a própria marca:

    - ALTA   : risco direto de confusão. Mesma classe com núcleo forte, OU
               cross-class com núcleo idêntico E afinidade mercadológica.
    - MEDIA  : núcleo idêntico/quase em classes distintas (diluição, prazo de
               oposição) OU mesma classe com sinal moderado.
    - VIGIAR : sinal mais fraco — vale acompanhar, baixa prioridade.

    A lógica reflete o gold-set do especialista: marcas com elemento distintivo
    idêntico são sinalizadas MESMO em classes diferentes (proteção marcária),
    o que o gate de afinidade puro descartava.
    """
    md_v = md if md is not None else 0.0
    sinal = max(md_v, s_nome)
    afinidade = af_classes >= 0.65 or s_spec >= 0.80

    if mesma_classe:
        if md_v >= 0.85 or s_nome >= 0.90:
            return "ALTA"
        if md_v >= 0.70 or s_fon >= 0.88 or s_nome >= 0.80:
            return "MEDIA"
        return "VIGIAR"
    # Cross-class
    if sinal >= 0.92:
        return "ALTA" if afinidade else "MEDIA"
    if sinal >= 0.85:
        return "MEDIA" if afinidade else "VIGIAR"
    return "VIGIAR"


def _nucleos_metafonicamente_equivalentes(par: dict) -> bool:
    """Metaphone do nucleo_distintivo INTEIRO (sem espaços) de A == o de B.

    Espelha o critério de escape usado no bypass de classe do C2
    (fonetica.py) — mesma marca quase-idêntica, agora avaliada com os
    campos já propagados no candidato.
    """
    nuc_a = (par.get("nucleo_distintivo_base") or "").replace(" ", "")
    nuc_b = (par.get("nucleo_distintivo_rpi") or "").replace(" ", "")
    if not nuc_a or not nuc_b:
        return False
    cod_a = metaphone_ptbr(nuc_a)
    return bool(cod_a) and cod_a == metaphone_ptbr(nuc_b)


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

        # Similaridade do elemento DISTINTIVO (computada cedo: governa tanto os
        # gates quanto o nível de severidade). Núcleo idêntico/quase entre as
        # marcas é o sinal mais forte de vigilância marcária.
        md = match_distintivo(par.get("marca_base", ""), par.get("marca_rpi", ""), ncl_a, ncl_b)
        mesma_classe = (ncl_a == ncl_b)
        # "Núcleo forte" = elemento distintivo idêntico ou quase. Sob a ótica de
        # vigilância de marca, esses pares NÃO devem ser descartados mesmo sem
        # afinidade mercadológica (risco de diluição / prazo de oposição).
        nucleo_forte = max(md if md is not None else 0.0, s_nome) >= 0.92

        # Vigilância de termo desgastado idêntico: quando as duas marcas
        # compartilham o MESMO termo desgastado ("TOP" × "TOP SENSE",
        # "MAX EVENTOS" × "MAX MUSIC") em classes com afinidade real, o
        # titular da marca fraca precisa do alerta (prazo de oposição) mesmo
        # sem distintividade — o gold set do especialista marca esses pares.
        # O par não é descartado pelos gates; o piso é o threshold (score
        # mínimo → classificação BAIXA) e o nível de severidade comunica a
        # prioridade real (VIGIAR/MEDIA), espelhando o modelo do nucleo_forte.
        desg_a = {t for t in normalizar_base(par.get("marca_base", "")).split()
                  if len(t) >= 2 and t in ELEMENTOS_DESGASTADOS}
        desgastado_comum = False
        if desg_a and af_classes >= 0.65:
            desg_b = {t for t in normalizar_base(par.get("marca_rpi", "")).split()
                      if len(t) >= 2 and t in ELEMENTOS_DESGASTADOS}
            desgastado_comum = bool(desg_a & desg_b)

        # ── Gate: Regra Inversa LPI ────────────────────────────────────────
        # Melhor evidência de similaridade entre os sinais. Inclui md: a
        # similaridade do ELEMENTO DISTINTIVO é o sinal juridicamente
        # relevante (art. 124, XIX) — sem ele, pares como "MM MARCIEL
        # CONSTRUÇÃO" × "MACIEL EDIFICA" (md=0.72, nome completo divergente)
        # eram descartados com exigência de afinidade impossível (1.01).
        s_sim = max(s_nome, s_nucleo, s_fon_adj, md if md is not None else 0.0)
        # Melhor evidência de afinidade mercadológica
        s_af = max(s_spec, af_classes)

        # Se a afinidade disponível não alcança o mínimo para este nível de
        # similaridade, o par não configura risco — EXCETO quando o núcleo é
        # idêntico/quase (vigilância marcária supera a Regra Inversa).
        if s_af < _af_minima(s_sim) and not nucleo_forte and not desgastado_comum:
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
        if ambos_genericos and not desgastado_comum:
            if s_nome < 0.92 and not (ncl_a == ncl_b and s_nucleo >= 0.95):
                continue

        # Gate de distintividade: a colidência exige que o ELEMENTO DISTINTIVO
        # das marcas seja semelhante. Palavras descritivas/setoriais comuns
        # ("BARBEARIA", "IGREJA", "ODONTOLOGIA", "VEÍCULOS") inflam a similaridade
        # do nome completo sem refletir risco real. Comparamos apenas os tokens
        # distintivos (orto OU fonética); se eles divergem e o nome completo não
        # é quase idêntico, descarta antes da IA.
        #
        # MODELO DE VIGILÂNCIA: núcleo idêntico/quase (nucleo_forte) nunca é
        # descartado — recebe apenas nível de severidade menor quando falta
        # afinidade mercadológica. Isso recupera os pares cross-class que o
        # especialista marca (proteção marcária) sem reintroduzir ruído.
        if md is None:
            # Marca puramente descritiva — sem sinal próprio.
            # Exceções calibradas pelo gold set:
            #   • Mesma classe + fonética/nome forte: variação ortográfica óbvia.
            #   • Mesma classe + fon ≥ 0.62 + spec ≥ 0.94: spec quase-idêntica
            #     (marcas de classe idêntica com som similar mas nome curto/diferente).
            #   • Cross-class + fon/núcleo ≥ 0.90: marcas foneticamente ou
            #     nuclearmente quase idênticas em classes relacionadas.
            #   • Cross-class + fon ≥ 0.80 + spec ≥ 0.70: som muito próximo
            #     com afinidade mercadológica relevante.
            allow_mc = mesma_classe and (
                s_nome >= 0.85 or s_fon >= 0.85
                or (s_fon >= 0.62 and s_spec >= 0.94)
            )
            allow_xc = not mesma_classe and (
                s_fon >= 0.90 or s_nucleo >= 0.90
                or (s_fon >= 0.80 and s_spec >= 0.70)
            )
            # Containment de núcleo: todos os tokens do núcleo distintivo de
            # uma marca aparecem no da outra ("CHEF" ⊂ "DU CHEF", "CANA" ⊂
            # "APIARIOS CANA") com afinidade de mercado relevante — o núcleo
            # menor está reproduzido dentro do maior (vigilância marcária).
            if not allow_mc and not allow_xc and s_spec >= 0.75:
                toks_na = set((par.get("nucleo_distintivo_base") or "").split())
                toks_nb = set((par.get("nucleo_distintivo_rpi") or "").split())
                if toks_na and toks_nb and (toks_na <= toks_nb or toks_nb <= toks_na):
                    allow_mc = allow_xc = True
            if not allow_mc and not allow_xc and not desgastado_comum:
                if s_nome < 0.92:
                    continue
        elif mesma_classe:
            # Mesma classe: exige sinal distintivo sólido.
            # Escape: spec muito alta (≥ 0.90) indica mesma sub-categoria de produto
            # — sinal de mercado sobrepõe sinal fonético moderado.
            if md < 0.80 and s_nome < 0.90:
                if s_fon < 0.85 and s_spec < 0.90:
                    continue
            if md < 0.90:
                score *= 0.85
        else:
            # Cross-class. Núcleo forte sempre passa (severidade decide o tier).
            # Sinal intermediário (0.85–0.92) exige afinidade. Sinal fraco cai.
            # Inclui s_fon_adj no sinal cross-class: fonética alta é evidência tão
            # forte quanto similaridade de nome para detectar cópia fonética.
            s_sem = par.get("score_spec_semantico", 0.0) or 0.0
            # Sinal cross-class enriquecido com dois detectores de variação:
            #   • Aglutinação: "KI SABOR" × "KISABOR" — JW dos núcleos
            #     distintivos SEM espaços reaproxima o que a tokenização separa.
            #   • Primeiro token do núcleo: "IMPÉRIO x" × "IMPÉRIO y" — o token
            #     líder idêntico é o elemento primário mesmo quando removido de
            #     tokens_distintivos pelo vocabulário de corpus.
            from ..utils.similaridade import jaro_winkler as _jw
            nuc_a = par.get("nucleo_distintivo_base") or par.get("nucleo_base", "")
            nuc_b = par.get("nucleo_distintivo_rpi") or par.get("nucleo_rpi", "")
            jw_colado = 0.0
            jw_first_tok = 0.0
            if nuc_a and nuc_b:
                jw_colado = _jw(nuc_a.replace(" ", ""), nuc_b.replace(" ", ""))
                ft_a, ft_b = nuc_a.split()[0], nuc_b.split()[0]
                if len(ft_a) >= 3 and len(ft_b) >= 3:
                    sim_ft = _jw(ft_a, ft_b)
                    if sim_ft >= 0.92:
                        jw_first_tok = sim_ft
            s_sig_cross = max(
                md if md is not None else 0, s_nome, s_fon_adj,
                jw_colado, jw_first_tok,
            )
            # Bypass de classe (C2): par cross-class sem afinidade de blocking
            # cujo sinal de nome/núcleo é muito forte. Os gates de sig/afinidade
            # abaixo foram calibrados para pares que já passaram pelo filtro de
            # classe do C2 — um par bypass_classe não passou por ele, então
            # aplicamos o mesmo alívio de nucleo_forte quando há evidência
            # equivalente (núcleo metafonicamente idêntico). Não adiciona piso
            # de score — o score composto ainda precisa superar o threshold.
            bypass_forte = bool(par.get("bypass_classe")) and (
                nucleo_forte or _nucleos_metafonicamente_equivalentes(par)
            )
            if not nucleo_forte and not bypass_forte and not desgastado_comum:
                # Escape graduado: sinal moderado (≥ 0.70) é aceito quando a
                # afinidade de especificação é alta (≥ 0.80) — mercado próximo
                # compensa sinal de nome intermediário.
                if s_sig_cross < 0.85 and not (s_sig_cross >= 0.70 and s_spec >= 0.80):
                    continue
                # Threshold de afinidade reduzido: correlação moderada entre classes
                # (≥ 0.60) é evidência suficiente quando o sinal de nome é alto.
                afinidade_ok = af_classes >= 0.60 or s_sem >= 0.20 or s_spec >= 0.80
                if not afinidade_ok:
                    continue
            if md is not None and md < 0.95:
                score *= 0.85
            # Sinal cross-class quase idêntico (≥ 0.90) que já passou pelo
            # filtro de afinidade: garante sobrevivência ao threshold — o
            # nível de severidade comunica a prioridade, não o descarte.
            if s_sig_cross >= 0.90:
                score = max(score, THRESHOLD_SCORE_FINAL)

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

        # Homônimos: ambas as marcas são o nome do próprio titular
        # (art. 124, XV LPI) e as classes não colidem → leve lenidade.
        # Fator conservador; calibrar com o gold set.
        if (par.get("is_nome_proprio_base") and par.get("is_nome_proprio_rpi")
                and not par.get("classes_colidem_flag")):
            score *= 0.90

        # Override: núcleo idêntico → mínimo 0.70
        if s_nucleo >= 0.99:
            score = max(score, 0.70)

        # Threshold mais baixo para classes de saúde
        threshold = THRESHOLD_SCORE_FINAL
        if ncl_a in CLASSES_CAUTELA_ALTA or ncl_b in CLASSES_CAUTELA_ALTA:
            threshold = threshold * FATOR_CAUTELA

        # Vigilância marcária: núcleo idêntico/quase não pode ser descartado
        # pelo threshold de score — recebe piso para sobreviver. O nível de
        # severidade (atribuído abaixo) é quem comunica a prioridade real.
        if nucleo_forte or desgastado_comum:
            score = max(score, threshold)

        if score >= threshold:
            updated = dict(par)
            updated["score_final"] = round(score, 4)
            updated["score_ri"] = round(score_ri, 4)
            updated["af_classes"] = round(af_classes, 4)
            updated["classificacao"] = _classificar(score)
            updated["nivel"] = _nivel_severidade(
                md, s_nome, s_fon, mesma_classe, af_classes, s_spec
            )
            updated["camada_deteccao"] = par.get("camada_deteccao", 4)
            aprovados.append(updated)

    return aprovados
