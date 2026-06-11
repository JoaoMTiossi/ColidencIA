"""
Camada 1 — Nome idêntico.
Hash lookup: se nomes normalizados são iguais → colidência automática.
"""
from __future__ import annotations

from ..config import classes_colidem
from ..utils.normalizacao import normalizar_para_hash


def camada1(carteira: list[dict], rpi: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Verifica nomes idênticos (score = 1.0) e núcleos idênticos (score = 0.85).

    Para nome idêntico: gera alerta independente de classe (o advogado avalia
    o princípio da especialidade e o alto renome). A classificação reflete as
    classes: ALTA se colidem, MEDIA se não colidem.

    Para núcleo idêntico: verifica classes antes de gerar alerta — evita falsos
    positivos entre marcas genéricas com mesmo elemento descritivo.

    O índice de núcleo usa `nucleo_distintivo` (quando disponível) para que
    "IBM BRASIL" e "IBM SOLUCOES" casem pelo núcleo "IBM", não pelo núcleo
    composto que diverge.

    Retorna:
        (alertas_automaticos, rpi_restante_para_camada2)
    """
    # Índice da carteira por hash do nome — (índice_carteira, marca)
    carteira_por_hash: dict[str, list[tuple[int, dict]]] = {}
    for idx_c, marca in enumerate(carteira):
        chave = normalizar_para_hash(marca["nome_normalizado"])
        carteira_por_hash.setdefault(chave, []).append((idx_c, marca))

    # Índice da carteira por hash do núcleo distintivo (ou núcleo quando
    # nucleo_distintivo está vazio — marca sem elemento descritivo aparável).
    carteira_por_nucleo: dict[str, list[tuple[int, dict]]] = {}
    for idx_c, marca in enumerate(carteira):
        chave_nucleo = normalizar_para_hash(
            marca.get("nucleo_distintivo") or marca["nucleo"]
        )
        if chave_nucleo:
            carteira_por_nucleo.setdefault(chave_nucleo, []).append((idx_c, marca))

    alertas: list[dict] = []
    rpi_processados: set[int] = set()
    # Rastreia pares (idx_rpi, idx_carteira) capturados por nome_identico para
    # evitar alerta nucleo_identico duplicado para o MESMO par, sem suprimir
    # alertas com outras marcas da carteira que casam apenas pelo núcleo.
    pares_nome_identico: set[tuple[int, int]] = set()

    for idx_rpi, marca_rpi in enumerate(rpi):
        hash_rpi = normalizar_para_hash(marca_rpi["nome_normalizado"])
        nucleo_hash_rpi = normalizar_para_hash(
            marca_rpi.get("nucleo_distintivo") or marca_rpi["nucleo"]
        )

        # Match por nome completo idêntico
        for idx_c, marca_base in carteira_por_hash.get(hash_rpi, []):
            colidem = classes_colidem(marca_base["ncl"], marca_rpi["ncl"])
            alertas.append(_criar_alerta(
                marca_base=marca_base,
                marca_rpi=marca_rpi,
                score_nome=1.0,
                score_nucleo=1.0,
                camada=1,
                motivo="nome_identico",
                colidem=colidem,
                mesma_classe=(marca_base["ncl"] == marca_rpi["ncl"]),
            ))
            rpi_processados.add(idx_rpi)
            pares_nome_identico.add((idx_rpi, idx_c))

        # Match por núcleo distintivo idêntico — corre mesmo quando nome_identico
        # já detectou este RPI, pois pode haver outras marcas na carteira que casam
        # pelo núcleo mas não pelo nome completo. Apenas o par exato já coberto por
        # nome_identico é pulado.
        if nucleo_hash_rpi and not marca_rpi.get("is_marca_generica"):
            for idx_c, marca_base in carteira_por_nucleo.get(nucleo_hash_rpi, []):
                if (idx_rpi, idx_c) in pares_nome_identico:
                    continue  # par já capturado por nome_identico — mais forte
                if marca_base.get("is_marca_generica"):
                    continue
                colidem = classes_colidem(marca_base["ncl"], marca_rpi["ncl"])
                alertas.append(_criar_alerta(
                    marca_base=marca_base,
                    marca_rpi=marca_rpi,
                    score_nome=0.85,
                    score_nucleo=1.0,
                    camada=1,
                    motivo="nucleo_identico",
                    colidem=colidem,
                    mesma_classe=(marca_base["ncl"] == marca_rpi["ncl"]),
                ))
                rpi_processados.add(idx_rpi)

    rpi_restante = [m for i, m in enumerate(rpi) if i not in rpi_processados]
    return alertas, rpi_restante


def reclassificar_pos_c3(alerta: dict) -> dict:
    """
    Re-deriva classificacao/nivel/score_final de um alerta C1 após a camada 3
    refinar score_spec.

    A C1 classifica com o flag binário classes_colidem (matriz COLLISIONS).
    A C3 sobrescreve score_spec com a afinidade real (correlatas/semântica),
    que pode contradizer o flag em ambas as direções:
      - classes colidem formalmente, mas a modulação semântica encontra
        especificações de domínios distintos → rebaixa para MEDIA;
      - classes não colidem na matriz, mas há afinidade real forte
        (transversal, CSV ou semântica >= 0.80) → eleva para ALTA.
    Sem esta etapa o alerta sairia com score_final=1.0/ALTA e score_spec=0.45
    no mesmo registro — inconsistente para quem consome o relatório.
    """
    motivo = alerta.get("motivo", "")
    if motivo not in ("nome_identico", "nucleo_identico"):
        return alerta
    spec = alerta.get("score_spec", 0.0)
    if alerta.get("classes_colidem_flag"):
        colidem = spec >= 0.60
    else:
        colidem = spec >= 0.80
    alerta["classificacao"] = "ALTA" if colidem else "MEDIA"
    alerta["nivel"] = _nivel_alerta(motivo, colidem)
    alerta["score_final"] = round(_score_final_c1(motivo, colidem), 4)
    return alerta


def _nivel_alerta(motivo: str, colidem: bool) -> str:
    """
    Nível de urgência para alertas automáticos da camada 1.

    Alinha com _nivel_severidade (scoring.py), sem importá-la:
    - colidem=True (mesma classe ou classes correlatas) → ALTA
    - nome_identico cross-class não correlato → MEDIA (advogado avalia art. 125)
    - nucleo_identico cross-class não correlato → VIGIAR (diluição potencial)
    """
    if colidem:
        return "ALTA"
    return "MEDIA" if motivo == "nome_identico" else "VIGIAR"


def _score_final_c1(motivo: str, colidem: bool) -> float:
    """
    Score final para alertas de camada 1 (bypassam camada 4).

    Espelha os overrides de scoring.py:
      nome_identico + colidem  → 1.0  (máximo — ALTA)
      nome_identico + não col. → 0.75 (faixa MEDIA)
      nucleo_identico + colidem → 0.85 (override mínimo de score_nucleo=1.0)
      nucleo_identico + não col. → 0.70 (faixa MEDIA)
    """
    if motivo == "nome_identico":
        return 1.0 if colidem else 0.75
    return 0.85 if colidem else 0.70


def _criar_alerta(
    marca_base: dict,
    marca_rpi: dict,
    score_nome: float,
    score_nucleo: float,
    camada: int,
    motivo: str,
    colidem: bool = True,
    mesma_classe: bool = False,
) -> dict:
    sf = _score_final_c1(motivo, colidem)
    return {
        "processo_base": marca_base.get("processo", ""),
        "marca_base": marca_base.get("marca") or marca_base.get("nome_marca", ""),
        "ncl_base": marca_base.get("ncl", 0),
        "ncl_versao_base": marca_base.get("ncl_versao", 12),
        "spec_base": marca_base.get("especificacao", ""),
        "nucleo_base": marca_base.get("nucleo", ""),
        "titular_base": marca_base.get("titular", ""),
        "marca_rpi": marca_rpi.get("nome_marca", ""),
        "ncl_rpi": marca_rpi.get("ncl", 0),
        "spec_rpi": marca_rpi.get("especificacao", ""),
        "nucleo_rpi": marca_rpi.get("nucleo", ""),
        "processo_rpi": marca_rpi.get("processo", ""),
        "titular_rpi": marca_rpi.get("titular", ""),
        "despacho_codigo": marca_rpi.get("despacho_codigo", ""),
        "despacho_nome": marca_rpi.get("despacho_nome", ""),
        "tipo_acao": marca_rpi.get("tipo_acao", ""),
        "motivo": motivo,
        "score_nome": round(score_nome, 4),
        "score_fonetico": 1.0 if motivo == "nome_identico" else 0.9,
        "score_spec": 1.0 if colidem else 0.5,
        "score_nucleo": round(score_nucleo, 4),
        "score_ia": None,
        # score_final e campos derivados computados aqui porque C1 bypassa C4.
        "score_final": round(sf, 4),
        "score_ri": 0.0,
        "af_classes": 1.0 if colidem else 0.0,
        "camada_deteccao": camada,
        "nivel": _nivel_alerta(motivo, colidem),
        # Nome idêntico + classes colidem → ALTA (art. 124, XIX LPI).
        # Nome idêntico + classes não colidem → MEDIA: o advogado avalia
        # se há alto renome (art. 125) ou afinidade indireta.
        "classificacao": "ALTA" if colidem else "MEDIA",
        "classes_colidem_flag": colidem,
        "is_sigla": bool(marca_base.get("is_sigla") or marca_rpi.get("is_sigla")),
        "is_desgastado": bool(marca_base.get("is_desgastado") or marca_rpi.get("is_desgastado")),
        "is_marca_generica": bool(marca_base.get("is_marca_generica") or marca_rpi.get("is_marca_generica")),
        "nucleo_base_generico": bool(marca_base.get("is_marca_generica")),
        "nucleo_rpi_generico": bool(marca_rpi.get("is_marca_generica")),
        "nucleo_distintivo_base": marca_base.get("nucleo_distintivo", ""),
        "nucleo_distintivo_rpi": marca_rpi.get("nucleo_distintivo", ""),
        "apresentacao_base": marca_base.get("apresentacao", ""),
        "apresentacao_rpi": marca_rpi.get("apresentacao", ""),
        "is_nome_proprio_base": bool(marca_base.get("is_nome_proprio")),
        "is_nome_proprio_rpi": bool(marca_rpi.get("is_nome_proprio")),
    }
