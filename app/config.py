"""
Configuração global do sistema de colidência.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Despachos relevantes
# ---------------------------------------------------------------------------
DESPACHOS_OPOSICAO: frozenset[str] = frozenset({"IPAS009", "IPAS756", "IPAS421", "IPAS135"})
DESPACHOS_PAN: frozenset[str] = frozenset({"IPAS158", "IPAS237"})
DESPACHOS_RELEVANTES: frozenset[str] = DESPACHOS_OPOSICAO | DESPACHOS_PAN

DESPACHOS_NOMES: dict[str, str] = {
    "IPAS009": "Publicação para oposição (exame formal concluído)",
    "IPAS756": "Publicação para oposição (designação Madri)",
    "IPAS421": "Republicação de pedido",
    "IPAS135": "Republicação (perda de prioridade)",
    "IPAS158": "Concessão de registro",
    "IPAS237": "Recurso provido (deferimento)",
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
THRESHOLD_FONETICO: float = float(os.getenv("THRESHOLD_FONETICO", "0.72"))
THRESHOLD_ESPECIFICACAO: float = float(os.getenv("THRESHOLD_ESPECIFICACAO", "0.40"))
THRESHOLD_SCORE_FINAL: float = float(os.getenv("THRESHOLD_SCORE_FINAL", "0.60"))
THRESHOLD_NUCLEO: float = 0.80

# ---------------------------------------------------------------------------
# Pesos do score composto (Camada 4)
# ---------------------------------------------------------------------------
PESO_SIMILARIDADE_NOME: float = 0.35
PESO_AFINIDADE_SPEC: float = 0.25
PESO_NUCLEO_MARCARIO: float = 0.15
PESO_FONETICA: float = 0.10
PESO_TIPO_MARCA: float = 0.10
PESO_BONUS: float = 0.05

# Classes que requerem cautela extra (saúde)
CLASSES_CAUTELA_ALTA: frozenset[int] = frozenset({5, 10, 44})
FATOR_CAUTELA: float = 0.85

# ---------------------------------------------------------------------------
# IA (OpenAI)
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BATCH_SIZE_IA: int = 50
MAX_PARES_IA: int = 15000
BUDGET_SEMANAL_USD: float = float(os.getenv("BUDGET_SEMANAL_USD", "18.0"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./outputs")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/colidencia.db")
DATA_DIR: str = os.path.join(os.path.dirname(__file__), "data")

# ---------------------------------------------------------------------------
# Retenção de dados
# ---------------------------------------------------------------------------
RETENTION_DAYS: int = 60

# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# ---------------------------------------------------------------------------
# Complementos descritivos (removidos do núcleo marcário)
# ---------------------------------------------------------------------------
COMPLEMENTOS_DESCRITIVOS: frozenset[str] = frozenset({
    "studio", "estudio", "atelier", "atelie", "oficina", "loja", "casa",
    "centro", "espaco", "clinica", "consultorio", "laboratorio", "academia",
    "instituto", "escola", "farmacia", "drogaria", "hamburgueria", "pizzaria",
    "padaria", "confeitaria", "sorveteria", "barbearia", "petshop",
    "store", "boutique", "shop", "market", "megastore", "outlet",
    "moda", "infantil", "kids", "baby", "trade", "telecom", "tech",
    "comercio", "servicos", "produtos", "industria", "importacao", "exportacao",
    "grupo", "rede", "franquia", "import", "export", "racing", "motorsports",
    "solucoes", "inteligencia", "assessoria", "consultoria",
    "design", "conceito", "multivendas", "climatizacao", "moveis",
    "placas", "motos", "transports", "componentes",
    "digital", "online", "express", "plus", "premium", "gold", "pro",
    "delivery", "fitness", "pilates", "yoga", "crossfit",
    "croche", "malhas", "tecidos", "confeccao", "costura",
})

# ---------------------------------------------------------------------------
# Elementos desgastados (baixa distintividade)
# ---------------------------------------------------------------------------
ELEMENTOS_DESGASTADOS: frozenset[str] = frozenset({
    "super", "max", "maxi", "mega", "ultra", "hiper", "hyper",
    "casa", "centro", "rede", "grupo", "brasil", "brazil",
    "nacional", "global", "master", "prime", "top", "plus",
    "gold", "premium", "express", "fast", "smart", "tech",
    "eco", "bio", "green", "life", "nova", "novo", "total",
    "good", "best", "ponto", "ideal", "real",
})

# ---------------------------------------------------------------------------
# Matriz de classes colidentes (NCL 13)
# ---------------------------------------------------------------------------
COLLISIONS: dict[int, list[int]] = {
    1: [2, 3, 4, 5, 17, 19, 40, 42],
    2: [1, 3, 16, 17, 19, 40],
    3: [1, 2, 5, 21, 44],
    4: [1, 7, 12, 40],
    5: [1, 3, 10, 29, 31, 44],
    6: [7, 8, 11, 12, 17, 19, 20, 21, 37],
    7: [4, 6, 8, 9, 11, 12, 37, 40, 42],
    8: [6, 7, 21, 28],
    9: [7, 10, 14, 15, 16, 28, 35, 38, 41, 42],
    10: [5, 9, 44],
    11: [6, 7, 19, 20, 37],
    12: [4, 6, 7, 28, 37, 39],
    13: [28],
    14: [9, 18, 25, 26],
    15: [9, 28, 41],
    16: [2, 9, 28, 35, 38, 41, 42],
    17: [1, 2, 6, 19, 40],
    18: [14, 24, 25, 26],
    19: [1, 2, 6, 11, 17, 37, 40],
    20: [6, 11, 21, 27],
    21: [3, 6, 8, 20, 29, 30],
    22: [23, 24, 27],
    23: [22, 24, 25, 26],
    24: [18, 22, 23, 25, 26, 27],
    25: [14, 18, 23, 24, 26, 35],
    26: [14, 18, 23, 24, 25],
    27: [20, 22, 24],
    28: [8, 9, 12, 13, 15, 16, 41],
    29: [5, 21, 30, 31, 32, 35, 43],
    30: [21, 29, 31, 32, 35, 43],
    31: [5, 29, 30, 44],
    32: [29, 30, 33, 43],
    33: [32, 43],
    34: [35],
    35: [9, 16, 25, 29, 30, 34, 36, 38, 39, 40, 41, 42, 43, 44, 45],
    36: [35, 39, 45],
    37: [6, 7, 11, 12, 19, 40],
    38: [9, 16, 35, 41, 42],
    39: [12, 35, 36, 43],
    40: [1, 2, 4, 7, 17, 19, 35, 37, 42],
    41: [9, 15, 16, 28, 35, 38, 42, 43, 44],
    42: [1, 7, 9, 16, 35, 38, 40, 41, 45],
    43: [29, 30, 32, 33, 35, 39, 41],
    44: [3, 5, 10, 31, 35, 41, 45],
    45: [35, 36, 42, 44],
}


def classes_colidem(cls_a: int, cls_b: int) -> bool:
    """Retorna True se as classes são iguais ou colidentes."""
    if cls_a == cls_b:
        return True
    return cls_b in COLLISIONS.get(cls_a, [])
