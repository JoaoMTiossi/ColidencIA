"""
Camada 5 — Refinamento IA (Claude / GPT-4o-mini fallback).
Envia batches de pares para a API e atualiza classificação/justificativa.

Provider preferido: Anthropic Claude (claude-haiku-4-5).
Fallback: OpenAI GPT-4o-mini (se ANTHROPIC_API_KEY não configurado).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from ..config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
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
    from ..utils.distintividade import match_distintivo, tokens_distintivos

    ncl_base = par.get("ncl_base")
    ncl_rpi = par.get("ncl_rpi")
    dist_base = tokens_distintivos(par.get("marca_base", ""), ncl_base) or ["(nenhum — marca descritiva)"]
    dist_rpi = tokens_distintivos(par.get("marca_rpi", ""), ncl_rpi) or ["(nenhum — marca descritiva)"]
    md = match_distintivo(par.get("marca_base", ""), par.get("marca_rpi", ""), ncl_base, ncl_rpi)
    md_txt = f"{md:.2f}" if md is not None else "N/A (marca sem elemento distintivo próprio)"

    return (
        f"Marca BASE: \"{par['marca_base']}\" (NCL {par['ncl_base']}) "
        f"Núcleo: \"{par['nucleo_base']}\"\n"
        f"Elementos DISTINTIVOS BASE (sem termos descritivos): {dist_base}\n"
        f"Especificação BASE: {par.get('spec_base', '')[:200]}\n\n"
        f"Marca RPI: \"{par['marca_rpi']}\" (NCL {par['ncl_rpi']}) "
        f"Núcleo: \"{par['nucleo_rpi']}\"\n"
        f"Elementos DISTINTIVOS RPI (sem termos descritivos): {dist_rpi}\n"
        f"Especificação RPI: {par.get('spec_rpi', '')[:200]}\n\n"
        f"ATENÇÃO: os scores de nome/fonética abaixo são do nome COMPLETO e podem "
        f"estar inflados por palavras descritivas compartilhadas (ex: 'BARBEARIA', "
        f"'VEÍCULOS', 'ODONTOLOGIA'). Baseie o julgamento na semelhança dos "
        f"ELEMENTOS DISTINTIVOS acima.\n"
        f"Similaridade dos elementos distintivos: {md_txt}\n"
        f"Scores do nome completo — nome: {par.get('score_nome', 0):.2f}, "
        f"fonético: {par.get('score_fonetico', 0):.2f}, "
        f"spec: {par.get('score_spec', 0):.2f}, "
        f"núcleo: {par.get('score_nucleo', 0):.2f}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Anthropic (Claude)
# ──────────────────────────────────────────────────────────────────────────────

async def _chamar_claude(client, prompt: str, idx: int) -> tuple[int, dict | None, dict]:
    """Chama a API Anthropic e retorna (idx, parsed_json, tokens)."""
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text if response.content else "{}"
        # Remove markdown code fences se presentes
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content.strip())
        tokens = {
            "prompt": response.usage.input_tokens if response.usage else 0,
            "completion": response.usage.output_tokens if response.usage else 0,
        }
        return idx, parsed, tokens
    except Exception as e:
        logger.warning("Erro na chamada Claude para par %d: %s", idx, e)
        return idx, None, {}


async def _processar_batch_claude(
    client,
    batch: list[tuple[int, dict]],
    resultados: list[dict],
    custo_acumulado: list[float],
) -> None:
    tasks = [_chamar_claude(client, _montar_prompt_par(par), idx) for idx, par in batch]
    respostas = await asyncio.gather(*tasks, return_exceptions=True)
    for resp in respostas:
        if isinstance(resp, Exception):
            logger.warning("Erro na API Claude: %s", resp)
            continue
        idx, parsed, tokens = resp
        if parsed:
            resultados[idx] = _aplicar_resposta_ia(resultados[idx], parsed)
            # claude-haiku-4-5: $0.80/1M input, $4.00/1M output (valores aproximados)
            custo = (tokens.get("prompt", 0) * 0.80 + tokens.get("completion", 0) * 4.00) / 1_000_000
            custo_acumulado[0] += custo


async def camada5_claude_async(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[dict], float]:
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic não instalado — pulando camada IA")
        return pares_scored, 0.0

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    resultados = list(pares_scored)
    custo_acumulado = [0.0]
    pares_para_ia = min(len(pares_scored), MAX_PARES_IA)

    for inicio in range(0, pares_para_ia, BATCH_SIZE_IA):
        if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
            logger.warning("Budget semanal IA atingido (%.2f USD)", custo_acumulado[0])
            break

        fim = min(inicio + BATCH_SIZE_IA, pares_para_ia)
        batch = [(i, pares_scored[i]) for i in range(inicio, fim)]

        # Processar em chunks de 5 paralelos para não sobrecarregar rate limit
        for chunk_start in range(0, len(batch), 5):
            chunk = batch[chunk_start:chunk_start + 5]
            await _processar_batch_claude(client, chunk, resultados, custo_acumulado)

        if progress_cb:
            progress_cb(f"Claude: {fim}/{pares_para_ia} pares — custo acumulado: ${custo_acumulado[0]:.4f}")

    return resultados, custo_acumulado[0]


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI (fallback)
# ──────────────────────────────────────────────────────────────────────────────

async def _chamar_openai(client, prompt: str, idx: int, par: dict) -> tuple[int, dict | None, dict]:
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
        logger.warning("Erro na chamada OpenAI para par %d: %s", idx, e)
        return idx, None, {}


async def _processar_batch_openai(
    client,
    batch: list[tuple[int, dict]],
    resultados: list[dict],
    custo_acumulado: list[float],
) -> None:
    tasks = [_chamar_openai(client, _montar_prompt_par(par), idx, par) for idx, par in batch]
    respostas = await asyncio.gather(*tasks, return_exceptions=True)
    for resp in respostas:
        if isinstance(resp, Exception):
            logger.warning("Erro na API OpenAI: %s", resp)
            continue
        idx, parsed, tokens = resp
        if parsed:
            resultados[idx] = _aplicar_resposta_ia(resultados[idx], parsed)
            custo = (tokens.get("prompt", 0) * 0.15 + tokens.get("completion", 0) * 0.60) / 1_000_000
            custo_acumulado[0] += custo


async def camada5_openai_async(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[dict], float]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai não instalado")
        return pares_scored, 0.0

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    resultados = list(pares_scored)
    custo_acumulado = [0.0]
    pares_para_ia = min(len(pares_scored), MAX_PARES_IA)

    for inicio in range(0, pares_para_ia, BATCH_SIZE_IA):
        if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
            logger.warning("Budget semanal IA atingido (%.2f USD)", custo_acumulado[0])
            break

        fim = min(inicio + BATCH_SIZE_IA, pares_para_ia)
        batch = [(i, pares_scored[i]) for i in range(inicio, fim)]

        for chunk_start in range(0, len(batch), 5):
            chunk = batch[chunk_start:chunk_start + 5]
            await _processar_batch_openai(client, chunk, resultados, custo_acumulado)

        if progress_cb:
            progress_cb(f"OpenAI: {fim}/{pares_para_ia} pares — custo: ${custo_acumulado[0]:.4f}")

    return resultados, custo_acumulado[0]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers comuns
# ──────────────────────────────────────────────────────────────────────────────

def _aplicar_resposta_ia(par: dict, ia_resp: dict) -> dict:
    updated = dict(par)

    classificacao = ia_resp.get("classificacao", "").upper()
    if classificacao in ("ALTA", "MEDIA", "BAIXA", "NENHUMA"):
        updated["classificacao"] = classificacao

    score_ia = ia_resp.get("score")
    if isinstance(score_ia, (int, float)) and 0.0 <= score_ia <= 1.0:
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


# ──────────────────────────────────────────────────────────────────────────────
# Ponto de entrada público
# ──────────────────────────────────────────────────────────────────────────────

async def camada5_async(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[dict], float]:
    """Usa Claude se ANTHROPIC_API_KEY configurado, senão tenta OpenAI."""
    if ANTHROPIC_API_KEY:
        return await camada5_claude_async(pares_scored, progress_cb)
    if OPENAI_API_KEY:
        logger.info("ANTHROPIC_API_KEY não configurado — usando OpenAI fallback")
        return await camada5_openai_async(pares_scored, progress_cb)
    logger.info("Nenhuma API key configurada — pulando camada IA")
    return pares_scored, 0.0


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
