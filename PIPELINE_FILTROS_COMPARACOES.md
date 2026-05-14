# Pipeline de Colidência — Filtros e Comparações

## Visão Geral

```
Carteira (Excel) ──┐
                   ├─► Camada 0: Pré-processamento
RPI (XML) ─────────┘
                       │
                       ▼
               Camada 1: Nome Idêntico  ──► alertas automáticos (ALTA)
                       │ (rpi_restante)
                       ▼
               Camada 2: Filtro Fonético ──► candidatos
                       │
                       ▼
               Camada 3: Filtro de Especificação
                       │
                       ▼
               Camada 4: Scoring Composto ──► aprovados
                       │
                       ▼
               Camada 5: Refinamento IA (GPT-4o-mini)
                       │
                       ▼
               Deduplicação + Ordenação → Relatório
```

---

## Camada 0 — Pré-processamento

Aplicado a **cada marca** da carteira e da RPI antes de qualquer comparação.

### Campos gerados

| Campo | Origem | Descrição |
|-------|--------|-----------|
| `nome_normalizado` | `normalizar_base(marca)` | Lowercase, sem acentos, sem pontuação |
| `nucleo` | `extrair_nucleo(marca)` | Tokens antes do primeiro stopword ou complemento descritivo |
| `codigo_fonetico` | `metaphone_ptbr(nome_normalizado)` | Código fonético PT-BR |
| `bigrams_set` | `bigramas(marca)` | Conjunto de bigramas de caracteres |
| `is_sigla` | `len(norm) ≤ 4 e isalpha()` | True se a marca é uma sigla |
| `is_nome_proprio` | ≥ 2 tokens com inicial maiúscula | Heurística de nome próprio |
| `is_marca_generica` | ver regra abaixo | True se o núcleo é majoritariamente desgastado |
| `is_desgastado` | qualquer token em `ELEMENTOS_DESGASTADOS` | Marca com elemento de baixa distintividade |

### Extração do núcleo marcário

```
"INSPIRE STUDIO DE PILATES"  →  "INSPIRE"
"CAVALINHO AZUL"             →  "CAVALINHO AZUL"
"SUPER MARKET PLUS"          →  "SUPER"  (mas is_marca_generica = True)
```

- Itera tokens do nome normalizado
- Para ao encontrar token em `_STOPWORDS` (de, do, ltda, me, grupo…) ou em `COMPLEMENTOS_DESCRITIVOS` (~55 termos: studio, store, shop, clinica, academy, digital, express, premium…)
- **Regra de segurança:** se o núcleo extraído tem menos de 3 caracteres, retorna o nome completo

### Regra `is_marca_generica`

```
Todos os tokens do núcleo são desgastados          → True
≥ 3 tokens e ≥ 2/3 são desgastados                → True
≤ 2 tokens e pelo menos 1 é desgastado             → True
Caso contrário                                      → False
```

`ELEMENTOS_DESGASTADOS` (~120 termos em 12 categorias): super, mega, ultra, prime, premium, gold, smart, tech, eco, bio, green, brasil, nova, novo, life, star, king, power, energy, alfa, beta, delta, omega, e outros.

---

## Camada 1 — Nome Idêntico

**Objetivo:** detectar colidências óbvias com score = 1.0 antes do processamento pesado.

### Índices construídos

- **Por hash do nome:** `normalizar_para_hash(nome_normalizado)` → lista de marcas da carteira
- **Por hash do núcleo:** `normalizar_para_hash(nucleo)` → lista de marcas da carteira

### Comparações

| Condição | Resultado |
|----------|-----------|
| `hash(nome_rpi) == hash(nome_carteira)` | Alerta automático `score_nome=1.0, score_nucleo=1.0, classificação=ALTA` |
| `hash(nucleo_rpi) == hash(nucleo_carteira)` *(e não detectado antes)* | Alerta com `score_nome=0.85, score_nucleo=1.0`, classes verificadas |

### Saída

- **alertas_c1:** pares com colidência automática, classificação ALTA
- **rpi_restante:** marcas da RPI que não tiveram match — seguem para Camada 2

---

## Camada 2 — Filtro Fonético (Blocking)

**Objetivo:** reduzir o espaço de comparação de O(N×M) para O(k×M) usando blocking.

### Índice fonético da carteira

- Chave: primeiros 4 caracteres do `codigo_fonetico` (Metaphone PT-BR)
- Exemplo: "NEOX" → código "NKS" → bucket "NKS"

### Estratégias de blocking (OR)

**2A — Bucket fonético exato + vizinhos com edit distance ≤ 1 no prefixo**
```
Se codigo_rpi[:4] == codigo_carteira[:4]  →  candidato
Se levenshtein(codigo_rpi[:4], bucket[:4]) ≤ 1  →  candidato
```

**2B — Jaccard de bigramas ≥ 0.30**
```
|bigrams_rpi ∩ bigrams_carteira| / |bigrams_rpi ∪ bigrams_carteira| ≥ 0.30
```

### Scores calculados por par

Usando `similaridade_par(nome_a, nucleo_a, nome_b, nucleo_b)`:

| Score | Cálculo | Valor |
|-------|---------|-------|
| `score_nome` | `max(jaro_winkler, token_sort_ratio, jaccard_bigramas)` | 0.0–1.0 |
| `score_fonetico` | `fuzz.ratio(metaphone_a, metaphone_b) / 100` | 0.0–1.0 |
| `score_nucleo` | `max(similaridade_nome(nucleo_a, nucleo_b), similaridade_fonetica(nucleo_a, nucleo_b))` | 0.0–1.0 |

### Threshold de passagem

```
score_fonetico >= THRESHOLD_FONETICO (0.70)
```

Pares abaixo do threshold são descartados. Os demais seguem para Camada 3.

---

## Camada 3 — Filtro de Especificação/Afinidade

**Objetivo:** eliminar pares fonética/nominalmente similares mas de setores incompatíveis.

### Três estratégias (score_spec = máximo das três)

**3A — Tabela de correlatas** (`especificacoes_correlatas.csv`)
```
score_3a = correlatas.get((ncl_base, ncl_rpi), 0.0)
```
Valores pré-calibrados de afinidade para pares de classes específicos.

**3B — Matriz de classes colidentes**
```
ncl_a == ncl_b          → 0.80
ncl_b ∈ COLLISIONS[ncl_a] → 0.70
caso contrário           → 0.00
```
Matriz COLLISIONS: 45 classes × 45 classes, bidirecional (ex: classe 35 colide com 9, 16, 25, 29, 30, 34, 36, 38, 39, 40, 41, 42, 43, 44, 45).

**3C — TF-IDF cosine similarity**
```
TfidfVectorizer(ngram_range=(1,2), min_df=1)
score_3c = cosine_similarity(tfidf[spec_base], tfidf[spec_rpi])
```
Compara os textos completos das especificações NCL.

### Threshold de passagem

```
score_spec = max(sc_3a, sc_3b, sc_3c) >= THRESHOLD_ESPECIFICACAO (0.40)
```

Pares abaixo do threshold são descartados.

---

## Camada 4 — Scoring Composto

**Objetivo:** calcular um score final ponderado e aplicar gates de qualidade.

### Fórmula do score

```
score = (
    score_nome     × PESO_SIMILARIDADE_NOME  (0.35)  [0.25 se marca genérica]
    score_spec     × PESO_AFINIDADE_SPEC     (0.25)  [0.35 se marca genérica]
    score_nucleo   × PESO_NUCLEO_MARCARIO    (0.15)
    score_fonetico × PESO_FONETICA           (0.10)  [0.00 se sigla]
    tipo_marca     × PESO_TIPO_MARCA         (0.10)
    bonus_classe   × PESO_BONUS              (0.05)
)
score = min(1.0, score)
```

**`tipo_marca`:**
- Sigla → 0.50 (peso neutro)
- Padrão → 0.70

**`bonus_classe`:**
- `ncl_a == ncl_b` → 0.80
- `ncl_b ∈ COLLISIONS[ncl_a]` → 0.50
- Classes não colidentes → 0.00

### Gates de eliminação (aplicados após o score)

**Gate 1 — Similaridade mínima**
```
se score_nome < 0.72 AND score_nucleo < 0.82 → descartar
```
Elimina pares onde só a classe ou o bônus sustenta o score, mas os nomes são muito distintos.

**Gate 2 — Ambos genéricos**
```
se nucleo_base_generico AND nucleo_rpi_generico:
    se score_nome < 0.92 AND NOT (ncl_a == ncl_b AND score_nucleo >= 0.95):
        → descartar
```
Elimina pares tipo SUPER MERCADO × MEGA MERCADO onde ambas as marcas são fracas.

**Gate 3 — Penalidade cross-class**
```
se NOT classes_colidem AND ncl_a != ncl_b:
    fator = distintividade(nucleo_base) × distintividade(nucleo_rpi)
    score = score × fator
```
`_fator_distintividade(nucleo)` = 0.3–1.0 com base na proporção de tokens desgastados no núcleo. Marcas fracas em classes distintas sofrem penalidade multiplicativa.

### Overrides de score mínimo

| Condição | Score mínimo aplicado |
|----------|-----------------------|
| Nome idêntico (camada 1) | `max(score, 0.85)` |
| Núcleo idêntico (`score_nucleo ≥ 0.99`) | `max(score, 0.70)` |

### Threshold e cautela

```
threshold = THRESHOLD_SCORE_FINAL (0.55)

# Classes de saúde (5, 10, 44) têm threshold reduzido
se ncl_a ∈ {5, 10, 44} OU ncl_b ∈ {5, 10, 44}:
    threshold = 0.55 × FATOR_CAUTELA (0.85) = 0.4675
```

### Classificação final

| Score | Classificação |
|-------|---------------|
| ≥ 0.80 | ALTA |
| ≥ 0.65 | MEDIA |
| ≥ 0.55 | BAIXA |
| < 0.55 | NENHUMA (descartado) |

---

## Camada 5 — Refinamento IA (GPT-4o-mini)

**Objetivo:** validação jurídico-marcária dos pares aprovados pelas camadas anteriores.

### Condições de ativação

- `OPENAI_API_KEY` configurada
- Máximo de `MAX_PARES_IA = 15.000` pares processados
- Budget máximo de `BUDGET_SEMANAL_USD = US$18,00`

### Prompt enviado por par

```
Marca BASE: "[nome]" (NCL X) Núcleo: "[nucleo]"
Especificação BASE: [primeiros 200 chars]

Marca RPI: "[nome]" (NCL Y) Núcleo: "[nucleo]"
Especificação RPI: [primeiros 200 chars]

Scores pré-calculados — nome: X.XX, fonético: X.XX, spec: X.XX, núcleo: X.XX
```

### Critérios aplicados pela IA (Art. 124, XIX LPI 9.279/96)

1. **Reprodução/imitação:** aspecto gráfico, fonético e ideológico
2. **Elemento principal:** foco no núcleo, não nos complementos
3. **Afinidade mercadológica:** natureza, finalidade, canais, público
4. **Regra inversa:** menos semelhança de sinais exige mais afinidade
5. **Exceções:** elementos desgastados (analisar conjunto), siglas (só gráfico), marcas genéricas

### Saída da IA

```json
{
  "classificacao": "ALTA|MEDIA|BAIXA|NENHUMA",
  "score": 0.0-1.0,
  "justificativa": "máx. 80 palavras",
  "aspecto_grafico": 0.0-1.0,
  "aspecto_fonetico": 0.0-1.0,
  "aspecto_ideologico": 0.0-1.0,
  "afinidade_mercadologica": 0.0-1.0
}
```

### Score final pós-IA

```
score_final = 0.60 × score_ia + 0.40 × score_c4
```

Pares classificados como `NENHUMA` pela IA são removidos na etapa de pós-processamento.

### Processamento em batch

- Batches de 50 pares
- 5 requisições paralelas por vez (asyncio)
- Modelo: `gpt-4o-mini`, `temperature=0.1`, `max_tokens=200`

---

## Pós-processamento

```
1. Remover classificação "NENHUMA"
2. Ordenar por score_final DESC
3. Deduplicar por (marca_base, ncl_base, marca_rpi, ncl_rpi) — manter maior score
```

---

## Resumo de Thresholds

| Parâmetro | Valor | Onde |
|-----------|-------|------|
| `THRESHOLD_FONETICO` | 0.70 | Camada 2: score fonético mínimo para candidato |
| `THRESHOLD_ESPECIFICACAO` | 0.40 | Camada 3: afinidade de spec mínima |
| `THRESHOLD_SCORE_FINAL` | 0.55 | Camada 4: score composto mínimo |
| Gate nome+núcleo mínimo | 0.72 / 0.82 | Camada 4: ao menos um deve ser alto |
| Gate ambos genéricos | 0.92 / 0.95 | Camada 4: nomes quase idênticos obrigatório |
| Classes saúde (5, 10, 44) | threshold × 0.85 | Camada 4: cautela extra |
| Override nome idêntico | score ≥ 0.85 | Camada 4 |
| Override núcleo idêntico | score ≥ 0.70 | Camada 4 |
| Peso IA no score final | 60% IA + 40% C4 | Camada 5 |
