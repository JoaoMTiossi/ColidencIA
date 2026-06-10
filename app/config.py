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
THRESHOLD_FONETICO: float = float(os.getenv("THRESHOLD_FONETICO", "0.60"))
THRESHOLD_ESPECIFICACAO: float = float(os.getenv("THRESHOLD_ESPECIFICACAO", "0.40"))
THRESHOLD_SCORE_FINAL: float = float(os.getenv("THRESHOLD_SCORE_FINAL", "0.62"))
THRESHOLD_NUCLEO: float = 0.80

# ---------------------------------------------------------------------------
# Pesos do score composto (Camada 4) — derivados via AHP
# ---------------------------------------------------------------------------
# Pesos obtidos pelo método AHP (Analytic Hierarchy Process) a partir das
# comparações par-a-par do especialista. Reproduza com:
#   python -m app.tests.ahp_pesos
# CR (razão de consistência) < 0.10 em todos os níveis. Soma = 1.0.
# Prioridade resultante: spec (0.357) > núcleo (0.282) > tipo (0.143) >
# fonética (0.079) > bônus classe (0.071) > nome completo (0.067).
PESO_SIMILARIDADE_NOME: float = float(os.getenv("PESO_SIMILARIDADE_NOME", "0.0669"))
PESO_AFINIDADE_SPEC: float = float(os.getenv("PESO_AFINIDADE_SPEC", "0.3571"))
PESO_NUCLEO_MARCARIO: float = float(os.getenv("PESO_NUCLEO_MARCARIO", "0.2823"))
PESO_FONETICA: float = float(os.getenv("PESO_FONETICA", "0.0794"))
PESO_TIPO_MARCA: float = float(os.getenv("PESO_TIPO_MARCA", "0.1429"))
PESO_BONUS: float = float(os.getenv("PESO_BONUS", "0.0714"))

# Peso do score da superfície 2D (Regra Inversa) no blend final.
# 0.30 = 30% superfície 2D + 70% SAW.
PESO_REGRA_INVERSA: float = float(os.getenv("PESO_REGRA_INVERSA", "0.30"))

# Classes que requerem cautela extra (saúde)
CLASSES_CAUTELA_ALTA: frozenset[int] = frozenset({5, 10, 44})
FATOR_CAUTELA: float = 0.85

# Classes transversais: cobrem comércio/serviços de quase todos os produtos
# (35 = publicidade/gestão de negócios/comércio). Uma marca de varejo/serviço
# da classe 35 pode colidir com a marca do produto correspondente em qualquer
# classe de bens. São tratadas como elegíveis contra todas as classes.
CLASSES_TRANSVERSAIS: frozenset[int] = frozenset({35})
# Afinidade-base atribuída a um par que envolve classe transversal em classes
# distintas (acima do THRESHOLD_ESPECIFICACAO para não ser descartado, mas
# abaixo de "mesma classe"; a similaridade semântica de spec refina depois).
AFINIDADE_TRANSVERSAL: float = float(os.getenv("AFINIDADE_TRANSVERSAL", "0.45"))
# Overlap textual mínimo para pares cross-class passarem a Camada 3
# sem apoio de classe genuinamente afim (afasta falsos cruzamentos via classe 35).
THRESHOLD_SPEC_CROSS: float = float(os.getenv("THRESHOLD_SPEC_CROSS", "0.10"))

# ---------------------------------------------------------------------------
# IA (Anthropic Claude — preferido; OpenAI como fallback)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BATCH_SIZE_IA: int = int(os.getenv("BATCH_SIZE_IA", "20"))
MAX_PARES_IA: int = int(os.getenv("MAX_PARES_IA", "15000"))
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
CORPUS_MIN_AMOSTRA_CLASSE: int = int(os.getenv("CORPUS_MIN_AMOSTRA", "200"))
# Frequência relativa mínima: termo descritivo se aparece em >= X% das marcas da classe.
CORPUS_LIMIAR_FREQ: float = float(os.getenv("CORPUS_LIMIAR_FREQ", "0.004"))
# Frequência absoluta mínima: ignorar limiares de freq se o termo aparece em < N marcas.
CORPUS_LIMIAR_ABS: int = int(os.getenv("CORPUS_LIMIAR_ABS", "10"))

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
    # Saúde digital e telemedicina
    "telemedicina", "telessaude",
    # Produto/processo industrial
    "injetados", "moldados", "usinados", "laminados",
    # Qualificadores de público-alvo e gênero — descritivos, sem distintividade
    "feminina", "feminino", "masculina", "masculino", "unissex",
    "infantil", "adulto", "adultos", "juvenil",
    # Qualificadores genéricos em inglês usados como sufixo descritivo
    "fit", "life", "care", "well", "hub", "lab",
    # Tipos de estabelecimento comercial/alimentício adicionais
    "emporio",       # ex: EMPÓRIO SOUZA → nucleo=souza
    "mercearia",
    # Setoriais que vazaram na auditoria das RPIs 2884/2885/2886 (descrevem o
    # ramo, não a marca — observados governando match_distintivo indevidamente)
    "eletro", "eletros", "semijoias", "semijoia", "bijoux", "bijuteria",
    "planejados", "planejado", "estofados", "estofado", "marmoraria",
    "enxovais", "enxoval", "artesanal", "artesanato", "esquadrias", "esquadria",
    "academy", "performance", "experience", "multimarcas", "multimarca",
    "uniformes", "uniforme", "calhas", "telhas", "vidracaria", "vidros",
    "climatizacao", "refrigeracao", "ferragens", "ferragem", "tintas",
    "materiais", "material", "ferramentas", "equipamentos", "suprimentos",
    "presentes", "variedades", "utilidades", "atacado", "varejo", "atacadao",
    # Serviços técnicos especializados — descrevem a ATIVIDADE, não o nome
    # (permitem que o núcleo sigla/nome próprio seja comparado isolado)
    "rebobinagem",   # ex: LL REBOBINAGEM → nucleo=ll
    "hidromecanica", # ex: L&L HIDROMECÂNICA → nucleo=ll
    "eletromecânica", "eletromecanica",
    "caldeiraria",
    "usinagem",
    "soldagem",
    "galvanizacao", "galvanoplastia",
    "retifica", "retificadora",
    "vulcanizadora", "vulcanizacao",
    "locacoes", "locacao",  # ex: MG LOCAÇÕES → nucleo=mg
    "guindastes",
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
    "hard", "pure", "moderno", "modern",
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
    3: [1, 2, 5, 21, 40, 44],
    4: [1, 7, 12, 40],
    5: [1, 3, 10, 29, 31, 40, 44],
    6: [7, 8, 11, 12, 17, 19, 20, 21, 37],
    7: [4, 6, 8, 9, 11, 12, 37, 40, 42],
    8: [6, 7, 21, 28],
    9: [7, 10, 14, 15, 16, 28, 35, 36, 37, 38, 39, 40, 41, 42],
    10: [5, 9, 44],
    11: [6, 7, 19, 20, 37, 40],
    12: [4, 6, 7, 28, 37, 39],
    13: [28],
    14: [9, 18, 25, 26, 40, 41],
    15: [9, 28, 41],
    16: [2, 9, 28, 35, 38, 41, 42],
    17: [1, 2, 6, 19, 40],
    18: [14, 24, 25, 26],
    19: [1, 2, 6, 11, 17, 37, 40],
    20: [6, 11, 21, 27, 40],
    21: [3, 6, 8, 20, 29, 30],
    22: [23, 24, 27],
    23: [22, 24, 25, 26],
    24: [18, 22, 23, 25, 26, 27],
    25: [14, 18, 23, 24, 26, 35, 39, 42],
    26: [14, 18, 23, 24, 25],
    27: [20, 22, 24],
    28: [8, 9, 12, 13, 15, 16, 41],
    29: [5, 21, 30, 31, 32, 35, 40, 43],
    30: [21, 29, 31, 32, 35, 39, 40, 43],
    31: [5, 29, 30, 40, 44],
    32: [29, 30, 33, 40, 43],
    33: [32, 40, 43],
    34: [35],
    35: [9, 16, 25, 29, 30, 34, 36, 38, 39, 40, 41, 42, 43, 44, 45],
    36: [9, 35, 39, 41, 44, 45],
    37: [6, 7, 9, 11, 12, 19, 39, 40, 41],
    38: [9, 16, 35, 41, 42],
    39: [12, 25, 30, 35, 36, 37, 40, 43, 44],
    40: [1, 2, 3, 4, 5, 7, 9, 11, 14, 17, 19, 20, 29, 30, 31, 32, 33, 35, 37, 39, 41, 42, 43, 44, 45],
    41: [9, 14, 15, 16, 28, 35, 36, 37, 38, 40, 42, 43, 44],
    42: [1, 7, 9, 16, 25, 35, 38, 40, 41, 45],
    43: [29, 30, 32, 33, 35, 39, 40, 41],
    44: [3, 5, 10, 31, 35, 36, 39, 40, 41, 45],
    45: [35, 36, 40, 42, 44],
}


def classes_colidem(cls_a: int, cls_b: int) -> bool:
    """Retorna True se as classes são iguais ou colidentes."""
    if cls_a == cls_b:
        return True
    return cls_b in COLLISIONS.get(cls_a, [])
