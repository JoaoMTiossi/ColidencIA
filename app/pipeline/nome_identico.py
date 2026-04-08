"""
Camada 1 — Nome idêntico.
Hash lookup: se nomes normalizados são iguais → colidência automática.
"""
from __future__ import annotations

from ..config import classes_colidem
from ..utils.normalizacao import normalizar_para_hash


def camada1(carteira: list[dict], rpi: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Verifica nomes idênticos (score = 1.0, classificação automática = ALTA).

    Regra: nome_normalizado igual → colidência independente de classe.
    Também verifica núcleo idêntico → candidato com bonus.

    Retorna:
        (alertas_automaticos, rpi_restante_para_camada2)
    """
    # Índice da carteira por hash do nome
    carteira_por_hash: dict[str, list[dict]] = {}
    for marca in carteira:
        chave = normalizar_para_hash(marca["nome_normalizado"])
        carteira_por_hash.setdefault(chave, []).append(marca)

    # Índice da carteira por hash do núcleo
    carteira_por_nucleo: dict[str, list[dict]] = {}
    for marca in carteira:
        chave_nucleo = normalizar_para_hash(marca["nucleo"])
        if chave_nucleo:
            carteira_por_nucleo.setdefault(chave_nucleo, []).append(marca)

    alertas: list[dict] = []
    rpi_processados: set[int] = set()

    for idx_rpi, marca_rpi in enumerate(rpi):
        hash_rpi = normalizar_para_hash(marca_rpi["nome_normalizado"])
        nucleo_hash_rpi = normalizar_para_hash(marca_rpi["nucleo"])

        # Match por nome completo idêntico
        matches = carteira_por_hash.get(hash_rpi, [])
        for marca_base in matches:
            alertas.append(_criar_alerta(
                marca_base=marca_base,
                marca_rpi=marca_rpi,
                score_nome=1.0,
                score_nucleo=1.0,
                camada=1,
                motivo="nome_identico",
            ))
            rpi_processados.add(idx_rpi)

        # Match por núcleo idêntico (apenas se não já detectado por nome)
        if idx_rpi not in rpi_processados and nucleo_hash_rpi:
            matches_nucleo = carteira_por_nucleo.get(nucleo_hash_rpi, [])
            for marca_base in matches_nucleo:
                # Verificar classes para núcleo idêntico
                colidem = classes_colidem(marca_base["ncl"], marca_rpi["ncl"])
                alertas.append(_criar_alerta(
                    marca_base=marca_base,
                    marca_rpi=marca_rpi,
                    score_nome=0.85,
                    score_nucleo=1.0,
                    camada=1,
                    motivo="nucleo_identico",
                    classes_colidem=colidem,
                ))
                rpi_processados.add(idx_rpi)

    rpi_restante = [m for i, m in enumerate(rpi) if i not in rpi_processados]
    return alertas, rpi_restante


def _criar_alerta(
    marca_base: dict,
    marca_rpi: dict,
    score_nome: float,
    score_nucleo: float,
    camada: int,
    motivo: str,
    classes_colidem: bool = True,
) -> dict:
    return {
        "marca_base": marca_base.get("marca") or marca_base.get("nome_marca", ""),
        "ncl_base": marca_base.get("ncl", 0),
        "spec_base": marca_base.get("especificacao", ""),
        "nucleo_base": marca_base.get("nucleo", ""),
        "marca_rpi": marca_rpi.get("nome_marca", ""),
        "ncl_rpi": marca_rpi.get("ncl", 0),
        "spec_rpi": marca_rpi.get("especificacao", ""),
        "nucleo_rpi": marca_rpi.get("nucleo", ""),
        "processo_rpi": marca_rpi.get("processo", ""),
        "titular_rpi": marca_rpi.get("titular", ""),
        "despacho_codigo": marca_rpi.get("despacho_codigo", ""),
        "despacho_nome": marca_rpi.get("despacho_nome", ""),
        "tipo_acao": marca_rpi.get("tipo_acao", ""),
        "score_nome": round(score_nome, 4),
        "score_fonetico": 1.0 if motivo == "nome_identico" else 0.9,
        "score_spec": 1.0 if classes_colidem else 0.5,
        "score_nucleo": round(score_nucleo, 4),
        "score_ia": None,
        "camada_deteccao": camada,
        "classificacao": "ALTA",
        "classes_colidem_flag": classes_colidem,
        "is_sigla": marca_rpi.get("is_sigla", False),
        "is_desgastado": marca_rpi.get("is_desgastado", False),
    }
