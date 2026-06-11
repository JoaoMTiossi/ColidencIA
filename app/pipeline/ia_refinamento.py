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
    BUDGET_SEMANAL_USD,
    MAX_PARES_IA,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PARES_POR_CHAMADA_IA,
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

_SYSTEM_PROMPT_LOTE = """Você é um examinador especialista em colidência de marcas do INPI brasileiro.
Você receberá VÁRIOS pares de marcas numerados (=== PAR 1 ===, === PAR 2 ===, ...).
Para CADA par, determine se há risco de colidência conforme o art. 124, XIX da LPI 9.279/96.

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

Responda APENAS com JSON válido, sem markdown — um item por par, na MESMA ordem,
com o campo "par" obrigatório correspondendo ao número do par:
{"resultados":[{"par":1,"classificacao":"ALTA|MEDIA|BAIXA|NENHUMA","score":0.0-1.0,"justificativa":"max 80 palavras","aspecto_grafico":0.0-1.0,"aspecto_fonetico":0.0-1.0,"aspecto_ideologico":0.0-1.0,"afinidade_mercadologica":0.0-1.0},{"par":2,...}]}"""


def _montar_prompt_par(par: dict) -> str:
    from ..utils.distintividade import match_distintivo, tokens_distintivos

    ncl_base = par.get("ncl_base")
    ncl_rpi = par.get("ncl_rpi")
    dist_base = tokens_distintivos(par.get("marca_base", ""), ncl_base) or ["(nenhum — marca descritiva)"]
    dist_rpi = tokens_distintivos(par.get("marca_rpi", ""), ncl_rpi) or ["(nenhum — marca descritiva)"]
    md = match_distintivo(par.get("marca_base", ""), par.get("marca_rpi", ""), ncl_base, ncl_rpi)
    md_txt = f"{md:.2f}" if md is not None else "N/A (marca sem elemento distintivo próprio)"

    prompt = (
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

    np_base = par.get("is_nome_proprio_base")
    np_rpi = par.get("is_nome_proprio_rpi")
    if np_base or np_rpi:
        qual = "ambas as marcas são" if np_base and np_rpi else (
            "a marca BASE é" if np_base else "a marca RPI é"
        )
        prompt += (
            f"\nCONTEXTO: {qual} o nome do próprio titular (art. 124, XV LPI) — "
            f"colisões entre homônimos são avaliadas com mais lenidade."
        )

    return prompt


def _montar_prompt_lote(pares: list[dict]) -> str:
    """Concatena os prompts individuais numerados para uma única chamada IA."""
    return "\n\n".join(
        f"=== PAR {i + 1} ===\n{_montar_prompt_par(p)}" for i, p in enumerate(pares)
    )


def _parsear_resposta_lote(content: str, n_pares: int) -> dict[int, dict]:
    """
    Parseia a resposta em lote da IA. Aceita {"resultados":[...]} ou lista pura.
    Retorna {numero_do_par (1-based): item} apenas para itens com campo "par"
    válido dentro de 1..n_pares. Qualquer falha de parse → {} (caller faz
    fallback por par).
    """
    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content.strip())
        itens = data.get("resultados") if isinstance(data, dict) else data
        if not isinstance(itens, list):
            return {}
        mapa: dict[int, dict] = {}
        for item in itens:
            if not isinstance(item, dict):
                continue
            par_n = item.get("par")
            if isinstance(par_n, int) and 1 <= par_n <= n_pares:
                mapa[par_n] = item
        return mapa
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────────────────
# Anthropic (Claude)
# ──────────────────────────────────────────────────────────────────────────────

async def _chamar_claude(client, prompt: str, idx: int) -> tuple[int, dict | None, dict]:
    """Chama a API Anthropic e retorna (idx, parsed_json, tokens)."""
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            temperature=0.1,
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


async def _chamar_claude_lote(
    client, grupo: list[tuple[int, dict]]
) -> tuple[dict[int, dict], dict]:
    """
    Uma chamada à API para um grupo de pares. Retorna ({idx_global: parsed}, tokens).
    Exceções propagam — o caller manda o grupo inteiro para fallback por par.
    """
    pares = [par for _, par in grupo]
    response = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=200 + 120 * len(grupo),
        temperature=0.1,
        system=_SYSTEM_PROMPT_LOTE,
        messages=[{"role": "user", "content": _montar_prompt_lote(pares)}],
    )
    content = response.content[0].text if response.content else "{}"
    mapa_local = _parsear_resposta_lote(content, len(grupo))
    tokens = {
        "prompt": response.usage.input_tokens if response.usage else 0,
        "completion": response.usage.output_tokens if response.usage else 0,
    }
    return {grupo[n - 1][0]: item for n, item in mapa_local.items()}, tokens


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
            custo_acumulado[0] += _custo_claude(tokens)


def _custo_claude(tokens: dict) -> float:
    # claude-haiku-4-5: $0.80/1M input, $4.00/1M output (valores aproximados)
    return (tokens.get("prompt", 0) * 0.80 + tokens.get("completion", 0) * 4.00) / 1_000_000


async def camada5_claude_async(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
    custo_inicial: float = 0.0,
) -> tuple[list[dict], float]:
    """
    Refina pares com Claude em chamadas agrupadas (PARES_POR_CHAMADA_IA pares
    por chamada). Pares ausentes/imparseáveis na resposta do lote recebem
    fallback por par. Retorna (resultados, custo DESTA invocação) — o budget
    é checado contra custo_inicial + custo desta invocação, permitindo limite
    global quando o executor processa a RPI em vários lotes.
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic não instalado — pulando camada IA")
        return pares_scored, 0.0

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    resultados = list(pares_scored)
    custo_acumulado = [custo_inicial]
    pares_para_ia = min(len(pares_scored), MAX_PARES_IA)

    grupos = [
        [(i, pares_scored[i]) for i in range(inicio, min(inicio + PARES_POR_CHAMADA_IA, pares_para_ia))]
        for inicio in range(0, pares_para_ia, PARES_POR_CHAMADA_IA)
    ]

    # 3 grupos em paralelo (≤ 3 × PARES_POR_CHAMADA_IA pares em voo)
    for chunk_start in range(0, len(grupos), 3):
        if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
            logger.warning("Budget IA atingido (%.2f USD)", custo_acumulado[0])
            break

        chunk = grupos[chunk_start:chunk_start + 3]
        respostas = await asyncio.gather(
            *[_chamar_claude_lote(client, g) for g in chunk], return_exceptions=True
        )

        pendentes: list[tuple[int, dict]] = []
        for grupo, resp in zip(chunk, respostas):
            if isinstance(resp, Exception):
                logger.warning("Erro na chamada Claude em lote: %s — fallback por par", resp)
                pendentes.extend(grupo)
                continue
            mapa, tokens = resp
            custo_acumulado[0] += _custo_claude(tokens)
            for idx, par in grupo:
                if idx in mapa:
                    resultados[idx] = _aplicar_resposta_ia(resultados[idx], mapa[idx])
                else:
                    pendentes.append((idx, par))

        # Fallback por par para os que faltaram na resposta do lote
        for fb_start in range(0, len(pendentes), 5):
            if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
                break
            await _processar_batch_claude(
                client, pendentes[fb_start:fb_start + 5], resultados, custo_acumulado
            )

        if progress_cb:
            fim = min((chunk_start + 3) * PARES_POR_CHAMADA_IA, pares_para_ia)
            progress_cb(
                f"Claude: {fim}/{pares_para_ia} pares — custo acumulado: ${custo_acumulado[0]:.4f}"
            )

    return resultados, custo_acumulado[0] - custo_inicial


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


async def _chamar_openai_lote(
    client, grupo: list[tuple[int, dict]]
) -> tuple[dict[int, dict], dict]:
    """
    Uma chamada à API para um grupo de pares. Retorna ({idx_global: parsed}, tokens).
    response_format=json_object exige raiz objeto — daí o wrapper {"resultados":[...]}.
    Exceções propagam — o caller manda o grupo inteiro para fallback por par.
    """
    pares = [par for _, par in grupo]
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT_LOTE},
            {"role": "user", "content": _montar_prompt_lote(pares)},
        ],
        temperature=0.1,
        max_tokens=200 + 120 * len(grupo),
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    mapa_local = _parsear_resposta_lote(content, len(grupo))
    tokens = {
        "prompt": response.usage.prompt_tokens if response.usage else 0,
        "completion": response.usage.completion_tokens if response.usage else 0,
    }
    return {grupo[n - 1][0]: item for n, item in mapa_local.items()}, tokens


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
            custo_acumulado[0] += _custo_openai(tokens)


def _custo_openai(tokens: dict) -> float:
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    return (tokens.get("prompt", 0) * 0.15 + tokens.get("completion", 0) * 0.60) / 1_000_000


async def camada5_openai_async(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
    custo_inicial: float = 0.0,
) -> tuple[list[dict], float]:
    """Espelho de camada5_claude_async com o provider OpenAI (fallback)."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai não instalado")
        return pares_scored, 0.0

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    resultados = list(pares_scored)
    custo_acumulado = [custo_inicial]
    pares_para_ia = min(len(pares_scored), MAX_PARES_IA)

    grupos = [
        [(i, pares_scored[i]) for i in range(inicio, min(inicio + PARES_POR_CHAMADA_IA, pares_para_ia))]
        for inicio in range(0, pares_para_ia, PARES_POR_CHAMADA_IA)
    ]

    for chunk_start in range(0, len(grupos), 3):
        if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
            logger.warning("Budget IA atingido (%.2f USD)", custo_acumulado[0])
            break

        chunk = grupos[chunk_start:chunk_start + 3]
        respostas = await asyncio.gather(
            *[_chamar_openai_lote(client, g) for g in chunk], return_exceptions=True
        )

        pendentes: list[tuple[int, dict]] = []
        for grupo, resp in zip(chunk, respostas):
            if isinstance(resp, Exception):
                logger.warning("Erro na chamada OpenAI em lote: %s — fallback por par", resp)
                pendentes.extend(grupo)
                continue
            mapa, tokens = resp
            custo_acumulado[0] += _custo_openai(tokens)
            for idx, par in grupo:
                if idx in mapa:
                    resultados[idx] = _aplicar_resposta_ia(resultados[idx], mapa[idx])
                else:
                    pendentes.append((idx, par))

        for fb_start in range(0, len(pendentes), 5):
            if custo_acumulado[0] >= BUDGET_SEMANAL_USD:
                break
            await _processar_batch_openai(
                client, pendentes[fb_start:fb_start + 5], resultados, custo_acumulado
            )

        if progress_cb:
            fim = min((chunk_start + 3) * PARES_POR_CHAMADA_IA, pares_para_ia)
            progress_cb(f"OpenAI: {fim}/{pares_para_ia} pares — custo: ${custo_acumulado[0]:.4f}")

    return resultados, custo_acumulado[0] - custo_inicial


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
    custo_inicial: float = 0.0,
) -> tuple[list[dict], float]:
    """
    Usa Claude se ANTHROPIC_API_KEY configurado, senão tenta OpenAI.
    custo_inicial: gasto já acumulado na execução (lotes anteriores) — o budget
    é global por execução. O retorno é o custo apenas desta invocação.
    """
    if ANTHROPIC_API_KEY:
        return await camada5_claude_async(pares_scored, progress_cb, custo_inicial)
    if OPENAI_API_KEY:
        logger.info("ANTHROPIC_API_KEY não configurado — usando OpenAI fallback")
        return await camada5_openai_async(pares_scored, progress_cb, custo_inicial)
    logger.info("Nenhuma API key configurada — pulando camada IA")
    return pares_scored, 0.0


def camada5(
    pares_scored: list[dict],
    progress_cb: Callable[[str], None] | None = None,
    custo_inicial: float = 0.0,
) -> tuple[list[dict], float]:
    """Wrapper síncrono para camada5_async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run, camada5_async(pares_scored, progress_cb, custo_inicial)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                camada5_async(pares_scored, progress_cb, custo_inicial)
            )
    except Exception as e:
        logger.error("Erro na camada IA: %s — usando fallback Camada 4", e)
        return pares_scored, 0.0
