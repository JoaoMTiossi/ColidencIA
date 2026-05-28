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
THRESHOLD_FONETICO: float = float(os.getenv("THRESHOLD_FONETICO", "0.70"))
THRESHOLD_ESPECIFICACAO: float = float(os.getenv("THRESHOLD_ESPECIFICACAO", "0.40"))
THRESHOLD_SCORE_FINAL: float = float(os.getenv("THRESHOLD_SCORE_FINAL", "0.55"))
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

# Peso do score da superfície 2D (Regra Inversa) no blend final.
# 0.30 = 30% superfície 2D + 70% SAW.
PESO_REGRA_INVERSA: float = float(os.getenv("PESO_REGRA_INVERSA", "0.30"))

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
# Alertas de disponibilidade
# ---------------------------------------------------------------------------
# URL de webhook para notificações de startup/shutdown.
# Suporta Discord (https://discord.com/api/webhooks/...) e qualquer webhook
# genérico que aceite POST com JSON {"content": "..."} ou {"text": "..."}.
ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
ALERT_SERVICE_NAME: str = os.getenv("ALERT_SERVICE_NAME", "ColidencIA")

# ---------------------------------------------------------------------------
# Corpus de vocabulário descritivo por classe (Fase 2)
# ---------------------------------------------------------------------------
# Mínimo de marcas distintas processadas para uma classe ser considerada
# com amostra suficiente para gerar vocab automático.
CORPUS_MIN_AMOSTRA_CLASSE: int = int(os.getenv("CORPUS_MIN_AMOSTRA", "300"))
# Frequência relativa mínima: termo descritivo se aparece em >= X% das marcas da classe.
CORPUS_LIMIAR_FREQ: float = float(os.getenv("CORPUS_LIMIAR_FREQ", "0.01"))
# Frequência absoluta mínima: ignorar limiares de freq se o termo aparece em < N marcas.
CORPUS_LIMIAR_ABS: int = int(os.getenv("CORPUS_LIMIAR_ABS", "15"))

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
    # Produtos alimentícios usados como tipo de negócio
    "sorvete", "sorvetes", "acai", "salgados", "doces", "bolos",
    # Veículos, peças e serviços automotivos
    "veiculos", "automoveis", "autopecas", "pneus", "motores",
    # Outros setores descritivos frequentes
    "embalagens", "pinturas", "grafica", "graficas",
    "supermercado", "supermercados", "mercados",
    "imoveis", "imobilio",
    "igreja", "templo", "paroquia",
    # Tipos de estabelecimento alimentício
    "cafe", "cafeteria", "bar", "restaurante", "cantina", "lanchonete",
    "bistrô", "bistro", "choperia", "cervejaria", "pizzeria",
    # Saúde e serviços médicos
    "hospital", "clinica", "medicina", "medico", "medica",
    "veterinaria", "farmaceutica",
    # Construção e imóveis
    "construtora", "imobiliaria", "incorporadora",
    # Serviços financeiros
    "financeira", "corretora", "seguradora", "administradora",
    # Logística e distribuição
    "distribuidora", "transportadora", "logistica",
    # Outros tipos de negócio
    "contabilidade", "contabil", "tecnologia", "sistemas", "software",
    "saude", "energia", "construcao",
    # Serviços automotivos e especializados
    "funilaria", "serralheria", "borracharia", "mecanica", "chaveiro",
    "marcenaria", "pintura", "eletrica", "hidraulica",
    # Varejo especializado
    "joalheria", "relojoaria", "otica", "oticas", "floricultura",
    "lavanderia", "tinturaria",
    # Saúde bucal e estética
    "odontologia", "odonto", "ortodontia", "estetica",
    # Alimentação especializada
    "acougue", "peixaria", "hortifruti", "mercearia", "quitanda",
    # Serviços pessoais
    "depilacao", "massagem", "spa",
})

# ---------------------------------------------------------------------------
# Elementos desgastados (baixa distintividade)
# ---------------------------------------------------------------------------
ELEMENTOS_DESGASTADOS: frozenset[str] = frozenset({
    # Intensificadores e superlativos
    "super", "max", "maxi", "mega", "ultra", "hiper", "hyper", "extra",
    "multi", "mini", "micro", "macro", "big", "grande",
    # Qualidade/excelência
    "prime", "premium", "master", "gold", "silver", "platinum", "diamond",
    "top", "plus", "best", "good", "great", "first", "one", "numero",
    "royal", "imperial", "classic", "classico", "original", "autentico",
    "exclusive", "exclusivo", "unique", "unico", "especial", "special",
    "superior", "elite", "vip",
    # Modernidade e tecnologia
    "smart", "tech", "digital", "online", "virtual", "net", "web",
    "express", "fast", "rapid", "quick", "agil", "veloz",
    # Sustentabilidade
    "eco", "bio", "green", "nature", "natural", "organico", "organic",
    # Localização e escopo
    "brasil", "brazil", "nacional", "global", "mundial", "internacional",
    "local", "regional", "universal", "total", "geral",
    "casa", "centro", "rede", "grupo", "holding", "corporacao",
    # Estilo de vida
    "life", "lifestyle", "living", "home", "house", "place", "spot",
    "zone", "city", "world", "way", "point", "ponto",
    # Cores e elementos visuais
    "nova", "novo", "blue", "red", "white", "black",
    # Adjetivos fracos
    "ideal", "real", "forte", "puro", "pura", "leve", "light", "soft",
    "hard", "only", "pure", "moderno", "modern",
    # Elementos naturais e celestiais
    "sol", "lua", "estrela", "star", "terra", "planeta", "universo",
    "universe", "fenix",
    # Metais e minerais preciosos (sem marca própria)
    "crystal", "magic", "magia",
    # Títulos e tratamentos comuns
    "santa", "santo", "sao", "dom", "dona", "rei", "king", "queen",
    "jr", "junior", "filho", "irmaos", "brothers", "family", "familia",
    # Letras gregas e símbolos genéricos
    "alfa", "beta", "delta", "omega",
    # Outros muito comuns
    "power", "energy", "force", "forte", "vitoria", "sucesso",
    "clube", "club", "art", "studio", "store", "shop", "market",
    "nossa", "nosso", "meu", "minha",
    # Setores / atividades econômicas — sem distintividade própria
    "saude", "energia", "construcao", "logistica", "transporte",
    "alimentar", "alimentacao", "educacao", "seguranca", "comunicacao",
    "inovacao", "gestao", "qualidade", "credito", "financeiro", "capital",
    "sistemas", "tecnologia", "software", "plataforma",
    "dental", "odonto", "clinico", "clinica", "medico", "medica",
    "imobiliario", "juridico", "contabil",
    "banco", "seguros", "seguro",
    # Bebidas/alimentos como setor
    "cafe", "bebida", "alimento",
    # Qualificadores comerciais genéricos
    "empresarial", "profissional", "comercial", "industrial",
    "servico", "produto", "solucao",
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
