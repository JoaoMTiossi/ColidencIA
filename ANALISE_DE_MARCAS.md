# Análise de Colidência de Marcas — Base de Conhecimento

> Documento consolidado com tudo que o sistema ColidencIA sabe sobre análise de marcas no contexto do INPI brasileiro.

---

## 1. Contexto Legal

### 1.1 Lei 9.279/96 — Lei da Propriedade Industrial (LPI)

| Artigo | Dispositivo | Relevância para o sistema |
|---|---|---|
| Art. 124, XIX | Proíbe registro de marca que reproduza ou imite marca de terceiro | Base da colidência |
| Art. 157 | INPI publica pedidos na RPI semanalmente | Fonte de dados da análise |
| Art. 158 | Prazo de **60 dias** para apresentar oposição após publicação | Prazo OPOSIÇÃO |
| Art. 168 | Nulidade administrativa pode ser pedida pelo INPI ou interessado | Base do PAN |
| Art. 169 | Prazo de **180 dias** após concessão para Pedido Administrativo de Nulidade | Prazo PAN |

### 1.2 Tipos de Ação

**OPOSIÇÃO**
- Ocorre quando o terceiro publicou um **pedido de registro** na RPI (ainda não concedido)
- O cliente tem **60 dias** a contar da data da publicação para ingressar com oposição
- Número de processo do terceiro: padrão `942xxxxx` ou `943xxxxx` (pedidos recentes)
- Despachos correspondentes: `IPAS009`, `IPAS756`, `IPAS421`, `IPAS135`

**PAN — Pedido Administrativo de Nulidade**
- Ocorre quando o terceiro **obteve o registro** (já concedido pelo INPI)
- O cliente tem **180 dias** a contar da data de concessão para ingressar com PAN
- Número de processo do terceiro: padrão `935xxxxx` (processos mais antigos já concedidos)
- Despachos correspondentes: `IPAS158`, `IPAS237`

---

## 2. Fontes de Dados

### 2.1 RPI — Revista de Propriedade Industrial

- Publicada **semanalmente** pelo INPI em formato **XML** (~48 MB)
- URL: `revistas.inpi.gov.br/rpi`
- O arquivo **XML é o correto** para processamento automatizado (o PDF existe mas não é legível por máquina)
- Estrutura relevante extraída por processo:
  - `numero` do processo
  - `nome` da marca
  - `apresentacao` (Nominativa, Mista, Figurativa)
  - `classe-nice` (código NCL e especificação)
  - `despacho` (código e nome)
  - `titular` (nome-razao-social)

### 2.2 Carteira de Clientes

- Planilha Excel exportada do sistema de gestão da agência (~46.556 processos)
- Formato do campo CLASSE: `35/10` (CLASSE/código interno) — **não** usar o segundo número
- Colunas relevantes por índice (base 0):

| Índice | Campo | Exemplo |
|---|---|---|
| 2 | PROCESSO | `006205534` |
| 3 | MARCA | `WALTER` |
| 4 | CLASSE | `35/10` → classe **35** |
| 5 | APRESENTAÇÃO | `Nominativa` |
| 18 | ESPECIFICAÇÃO | texto da especificação |
| 20 | TITULAR | `GRAFICA WALTER LTDA - ME` |

---

## 3. Classificação de Marcas

### 3.1 Classes NCL (Nice Classification)

Sistema internacional com **45 classes**:
- Classes 1–34: **produtos**
- Classes 35–45: **serviços**

Classes mais frequentes nos alertas de colidência:

| Classe | Descrição |
|---|---|
| 35 | Publicidade, gestão comercial, serviços administrativos |
| 40 | Tratamento de materiais, manufatura |
| 41 | Educação, entretenimento, esportes |
| 43 | Serviços de alimentação e hospedagem |
| 25 | Vestuário, calçados, chapelaria |
| 30 | Café, chá, açúcar, alimentos (farináceos) |
| 37 | Construção, reparação, serviços de instalação |
| 44 | Serviços médicos, veterinários, cuidados de beleza |

### 3.2 Matriz de Classes Colidentes

Algumas classes têm afinidade mercadológica entre si e devem ser consideradas colidentes mesmo quando diferentes:

| Classe | Colidentes com |
|---|---|
| 5 (farmacêuticos) | 1, 3, 10, 29, 31, 44 |
| 9 (eletrônicos) | 7, 10, 14, 15, 16, 28, 35, 38, 41, 42 |
| 25 (vestuário) | 14, 18, 23, 24, 26, 35 |
| 35 (serviços comerciais) | 36, 38, 41, 42 (indiretamente) |
| 44 (saúde) | 3, 5, 10 |

**Classes de cautela especial** (saúde): 5, 10, 44 — threshold reduzido em 15% (mais sensível).

### 3.3 Versões da NCL

O formato no relatório usa `NCL(versão) classe`:
- `NCL(12) 35` — 12ª edição (atual), classe 35
- `NCL(11) 35` — 11ª edição (registros mais antigos)
- A carteira usa o formato legado `CLASSE/código` (ex: `35/10`)

---

## 4. Tipos de Marca

| Apresentação | Descrição | Impacto na análise |
|---|---|---|
| **Nominativa** | Apenas texto/palavras | Comparação textual/fonética |
| **Figurativa** | Apenas imagem/figura | Excluída da comparação automática (sem nome) |
| **Mista** | Texto + imagem | Comparação pelo elemento nominativo |

**Marcas figurativas puras** são excluídas do pipeline (sem texto para comparar).

---

## 5. Elementos do Nome da Marca

### 5.1 Núcleo Marcário

A parte **distintiva** da marca — extraída removendo complementos descritivos.

Exemplos:
- `INSPIRE STUDIO DE PILATES` → núcleo: `INSPIRE`
- `CAVALINHO AZUL` → núcleo: `CAVALINHO AZUL`
- `A PLUS VIAGENS` → núcleo: `a plus viagens` (núcleo < 3 chars → usa nome completo)

### 5.2 Complementos Descritivos (~553 termos)

Palavras que **não fazem parte do núcleo** — indicam tipo de negócio:

| Categoria | Exemplos |
|---|---|
| Estabelecimentos | studio, clínica, consultório, academia, farmácia |
| Comércio | loja, mercado, store, boutique, shop |
| Alimentação | restaurante, hamburgueria, pizzaria, padaria, sorveteria |
| Serviços | assessoria, consultoria, soluções, serviços |
| Jurídico | ltda, me, epp, eireli, s.a. |
| Profissões | advogados, engenharia, arquitetura, odontologia |

### 5.3 Elementos Desgastados (~120 termos)

Palavras de **baixíssima distintividade** — usadas por tantas marcas que perderam capacidade diferenciadora:

| Categoria | Exemplos |
|---|---|
| Intensificadores | super, mega, ultra, hiper, maxi, extra |
| Qualidade | prime, premium, master, gold, platinum, top, plus |
| Tecnologia | smart, tech, digital, express, fast |
| Escopo | nacional, global, total, universal, brasil |
| Estilo de vida | life, home, house, club, world |
| Adjetivos genéricos | novo, nova, real, ideal, forte, puro |
| Grego | alfa, beta, delta, omega |

**Marca genérica**: núcleo composto **majoritariamente** por elementos desgastados:
- 100% dos tokens são desgastados → genérica
- ≥ 66% dos tokens (em nomes com ≥ 3 tokens) → genérica
- Qualquer token desgastado em nomes com ≤ 2 tokens → genérica

---

## 6. Pipeline de Detecção

### Visão Geral

```
Carteira (Excel)  ──┐
                    ├──► [PRÉ-PROCESSAMENTO] ──► [CAM. 1] ──► [CAM. 2] ──► [CAM. 3] ──► [CAM. 4] ──► Alertas
RPI (XML)         ──┘
```

### Camada 0 — Pré-processamento

Para cada marca, calcula:
- `nome_normalizado`: lowercase, sem acentos, sem pontuação
- `nucleo`: parte distintiva (sem complementos)
- `codigo_fonetico`: Metaphone PT-BR (máx. 6 chars)
- `bigrams_set`: bigramas de caracteres
- `is_sigla`: True se ≤ 4 chars alfanuméricos
- `is_nome_proprio`: heurística por maiúsculas
- `is_marca_generica`: núcleo fraco (ver seção 5.3)
- `is_desgastado`: qualquer token desgastado

### Camada 1 — Nome Idêntico

- **Hash lookup**: compara nome normalizado sem espaços
- Nome idêntico → score 1.0, classificação ALTA automática
- Núcleo idêntico (mas nome diferente) → score 0.85, verifica classes
- **Resultado**: alertas imediatos + RPI restante para Camada 2

### Camada 2 — Fonético com Blocking

- **Blocking fonético**: índice por prefixo Metaphone (4 chars) + vizinhos com edit distance ≤ 1
- **Blocking por bigramas**: índice invertido (bigrama → marcas) — Jaccard ≥ 0.30
- Para candidatos encontrados: calcula Jaro-Winkler + bigramas
- Threshold: **0.72** (configurável via env `THRESHOLD_FONETICO`)
- **Performance**: índice invertido reduz de O(n×m) para O(|bigramas_rpi|)

### Camada 3 — Afinidade de Especificação

- **TF-IDF** em batch sobre especificações (1 fit por execução)
- Cosine similarity entre especificações em chunks de 5k
- Bônus de classe: +0.15 (mesma NCL), +0.10 (NCL colidentes)
- Threshold: **0.40** (configurável via `THRESHOLD_ESPECIFICACAO`)

### Camada 4 — Score Composto

```
score = (score_nome   × 0.35) +
        (score_spec   × 0.25) +
        (score_nucleo × 0.15) +
        (score_fon    × 0.10) +
        (tipo_marca   × 0.10) +
        (bonus_classe × 0.05)
```

**Ajustes por tipo de marca:**
- `is_marca_generica`: reduz peso do nome (−0.10), aumenta peso da spec (+0.10)
- `is_sigla`: zera fonético, aumenta peso do nome (+0.10), tipo_marca = 0.5

**Bônus de classe:**
- Mesma NCL: +0.8
- NCLs colidentes: +0.5
- Sem relação: 0.0

**Gates de filtro:**
1. `s_nome < 0.72 AND s_nucleo < 0.82` → descarta (nome e núcleo fracos)
2. Ambos genéricos: só passa se `s_nome ≥ 0.92` OU (mesma NCL + `s_nucleo ≥ 0.95`)
3. Cross-class sem colisão: penalidade multiplicativa pela força distintiva dos núcleos

**Threshold final:** 0.55–0.60 (ajustado para classes de saúde: ×0.85)

### Classificação Final

| Score | Classificação |
|---|---|
| ≥ 0.80 | **ALTA** |
| ≥ 0.65 | **MÉDIA** |
| ≥ 0.55 | **BAIXA** |
| < 0.55 | Descartado |

---

## 7. Padrões de Colidência Identificados

Baseado na análise de 1.377 pares validados por especialistas humanos (RPIs 2879, 2882, 2883):

### 7.1 Tipos de Similaridade Observados

| Tipo | Exemplo | Frequência |
|---|---|---|
| **Nome idêntico** | ATIVA × ATIVA | ~15% |
| **Variação gráfica mínima** | JOLLI × JOLY, PARFF × PARF | ~20% |
| **Imitação fonética** | CAVALINHO × KAVALLO | ~25% |
| **Abreviação/extensão** | PK SUPLEMENTOS × PKY SUPLEMENTOS | ~15% |
| **Marca contida** | LEGACY × HOGWARTS LEGACY | ~10% |
| **Variação ortográfica** | MAGNASTORE × MAGNA STORE | ~10% |
| **Raiz comum** | +COR × KOR, #TDD × TD | ~5% |

### 7.2 Distribuição por Tipo de Ação

| Tipo | Proporção | Prazo |
|---|---|---|
| OPOSIÇÃO | ~53% | 60 dias |
| PAN | ~47% | 180 dias |

### 7.3 Distribuição por Classe

- ~70% dos pares envolvem **classes diferentes** (cross-class)
- ~30% são da **mesma classe**
- Classe 35 (serviços comerciais) é a mais frequente (~28% dos alertas)
- Cross-class mais comum: 40×35, 35×25, 40×43

### 7.4 Similaridade dos Nomes nos Pares Validados

| Faixa | % dos pares aprovados |
|---|---|
| 0.0 – 0.3 | ~8% (casos especiais: marca contida, sigla) |
| 0.3 – 0.6 | ~36% |
| 0.6 – 0.9 | ~38% |
| 0.9 – 1.0 | ~18% (idêntico ou quase) |

> **Implicação**: especialistas aprovam pares com similaridade baixa quando há outros fatores (mesma classe, atividade idêntica, marca famosa). O algoritmo prioriza casos com score ≥ 0.60.

---

## 8. Falsos Positivos — O que Descartar

### 8.1 "Marcas de Padrão" (Nomes Genéricos)

Pares onde ambos têm nomes compostos exclusivamente por elementos desgastados:
- `SUPER MERCADO PRIME` × `MEGA MERCADO PRIME` → **descartar**
- `TECH HOUSE SOLUTIONS` × `DIGITAL HOUSE EXPRESS` → **descartar**
- `SUPER` × `MEGA` (núcleos diferentes, ambos desgastados) → **descartar**

**Gate implementado**: ambos genéricos + s_nome < 0.92 + não mesma NCL → descartado.

### 8.2 Núcleo Minúsculo

- `A PLUS VIAGENS` sem o gate → núcleo `"a"` (1 char) → matches espúrios
- **Correção**: núcleo com < 3 chars → usar nome normalizado completo

### 8.3 Cross-class Sem Afinidade

- Marcas frágeis (desgastadas) em classes completamente distintas
- Ex: `REAL` (classe 1 — química) × `REAL` (classe 44 — beleza) → penalidade ×0.25

---

## 9. Formato do Relatório Final

### 9.1 Aba "Relatório" — Entrega ao Cliente

| Coluna | Conteúdo |
|---|---|
| PROCESSO CLIENTE | Número INPI da marca do cliente |
| MARCA CLIENTE | Nome da marca protegida |
| CLASSE CLIENTE | `NCL(versão) classe` (ex: NCL(12) 35) |
| TITULAR CLIENTE | Proprietário da marca |
| PROCESSO TERCEIRO | Número INPI da marca conflitante |
| MARCA TERCEIRO | Nome da marca conflitante |
| CLASSE TERCEIRO | `NCL(12) classe` |
| TIPO DESPACHO | **OPOSIÇÃO** ou **PAN** |
| PRAZO DESPACHO | Data limite calculada automaticamente |
| DESC. DESPACHO | Texto do despacho INPI |

**Codificação por cor:**
- 🔴 Vermelho claro: OPOSIÇÃO (urgente — 60 dias)
- 🟡 Amarelo claro: PAN (180 dias)

### 9.2 Aba "Análise Técnica" — Uso Interno

Contém todos os scores: `score_nome`, `score_fonetico`, `score_spec`, `score_nucleo`, `score_ia`, `camada_deteccao`, núcleos extraídos, flags de sigla/desgastado.

### 9.3 Aba "Resumo" — Estatísticas

Volumes por tipo de ação, por classificação (ALTA/MÉDIA/BAIXA), por camada do pipeline.

---

## 10. Cálculo de Prazos

```
Data da RPI: 10/03/2026

OPOSIÇÃO → prazo: 10/03/2026 + 60 dias = 09/05/2026
PAN      → prazo: 10/03/2026 + 180 dias = 07/09/2026
```

> Os prazos são **corridos** (dias calendário), não úteis.

---

## 11. Prompt Recomendado para Análise pela IA

Quando enviar o relatório para o Claude fazer a análise jurídica final:

```
Você é um especialista em propriedade intelectual e direito de marcas brasileiro.

Vou te enviar um relatório de colidência de marcas gerado pelo sistema ColidencIA.
Cada linha representa um possível conflito entre uma marca do cliente (MARCA CLIENTE)
e uma marca de terceiro (MARCA TERCEIRO) publicada na RPI do INPI.

Para cada par, analise:

1. **SEMELHANÇA** — os nomes são semelhantes? Considere:
   - Semelhança gráfica (visual)
   - Semelhança fonética (som)
   - Semelhança ideológica (conceito/significado)

2. **AFINIDADE MERCADOLÓGICA** — as atividades colidem?
   - Compare CLASSE CLIENTE × CLASSE TERCEIRO
   - Considere se os produtos/serviços concorrem ou se complementam

3. **RISCO DE CONFUSÃO** — o consumidor médio poderia confundir as marcas?

4. **RECOMENDAÇÃO** — para cada par:
   - ✅ ACIONAR: recomendar oposição/PAN ao cliente
   - ⚠️ MONITORAR: conflito baixo, manter atenção
   - ❌ DESCARTAR: sem risco real de confusão

Agrupe os casos por urgência:
- 🔴 OPOSIÇÃO com prazo próximo (verificar PRAZO DESPACHO)
- 🟡 PAN com prazo em andamento
```

---

## 12. Métricas de Desempenho

| RPI | Marcas verificadas | Carteira | Alertas gerados | Meta |
|---|---|---|---|---|
| 2879 (10/03/2026) | 15.397 | 24.999 | 595 | < 1.000 |
| 2882 (31/03/2026) | 13.056 | 24.999 | 387 | < 1.000 |
| 2883 (07/04/2026) | 15.834 | 21.609 | 395 | < 1.000 |
| Sistema anterior | ~13.000 | 49.000 | **101.791** | reduzir |

**Meta de calibração**: 5.000–15.000 alertas por RPI (volume manejável para revisão humana + IA).

---

## 13. Configurações Chave

| Parâmetro | Valor padrão | Descrição |
|---|---|---|
| `THRESHOLD_FONETICO` | 0.72 | Score mínimo na Camada 2 |
| `THRESHOLD_ESPECIFICACAO` | 0.40 | Score mínimo na Camada 3 |
| `THRESHOLD_SCORE_FINAL` | 0.60 | Score mínimo para alerta |
| `FATOR_CAUTELA` | 0.85 | Multiplicador para classes de saúde (5, 10, 44) |
| `BATCH_SIZE_IA` | 50 | Pares por chamada à IA |
| `MAX_PARES_IA` | 15.000 | Limite de pares para análise por IA |

---

*Gerado em 14/05/2026 — Sistema ColidencIA*
