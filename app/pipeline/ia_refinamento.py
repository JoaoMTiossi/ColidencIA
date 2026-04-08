"""
Camada 5 — Refinamento IA (GPT-4o-mini).
Envia batches de pares para a API OpenAI e atualiza classificação/justificativa.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from ..config import (
    BATCH_SIZE_IA,
    BUDGET_SEMANAL_USD,
    MAX_PARES_IA,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Você é um examinador especialista em colidência de marcas do INPI brasileiro.
Analise o par de marcas e determine se há risco de colidência conforme o art. 124, XIX da LPI 9.279/96.

CRITÉRIOS (nesta ordem):
1. REPRODUÇÃO/IMITAÇÃO: aspecto gráfico (letras, estrutura), fonético (sílabas, sons), ideológico (conceito, tradução)
2. ELEMENTO PRINCIPAL: foco no núcleo marcário, não nos complementos descritivos
3. AFINIDADE MERCADOLÓGICA: natureza, finalidade, complementariedade, canais, público, origem
4. REGRA INVERSA: menor semelhança entre sinais → maior afinidade necessária
5. EXCEÇÕES: elementos desgastados (analisar conjunto), siglas (só gráfico), marcas genéricas

CLASSIFICAÇÃO:
- ALTA: reprodução/imitação clara + afinidade evidente
- MÉDIA: similaridade parcial + alguma afinidade
- BAIXA: similaridade marginal OU afinidade muito fraca
- NENHUMA: sem risco de confusão

Responda APENAS com JSON válido, sem markdown:
{"classificacao":"ALTA|MEDIA|BAIXA|NENHUMA","score":0.0-1.0,"justificativa":"max 80 palavras","aspecto_grafico":0.0-1.0,"aspecto_fonetico":0.0-1.0,"aspecto_ideologico":0.0-1.0,"afinidade_mercadologica":0.0-1.0}"""


def _montar_prompt_par(par: dict) -> str:
    return (
        f"Marca BASE: \"{par['marca_base']}\" (NCL {par['ncl_base']}) "
        f"Núcleo: \"{par['nucleo_base']}\"\n"
        f"Especificação BASE: {par.get('spec_base', '')[:200]}\n\n"
        f"Marca RPI: \"{par['marca_rpi']}\" (NCL {par['ncl_rpi']}) "
        f"Núcleo: \"{par['nucleo_rpi']}\"\n"
        f"Especificação RPI: {par.get('spec_rpi', '')[:200]}\n\n"
        f"Scores pré-calculados — nome: {par.get('score_nome', 0):.2f}, "
        f"fonético: {par.get('score_fonetico', 0):.2f}, "
        f"spec: {par.get('score_spec', 0):.2f}, "
        f"núcleo: {par.get('score_nucleo', 0):.2f}"
    )


async def _processar_batch(
    client,
    batch: list[tuple[int, dict]],
    resultados: list[dict],
    custo_acumulado: list[float],
    progress_cb: Callable[[str], None] | None,
) -> None:
    """Processa um batch de pares em paralelo."""
    tasks = []
    for idx, par in batch:
        prompt = _montar_prompt_par(par)
        tasks.append(_chamar_api(client, prompt, idx, par))

    respostas = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in respostas:
        if isinstance(resp, Exception):
            logger.warning("Erro na API IA: %s", resp)
            continue
        idx, parsed, tokens_used = resp
        if parsed:
            resultados[idx] = _aplicar_resposta_ia(resultados[idx], parsed)
            # Estimativa de custo: ~$0.15/1M input tokens, $0.60/1M output tokens
            custo = (tokens_used.get("prompt", 0) * 0.15 + tokens_used.get("completion", 0) * 0.60) / 1_000_000
            custo_acumulado[0] += custo


async def _chamar_api(client, prompt: str, idx: int, par: dict) -> tuple[int, dict | None, dict]:
    """Chama a API OpenAI e retorna (idx, parsed_json, tokens)."""
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        tokens = {
            "prompt": response.usage.prompt_tokens if response.usage else 0,
            "completion": response.usage.completion_tokens if response.usage else 0,
        }
        return idx, parsed, tokens
    except Exception as e:
        logger.warning("Erro na chamada IA para par %d: %s", idx, e)
        return idx, None, {}


def _aplicar_resposta_ia(par: dict, ia_resp: dict) -> dict:
    """Aplica a resposta da IA ao par, atualizando classificação se válida."""
    updated = dict(par)

    classificacao = ia_resp.get("classificacao", "").upper()
    if classificacao in ("ALTA", "MEDIA", "BAIXA", "NENHUMA"):
        updated["classificacao"] = classificacao

    score_ia = ia_resp.get("score")
    if isinstance(score_ia, (int, float)) and 0.0 <= score_ia <= 1.0:
        # Ponderar score IA com score da camada 4
        score_c4 = updated.get("score_final", 0.0)
        updated["score_final"] = round(0.6 * float(score_ia) + 0.4 * score_c4, 4)
        updated["score_ia"] = round(float(score_ia), 4)

    updated["justificativa_ia"] = ia_resp.get("justificativa", "")
    updated["aspecto_grafico"] = ia_resp.get("aspecto_grafico")
    updated["aspecto_fonetico"] = ia_resp.get("aspecto_fonetico")
    updated["aspecto_ideologico"] = ia_resp.get("aspecto_ideologico")
    updated["afinidade_mercadologica"] = ia_resp.get("afinidade_mercadologica")
    updated["camada_deteccao"] = 5

    return updated


async def camada5_async(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[dict], float]:
    """
    Camada 5 assíncrona: refina com IA em batches de BATCH_SIZE_IA pares,
    5 requests paralelos.

    Retorna (resultados_refinados, custo_total_usd).
    """
    if not OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY não configurada — pulando camada IA")
        return pares_scored, 0.0

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai não instalado — pulando camada IA")
        return pares_scored, 0.0

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    resultados = list(pares_scored)
    custo_acumulado = [0.0]

    # Limitar quantidade de pares enviados para IA
    pares_para_ia = min(len(pares_scored), MAX_PARES_IA)

    processados = 0
    for inicio in range(0, pares_para_ia, BATCH_SIZE_IA):
        # Verificar budget
        if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
            logger.warning("Budget semanal IA atingido (%.2f USD) — usando scores Camada 4 para restantes",
                           custo_acumulado[0])
            break

        fim = min(inicio + BATCH_SIZE_IA, pares_para_ia)
        batch = [(i, pares_scored[i]) for i in range(inicio, fim)]

        # Processar 5 batches por vez em paralelo
        chunk_size = 5
        for chunk_inicio in range(0, len(batch), chunk_size):
            chunk = batch[chunk_inicio:chunk_inicio + chunk_size]
            await _processar_batch(client, chunk, resultados, custo_acumulado, progress_cb)

        processados = fim
        if progress_cb:
            progress_cb(f"IA: {processados}/{pares_para_ia} pares processados")

    return resultados, custo_acumulado[0]


def camada5(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[dict], float]:
    """Wrapper síncrono para camada5_async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, camada5_async(pares_scored, progress_cb))
                return future.result()
        else:
            return loop.run_until_complete(camada5_async(pares_scored, progress_cb))
    except Exception as e:
        logger.error("Erro na camada IA: %s — usando fallback Camada 4", e)
        return pares_scored, 0.0
