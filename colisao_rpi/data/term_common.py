"""
Termos genéricos/comuns centralizados — fonte única de verdade.

TRÊS CATEGORIAS:

  CAT_1_DESCRITORES  — descritores de segmento: param extract_nucleus E excluem R4c.
                        Ex: CONTABILIDADE, ENGENHARIA, LOGISTICA.
                        Esses termos indicam o ramo de atividade mas não podem
                        ser monopolizados isoladamente como elemento distintivo.

  CAT_2_QUALIFICADORES — qualificadores genéricos: excluem R4c mas NÃO param nucleus.
                          Podem fazer parte do conjunto distintivo quando combinados.
                          Ex: BRASIL, MASTER, PRIME, DIGITAL, NACIONAL.

  CAT_3_ESTRUTURAIS  — stopwords gramaticais puras: param nucleus, excluem tudo.
                        Ex: DE, DO, DA, E, LTDA, MEI.

Uso:
    from colisao_rpi.data.term_common import (
        DESCRITORES, QUALIFICADORES, ESTRUTURAIS,
        TODOS_GENERICOS,   # union das 3 categorias
        PARAM_NUCLEUS,     # CAT_1 | CAT_3  (para extract_nucleus)
        EXCLUIR_R4C,       # CAT_1 | CAT_2  (para _token_keys)
    )
"""

from __future__ import annotations

# ===========================================================================
# CAT_1 — DESCRITORES DE SEGMENTO
# ===========================================================================
CAT_1_DESCRITORES: frozenset[str] = frozenset({

    # --- Jurídico / advocacia ---
    'ADVOCACIA', 'ADVOGADOS', 'ADVOGADO', 'JURIDICO', 'JURIDICA',
    'ESCRITORIO', 'ESCRIT RIO', 'ASSESSORIA', 'ASSESSORIAS',
    'CONSULTORIA', 'CONSULTORIAS', 'NOTARIO', 'CARTORIO',
    'CONTENCIOSO', 'COMPLIANCE', 'REGULATORIO',

    # --- Contabilidade / finanças ---
    'CONTABILIDADE', 'CONTABIL', 'CONTABEIS', 'CONTADOR', 'CONTADORES',
    'FINANCEIRA', 'FINANCEIRO', 'FINANCEIRAS', 'FINANCEIROS',
    'FINANCAS', 'AUDITORIA', 'AUDITORES', 'TRIBUTARIO', 'TRIBUTARIA',
    'FISCAL', 'FISCAIS', 'PERICIA', 'PERICIAS', 'GESTAO',
    'ADMINISTRACAO', 'CONTROLADORIA',

    # --- Seguros / corretagem ---
    'SEGUROS', 'SEGURO', 'CORRETORA', 'CORRETORAS', 'CORRETOR',
    'CORRETORES', 'PREVIDENCIA', 'PLANO', 'PLANOS', 'SINISTRO',
    'RESSEGUROS', 'ATUARIA', 'BENEFICIOS',

    # --- Crédito / investimentos ---
    'CREDITO', 'CREDITOS', 'FINANCIAMENTO', 'FINANCIAMENTOS',
    'INVESTIMENTOS', 'INVESTIMENTO', 'PATRIMONIO', 'CAPITAL',
    'EMPRESTIMOS', 'EMPRESTIMO', 'CONSORCIO', 'CONSORCIOS',
    'CAMBIO', 'VALORES', 'ACOES', 'BOLSA', 'FUNDO', 'FUNDOS',

    # --- Imóveis / construção ---
    'IMOVEIS', 'IMOBILIARIA', 'IMOBILIARIAS', 'IMÓVEIS',
    'INCORPORADORA', 'INCORPORADORAS', 'CONSTRUTORA', 'CONSTRUTORAS',
    'CONSTRUCAO', 'CONSTRUÇÕES', 'ENGENHARIA', 'ENGENHARIAS',
    'ARQUITETURA', 'ARQUITETURAS', 'REFORMAS', 'REFORMA',
    'EMPREENDIMENTOS', 'EMPREENDIMENTO', 'LOTEAMENTOS', 'LOTEAMENTO',
    'INCORPORACAO', 'RESIDENCIAL', 'RESIDENCIAIS', 'COMERCIAL',
    'COMERCIAIS', 'OBRAS', 'PROJETOS', 'PROJETO',
    'ELETRICA', 'ELETRICO', 'HIDRAULICA', 'HIDRAULICO',
    'PINTURAS', 'PINTURA', 'INSTALACOES', 'INSTALACAO',
    'MANUTENCAO', 'MANUTENCOES', 'ESTRUTURAS', 'ESTRUTURA',

    # --- Tecnologia / TI ---
    'TECNOLOGIA', 'TECNOLOGIAS', 'SISTEMAS', 'SISTEMA',
    'INFORMATICA', 'SOFTWARE', 'HARDWARE', 'DESENVOLVIMENTO',
    'DESENVOLVEDORA', 'INOVACAO', 'INOVACOES', 'SOLUCOES', 'SOLUCAO',
    'AUTOMACAO', 'ROBOTICA', 'INTELIGENCIA', 'ARTIFICIAL',
    'COMPUTACAO', 'PROGRAMACAO', 'APLICATIVO', 'APLICATIVOS',
    'PLATAFORMA', 'PLATAFORMAS', 'SUPORTE', 'SERVICOS',

    # --- Saúde ---
    'SAUDE', 'CLINICA', 'CLINICAS', 'HOSPITAL', 'HOSPITAIS',
    'LABORATORIO', 'LABORATORIOS', 'FARMACIA', 'FARMACIAS',
    'DROGARIA', 'DROGARIAS', 'ODONTOLOGIA', 'ODONTOLOGICO',
    'DENTISTA', 'DENTISTAS', 'MEDICO', 'MEDICOS', 'MEDICA',
    'NUTRICAO', 'NUTRICIONAL', 'NUTRICIONISTA', 'FISIOTERAPIA',
    'FISIOTERAPEUTA', 'PSICOLOGIA', 'PSICOLOGO', 'PSICANALISE',
    'TERAPIA', 'TERAPIAS', 'TERAPEUTA', 'OCUPACIONAL',
    'ORTOPEDIA', 'CARDIOLOGIA', 'DERMATOLOGIA', 'PEDIATRIA',
    'GINECOLOGIA', 'ONCOLOGIA', 'RADIOLOGIA', 'DIAGNOSTICO',
    'EXAMES', 'VACINAS', 'VACINA', 'HOMECARE', 'HOME',

    # --- Veterinária / pets ---
    'VETERINARIA', 'VETERINARIO', 'VETERINARIOS', 'VETERINARIAS',
    'PETSHOP', 'PETS', 'PET', 'CANIL', 'GATIL',
    'BANHO', 'TOSA', 'RACAO', 'RACOES',

    # --- Estética / beleza ---
    'ESTETICA', 'ESTETICAS', 'ESTETICO', 'BELEZA', 'SALAO',
    'BARBEARIA', 'BARBEARIAS', 'CABELOS', 'CABELO',
    'UNHAS', 'MANICURE', 'PEDICURE', 'SOBRANCELHA', 'SOBRANCELHAS',
    'DEPILACAO', 'MAQUIAGEM', 'MAKEUP', 'COSMETICOS',
    'ESTETICISTA', 'MICROPIGMENTACAO', 'EXTENSAO', 'CABELEIREIRO',

    # --- Educação ---
    'EDUCACAO', 'ESCOLA', 'ESCOLAS', 'COLEGIO', 'COLEGIOS',
    'ACADEMIA', 'ACADEMIAS', 'INSTITUTO', 'INSTITUTOS',
    'CENTRO', 'CURSOS', 'CURSO', 'TREINAMENTO', 'TREINAMENTOS',
    'CAPACITACAO', 'CAPACITACOES', 'IDIOMAS', 'IDIOMA',
    'ENSINO', 'APRENDIZAGEM', 'FORMACAO', 'FACULDADE', 'FACULDADES',
    'UNIVERSITARIO', 'UNIVERSITARIA', 'PEDAGOGICO', 'PEDAGOGICA',
    'MENTORIA', 'COACHING', 'COACH',

    # --- Alimentação ---
    'RESTAURANTE', 'RESTAURANTES', 'LANCHONETE', 'LANCHONETES',
    'PADARIA', 'PADARIAS', 'CONFEITARIA', 'CONFEITARIAS',
    'DOCERIA', 'DOCERIAS', 'PIZZARIA', 'PIZZARIAS',
    'HAMBURGUERIA', 'HAMBURGUERIAS', 'SUSHI', 'TEMAKERIA',
    'CAFETERIA', 'CAFETERIAS', 'BISTRÔ', 'BISTRO',
    'CHURRASCARIA', 'CHURRASCARIAS', 'BUFFET', 'QUITANDA',
    'SORVETERIA', 'SORVETES', 'ACAI', 'CREPERIA',
    'TAPIOCA', 'HOTDOG', 'ESFIHARIA', 'PASTELARIA',
    'COMIDA', 'ALIMENTOS', 'REFEICOES', 'GASTRONOMIA',
    'CULINARIA', 'DELIVERY', 'ENTREGA', 'MARMITA',

    # --- Bebidas ---
    'CERVEJARIA', 'CERVEJA', 'CERVEJAS', 'CHOPERIA', 'CHOPP',
    'ADEGA', 'ADEGAS', 'VINHOS', 'VINHO', 'DESTILADOS',
    'CACACA', 'BEBIDAS', 'BEBIDA', 'SUCOS', 'SUCO',
    'AGUA', 'AGUAS',

    # --- Varejo / comércio ---
    'COMERCIO', 'COMERCIOS', 'LOJA', 'LOJAS', 'MERCADO',
    'MERCADOS', 'SUPERMERCADO', 'SUPERMERCADOS', 'HIPERMERCADO',
    'ATACADO', 'ATACADISTA', 'DISTRIBUIDORA', 'DISTRIBUIDORAS',
    'IMPORTADORA', 'IMPORTADORAS', 'EXPORTADORA', 'EXPORTADORAS',
    'REPRESENTACOES', 'REPRESENTACAO', 'VENDAS', 'VENDA',
    'MARKETPLACE', 'SHOPPING', 'GALERIA', 'LOJA',

    # --- Moda / vestuário ---
    'MODA', 'MODAS', 'FASHION', 'VESTUARIO', 'CONFECCOES',
    'CONFECCAO', 'ROUPAS', 'ROUPA', 'CALCADOS', 'CALCADO',
    'BOLSAS', 'BOLSA', 'ACESSORIOS', 'ACESSORIO',
    'FEMININA', 'FEMININO', 'FEMININAS', 'FEMININOS',
    'MASCULINO', 'MASCULINA', 'MASCULINOS', 'MASCULINAS',
    'INFANTIL', 'INFANTIS', 'JUVENIL', 'JUVENIS',
    'LINGERIE', 'UNDERWEAR', 'BEACHWEAR', 'SPORTSWEAR',
    'JEANS', 'CAMISAS', 'CALCAS', 'VESTIDOS',

    # --- Móveis / decoração ---
    'MOVEIS', 'MOVEL', 'PLANEJADOS', 'PLANEJADO',
    'DECORACAO', 'DECORACOES', 'INTERIORES', 'DESIGN',
    'COLCHOES', 'COLCHAO', 'ESTOFADOS', 'ESTOFADO',
    'COZINHAS', 'COZINHA', 'ARMARIOS', 'ARMARIO',

    # --- Automotivo ---
    'VEICULOS', 'VEICULO', 'AUTOMOVEIS', 'AUTOMOVEL',
    'AUTOPECAS', 'AUTOPECA', 'PNEUS', 'PNEU',
    'CONCESSIONARIA', 'REVISAO', 'OFICINA', 'FUNILARIA',
    'MECANICA', 'ELETRICA', 'MOTORES', 'MOTOR',
    'MOTO', 'MOTOS', 'MOTOCICLETAS', 'CICLISMO',
    'CAMINHOES', 'CAMINHAO', 'FROTAS', 'FROTA',

    # --- Transporte / logística ---
    'LOGISTICA', 'TRANSPORTES', 'TRANSPORTE', 'MUDANCAS',
    'MUDANCA', 'FRETE', 'FRETES', 'CARGAS', 'CARGA',
    'COURIER', 'EXPEDICAO', 'RASTREAMENTO', 'ARMAZENAGEM',
    'ARMAZEM', 'DEPOSITO', 'DEPOSITOS', 'DISTRIBUICAO',

    # --- Agronegócio ---
    'AGRONEGOCIO', 'AGRONEGÓCIOS', 'AGROPECUARIA', 'AGRICOLA',
    'RURAL', 'CAMPO', 'PRODUCAO', 'SAFRA', 'COLHEITA',
    'SEMENTES', 'INSUMOS', 'FERTILIZANTES', 'AGRONOMIA',
    'PECUARIA', 'AVICULTURA', 'SUINOCULTURA', 'AQUICULTURA',
    'IRRIGACAO', 'MAQUINAS', 'IMPLEMENTOS',

    # --- Eventos / entretenimento ---
    'EVENTOS', 'EVENTO', 'FESTAS', 'FESTA', 'CASAMENTOS',
    'CASAMENTO', 'FORMATURAS', 'FORMATURA', 'BUFFET',
    'SONORIZACAO', 'ILUMINACAO', 'DECORACOES', 'CERIMONIAL',
    'PRODUCOES', 'PRODUCAO', 'SHOWS', 'ESPETACULOS',

    # --- Fitness / esportes ---
    'FITNESS', 'PILATES', 'CROSSFIT', 'SPINNING', 'MUSCULACAO',
    'NATACAO', 'FUTEBOL', 'ESPORTES', 'ESPORTE',
    'GINASTICA', 'YOGA', 'LUTAS', 'ARTES', 'MARCIAIS',

    # --- Turismo / hotelaria ---
    'TURISMO', 'VIAGENS', 'VIAGEM', 'HOTEL', 'HOTEIS',
    'POUSADA', 'POUSADAS', 'HOSPEDAGEM', 'HOSTEL',
    'RESORT', 'AGENCIA', 'AGENCIAS', 'RECEPTIVO',
    'EXCURSOES', 'ECOTURISMO', 'CRUZEIROS',

    # --- Limpeza / serviços gerais ---
    'LIMPEZA', 'LIMPEZAS', 'HIGIENIZACAO', 'LAVANDERIA',
    'LAVANDERIAS', 'TERCEIRIZACAO', 'JARDINAGEM',
    'PORTARIA', 'VIGILANCIA', 'SEGURANCA', 'MONITORAMENTO',
    'CONSERVACAO', 'FACILITIES',

    # --- Comunicação / marketing ---
    'COMUNICACAO', 'MARKETING', 'PUBLICIDADE', 'PROPAGANDA',
    'MIDIA', 'DIGITAL', 'AGENCIA', 'CRIACAO', 'CONTEUDO',
    'BRANDING', 'SOCIAL', 'INFLUENCER', 'STREAMING',

    # --- Energia / meio ambiente ---
    'ENERGIA', 'ENERGIAS', 'SOLAR', 'EOLICA', 'RENOVAVEL',
    'AMBIENTAL', 'SUSTENTABILIDADE', 'RESIDUOS', 'RECICLAGEM',
    'MEIO', 'AMBIENTE', 'ELETRICA',

    # --- Gráfica / impressão ---
    'GRAFICA', 'GRAFICAS', 'IMPRESSAO', 'IMPRESSOES',
    'PLOTAGEM', 'SINALIZAÇÃO', 'SINALIZACAO', 'BANNERS',
    'EMBALAGENS', 'EMBALAGEM', 'ROTULOS', 'ROTULO',

    # --- Outros serviços ---
    'STUDIO', 'STUDIOS', 'ATELIE', 'ATELIES',
    'FRANQUIA', 'FRANQUIAS', 'HOLDING', 'PARTICIPACOES',
    'GRUPO', 'GRUPOS',

    # --- Automotivo / limpeza (compostos comuns) ---
    'LAVA', 'LAVAGEM', 'LAVANDERIA', 'LAVAGENS',
    'JATO', 'LAVAJATO', 'BORRACHARIA', 'FUNILARIA',
    'MECANICA', 'BORRACHA', 'FUNILEIRO',

    # --- Agronegócio (complementos) ---
    'AGRO', 'AGROS', 'AGRI',

    # --- Construção / material ---
    'GESSO', 'GESSOS', 'ARGAMASSA', 'CIMENTO',
    'TINTAS', 'TINTA', 'VERNIZ', 'VERNIZES',
    'VIDROS', 'VIDRO', 'ALUMINIO', 'FERRAGENS',
    'FERRAGEM', 'PERSIANAS', 'PERSIANA',

    # --- Varejo / atacado ---
    'ATACADO', 'ATACADAO', 'ATACADISTA', 'ATACADISTAS',
    'VAREJAO', 'VAREJISTA',

    # --- Alimentação (complementos) ---
    'ESFIHA', 'ESFIHAS', 'COXINHA', 'COXINHAS',
    'PASTEL', 'PASTEIS', 'TAPIOCA', 'TAPIOCAS',
    'ACAI', 'SORVETE', 'SORVETES', 'GELATO',
    'BRIGADEIRO', 'BRIGADEIROS', 'BOLO', 'BOLOS',
    'SALGADO', 'SALGADOS', 'DOCE', 'DOCES',
    'MARMITA', 'MARMITAS', 'REFEICAO', 'REFEICOES',
    'PRATO', 'PRATOS',

    # --- Saúde / bem-estar (complementos) ---
    'CARE', 'CARES', 'SAUDE', 'WELLNESS',
    'OLEO', 'OLEOS',

    # --- Moda / esporte ---
    'SPORT', 'SPORTS', 'ESPORTIVO', 'ESPORTIVA',
    'BABY', 'KIDS', 'INFANTIS',
    'OUTLET', 'OUTLETS', 'BRECHÓ', 'BRECHO',

    # --- Comunicação / media ---
    'CANAL', 'CANAIS', 'MIDIA', 'MIDIAS',
    'RADIO', 'PODCAST', 'STREAMING',

    # --- Combustível / energia ---
    'DIESEL', 'GASOLINA', 'COMBUSTIVEL', 'COMBUSTIVEIS',
    'ETANOL', 'PETROLEO', 'GAS',

    # --- Serviços gerais (complementos) ---
    'BOMBAS', 'BOMBA', 'PISCINAS', 'PISCINA',
    'JARDIM', 'JARDINAGEM', 'PAISAGISMO',
    'DEDETIZACAO', 'DEDETIZADORA',

    # --- Tecnologia / digital ---
    'APP', 'APPS', 'APLICATIVO', 'APLICATIVOS',

    # --- Saúde / diagnóstico ---
    'IMAGEM', 'IMAGENS', 'DIAGNOSTICO', 'DIAGNOSTICOS',
    'RADIOLOGIA', 'ULTRASSOM', 'RESSONANCIA',

    # --- Temáticas genéricas ---
    'COWBOY', 'COWBOYS',
    'BOI', 'BOIS', 'BOVINO', 'BOVINOS',
    'RODEIO', 'RODEIOS', 'COUNTRY',
    'SERTANEJO', 'CAIPIRA',
})

# ===========================================================================
# CAT_2 — QUALIFICADORES GENÉRICOS
# (não param nucleus mas são excluídos do R4c isoladamente)
# ===========================================================================
CAT_2_QUALIFICADORES: frozenset[str] = frozenset({

    # Superlativos / qualidade
    'SUPER', 'MEGA', 'ULTRA', 'MAXI', 'MINI',
    'TOP', 'BEST', 'FIRST', 'UNIQUE', 'UNICO', 'UNICA',
    'MASTER', 'PREMIER', 'PREMIUM', 'PRIME', 'ELITE',
    'GOLD', 'SILVER', 'BRONZE', 'PLATINUM', 'PLATINA',
    'VIP', 'PLUS', 'PRO', 'MAX', 'MAXIMO',
    'TOTAL', 'GERAL', 'GLOBAL', 'FULL', 'COMPLETO',
    'IDEAL', 'PERFEITO', 'EXCELENTE', 'EXCELENCIA',
    'QUALITY', 'QUALIDADE',

    # Tecnologia / modernidade
    'DIGITAL', 'TECH', 'NET', 'WEB', 'ONLINE', 'VIRTUAL',
    'SMART', 'INTELI', 'FAST', 'SPEED', 'TURBO', 'FLEX',
    'CONNECT', 'LINK', 'HUB', 'LAB', 'LABS',

    # Escala / abrangência
    'MULTI', 'INTER', 'NACIONAL', 'REGIONAL', 'LOCAL',
    'BRASIL', 'BRASILEIRA', 'BRASILEIRAS', 'BRASILEIRO',
    'GLOBAL', 'MUNDIAL', 'INTERNACIONAL',

    # Localização genérica
    'NORTE', 'SUL', 'LESTE', 'OESTE',
    'NORDESTE', 'SUDESTE', 'CENTRO', 'CENTRAL',

    # Temporal / sequência
    'NOVA', 'NOVO', 'NOVAS', 'NOVOS',
    'MODERNA', 'MODERNO', 'MODERNAS', 'MODERNOS',
    'ATUAL', 'ATUALIZADA',
    'DIA', 'DIAS', 'DIARIO', 'DIARIA',   # "do dia", "de cada dia" — qualificador temporal

    # Natureza / elementos
    'VERDE', 'VERDE', 'NATURAL', 'NATURAIS',
    'VIDA', 'VIVA', 'VIVO', 'BIO', 'ECO', 'ORG',
    'ORGANICO', 'ORGANICA',

    # Tamanho / força
    'FORTE', 'FORTES', 'GRANDE', 'GRANDES',
    'REAL', 'REAIS', 'EXPRESS', 'EXPRESSO',

    # Cores (quando são qualificadores, não descritores)
    'AZUL', 'VERMELHO', 'VERMELHA', 'ROSA', 'PINK',
    'BRANCO', 'BRANCA', 'PRETO', 'PRETA',
    'AMARELO', 'AMARELA', 'LARANJA', 'ROXO', 'ROXA',
    'CINZA', 'DOURADO', 'DOURADA', 'PRATA',
    'VERDE', 'MARROM',

    # Outros genéricos
    'REDE', 'REDES', 'MUNDO', 'CASA', 'MAIS',
    'TUDO', 'FACIL', 'RAPIDO', 'RAPIDA',
    'POLAR', 'TROPICAL', 'SOLAR',
    'ACE', 'TOP', 'ONE', 'WIN',

    # Nomes geográficos / localidades genéricas
    'PORTO', 'PORTOS',
    'PARAISO', 'PARAÍSO',
    'JARDIM', 'JARDINS',
    'CENTRO', 'CENTROS',
    'VILA', 'VILAS',
    'BAIRRO', 'CIDADE',
    'CAMPO', 'CAMPOS',
    'VALE', 'VALES',
    'SERRA', 'SERRAS',
    'PRAIA', 'PRAIAS',
    'LAGO', 'LAGOS',
    'RIO', 'RIOS',
    'NORTE', 'SUL', 'LESTE', 'OESTE',

    # Qualificadores de escala / mercado
    'ZERO', 'ZEROS',   # "zero burocracia", "zero taxa" — genérico
    'FULL', 'PLUS',
    'ATACADAO', 'VAREJAO',

    # Inglês genérico adicional
    'CARE', 'HOME', 'HOUSE', 'MARKET', 'STORE',
    'GROUP', 'CORP', 'SOLUTIONS', 'SERVICES',
})

# ===========================================================================
# CAT_3 — ESTRUTURAIS / STOPWORDS PURAS
# ===========================================================================
CAT_3_ESTRUTURAIS: frozenset[str] = frozenset({

    # Preposições / conjunções
    'DE', 'DO', 'DA', 'DOS', 'DAS', 'DI',
    'E', 'EM', 'COM', 'PARA', 'POR', 'PRA',
    'NO', 'NA', 'NOS', 'NAS',
    'AO', 'AOS', 'A',
    'OU', 'SE', 'QUE', 'NEM', 'MAS',
    'ATÉ', 'ATE', 'DESDE', 'SOBRE', 'ENTRE', 'APOS',

    # Artigos
    'O', 'OS', 'AS',
    'UM', 'UMA', 'UNS', 'UMAS',

    # Sufixos jurídicos
    'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'SS',
    'MEI', 'CIA', 'COMPANHIA', 'INC', 'CORP', 'LLC',
    'SRL', 'SAS', 'SOCIEDADE',

    # Inglês
    'AND', 'OF', 'THE', 'FOR', 'BY', 'WITH',
    'IN', 'AT', 'TO', 'FROM', 'ON',

    # Espanhol
    'Y', 'DEL', 'LOS', 'LAS', 'POR', 'PARA',
    'EL', 'LA',

    # Símbolos / caracteres convertidos
    'AMP', 'CIA',
})

# ===========================================================================
# CONJUNTOS DERIVADOS — uso direto no engine
# ===========================================================================

# Para extract_nucleus: parar quando encontrar qualquer um desses
PARAM_NUCLEUS: frozenset[str] = CAT_1_DESCRITORES | CAT_3_ESTRUTURAIS

# Para _token_keys no R4c: excluir esses tokens do matching isolado
EXCLUIR_R4C: frozenset[str] = CAT_1_DESCRITORES | CAT_2_QUALIFICADORES | CAT_3_ESTRUTURAIS

# Union total
TODOS_GENERICOS: frozenset[str] = CAT_1_DESCRITORES | CAT_2_QUALIFICADORES | CAT_3_ESTRUTURAIS

# Aliases de conveniência
DESCRITORES   = CAT_1_DESCRITORES
QUALIFICADORES = CAT_2_QUALIFICADORES
ESTRUTURAIS   = CAT_3_ESTRUTURAIS


def is_generic(token: str) -> bool:
    """Retorna True se o token normalizado é genérico em qualquer categoria."""
    return token.upper() in TODOS_GENERICOS


def categoria(token: str) -> str | None:
    """Retorna a categoria do token ou None se for distintivo."""
    t = token.upper()
    if t in CAT_3_ESTRUTURAIS:   return 'ESTRUTURAL'
    if t in CAT_1_DESCRITORES:   return 'DESCRITOR'
    if t in CAT_2_QUALIFICADORES: return 'QUALIFICADOR'
    return None


if __name__ == '__main__':
    print(f'CAT_1 DESCRITORES  : {len(CAT_1_DESCRITORES):>4} termos')
    print(f'CAT_2 QUALIFICADORES: {len(CAT_2_QUALIFICADORES):>4} termos')
    print(f'CAT_3 ESTRUTURAIS  : {len(CAT_3_ESTRUTURAIS):>4} termos')
    print(f'TOTAL (sem duplicata): {len(TODOS_GENERICOS):>4} termos')
    print(f'PARAM_NUCLEUS      : {len(PARAM_NUCLEUS):>4} termos')
    print(f'EXCLUIR_R4C        : {len(EXCLUIR_R4C):>4} termos')
