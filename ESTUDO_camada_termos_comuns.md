# Estudo — Camada de Termos Comuns / Distintividade

> Status: **estudo/design** (não implementado). Para execução na sessão Sonnet.
> Base empírica: RPI 2886 (22.796 marcas) + base cliente (1.085 marcas).

---

## 1. O problema, com precisão

A "colidência" de marca compostas se decide pelo **elemento distintivo**, não pelo
complemento descritivo. O motor atual erra porque trata o nome como um bloco e/ou
depende de uma **lista estática** de termos genéricos que:

1. **Nunca está completa** — sempre falta termo (regional, setor novo, gíria).
2. **É binária** — "genérico ou não", mas genericidade é um *espectro de frequência*.
3. **É cega ao contexto/classe** — `ENERGIA` é descritivo na classe 39/40, mas
   distintivo numa padaria. `SOL` idem.
4. **Exige curadoria manual** — não escala, não aprende.

Casos reais que quebram a lista estática (medidos):

| Par | Núcleo real | Por que colide hoje (errado) |
|-----|-------------|------------------------------|
| ACT CONTABILIDADE × ROTA CONTABILIDADE | ACT × ROTA | "CONTABILIDADE" idêntico infla score |
| AOCT × AEROCAR CORRETORA DE SEGUROS | AOCT × AEROCAR | "CORRETORA DE SEGUROS" idêntico |
| JP × PAULINHO PNEUS AUTO CENTER | JP × PAULINHO | "PNEUS AUTO CENTER" idêntico |

---

## 2. O que os dados dizem (medição real)

Construí a tabela de frequência de tokens da RPI 2886 (script `_estudo_distintividade.py`).

### 2.1 IDF global puro com 1 RPI é **insuficiente**

O token mais comum (`BRASIL`, 162 marcas) só chega a `dist_global = 0.49`. Tudo se
comprime entre 0.49 e 1.0 — separação fraca:

```
CONTABILIDADE  → 0.63     EDIPHARMA → 1.00
SEGUROS        → 0.60     AOCT      → 1.00
RESTAURANTE    → 0.65     NIU       → 1.00
```

A **ordem está certa** (genéricos embaixo, distintivos no topo), mas o limiar de
corte é instável com uma única RPI.

### 2.2 Frequência **por classe** (contagem crua) é o melhor sinal

```
CORRETORA   → aparece em 27 das marcas da classe 36
SEGUROS     → 45 da classe 36
RESTAURANTE → 27 da classe 43
CONTABILIDADE → 35 da classe 35
```

Um token que aparece em **dezenas de marcas da mesma classe** é descritivo *para
aquela classe* — sinal direto e interpretável, melhor que IDF global.

### 2.3 A lista estática cobre a "cauda longa"; o corpus cobre o "topo"

- **511** dos 737 termos da lista **não são frequentes** nesta RPI → são descritores
  válidos de setores pouco representados aqui (PSICANALISE, CROSSFIT…). Só a lista
  curada cobre isso.
- O corpus pega o que a lista esquece: `CAFE` (93 marcas!), `METODO` (75), `BEAUTY`
  (63), `STORE` (58), `AUTO` (53), `CLUB` (51), `CENTER` (19), `ROTA` (27) — todos
  **ausentes** da lista hoje. Além de stopwords vazadas (`SEU`, `BEM`, `QUE`).

**Conclusão central:** lista *ou* corpus isolados falham. **Híbrido** é a resposta —
e a peça que torna o sistema robusto independentemente da completude da lista é
deixar de usar uma lista binária e passar a usar **peso de distintividade contínuo
por token**, com a comparação ponderada por esse peso.

---

## 3. Arquitetura recomendada — Camada de Distintividade

Substituir o conceito "lista de termos comuns" por uma **camada que atribui a cada
token um peso de distintividade `w ∈ [0,1]`** (0 = genérico, 1 = distintivo) e faz a
similaridade ser **ponderada** por esse peso.

```
 Token "CONTABILIDADE"  → w ≈ 0.15   (genérico: lista + 35 marcas na classe)
 Token "ACT"            → w ≈ 1.00   (distintivo: inédito no corpus)
 → similaridade do par "ACT CONTAB." × "ROTA CONTAB." é dominada por ACT×ROTA (baixa)
```

### 3.1 Componentes

```
data/term_common.py      (já existe, 737 termos) → SEMENTE / override manual
data/corpus_freq.json    (NOVO) → frequências acumuladas por classe, persistidas
engine/corpus.py         (NOVO) → constrói/atualiza/lê corpus_freq.json
engine/distinctiveness.py(NOVO) → w(token, classe) combinando semente + corpus
engine/similarity.py     (alterar) → weighted_similarity(a, b, classe)
engine/rules.py          (alterar) → usa score ponderado + override de conjunto + spec gate
```

### 3.2 Cálculo do peso `w(token, classe)`

```python
def w(token, classe):
    if token in CAT_3_ESTRUTURAIS:        # DE, DA, LTDA…
        return 0.0
    w_semente = 0.15 if token in (CAT_1 | CAT_2) else 1.0
    # sinal do corpus: frequência relativa na classe
    fr = df_classe[classe][token] / max(1, N_classe[classe])
    if df_classe[classe][token] >= 10 or fr > 0.005:
        w_corpus = 0.20
    else:
        w_corpus = 1.0
    return min(w_semente, w_corpus)        # qualquer sinal de genérico rebaixa
```

### 3.3 Similaridade ponderada (resolve a inflação por complemento)

Alinhar os tokens das duas marcas; cada par casado contribui proporcional ao **peso
do par** (max dos dois pesos). Tokens genéricos pesam ~0:

```
score_ponderado = Σ (sim(tok_a, tok_b) · w_par)  /  Σ w_par
```

- `ACT CONTABILIDADE × ROTA CONTABILIDADE`: CONTABILIDADE casa mas w≈0.15; ACT×ROTA
  w≈1.0 mas sim≈0.3 → **score baixo → NÃO colide**. ✔
- `EDIPHARMA × EDITH FARMA`: ambos distintivos, similares → **score alto → colide**. ✔

### 3.4 Override de conjunto (preserva o princípio do conjunto marcário)

Marcas 100% formadas por termos comuns ainda colidem se o **conjunto inteiro** for
quase idêntico — exigência do INPI (análise do conjunto):

```
if similaridade_bruta_nome_completo >= 0.90:
    → colide  (ex.: "CHINES É FÁCIL" × "CHINES MUITO FÁCIL")
score_final = max(score_ponderado, conjunto_override)
```

### 3.5 Portão de especificação (já existe, mantém)

Aplica por cima: specs incompatíveis (<5% overlap) bloqueiam mesmo com nome idêntico.

### 3.6 Corpus acumulativo (auto-aprendizado)

`corpus_freq.json` é **somado a cada RPI processada** (`--update-corpus`). Quanto mais
RPIs, mais robusto o sinal de frequência — o sistema melhora sozinho sem curadoria.
Commitar o JSON ao repo para acumular ao longo do tempo.

---

## 4. Comparação de abordagens

| Critério | A. Lista estática (hoje) | B. Corpus IDF puro | **C. Híbrido (recomendado)** |
|----------|--------------------------|--------------------|------------------------------|
| Completude | Baixa (sempre falta) | Média (1 RPI fraca) | **Alta (lista + corpus)** |
| Contexto/classe | Não | Sim | **Sim** |
| Auto-aprende | Não | Sim | **Sim (acumula RPIs)** |
| Robustez sem lista perfeita | Não | Parcial | **Sim (peso contínuo)** |
| Esforço | — | Médio | **Médio-alto** |
| Conjunto marcário | Quebra | Quebra | **Preserva (override)** |

---

## 5. Plano de implementação (para a sessão Sonnet)

**Fase 1 — Corpus** (`engine/corpus.py` + `data/corpus_freq.json`)
- Função `build_corpus(rpi_records)` → `{classe: {token: df}, _N: {classe: count}}`.
- `update_corpus(path, rpi_records)` soma à base existente e persiste.
- `load_corpus(path)` para uso em runtime.

**Fase 2 — Distintividade** (`engine/distinctiveness.py`)
- `weight(token, classe, corpus)` conforme §3.2 (semente + corpus).
- `distinctive_tokens(marca, classe, corpus)` → lista de (token, peso).

**Fase 3 — Similaridade ponderada** (`engine/similarity.py`)
- `weighted_similarity(a, b, classe, corpus)` conforme §3.3.
- manter `similarity_score` para o override de conjunto (§3.4).

**Fase 4 — Integração** (`engine/rules.py`)
- `check_collision`: `score = max(weighted_sim, conjunto_override)`; aplicar spec gate
  R0; thresholds recalibrados.
- `run_collision_detection`: carregar corpus uma vez no início.

**Fase 5 — Calibração e validação**
- Reprocessar RPI 2886.
- Validar contra o **conjunto-ouro de 40 casos** (20 ALTO + 20 MÉDIO já analisados):
  os 13 falsos positivos de complemento (AOCT×*, ACT×*, JP PNEUS×*) devem cair;
  os 5 legítimos (EDIPHARMA, AIKA/RAYKA, FAC×UFA EMBALAGENS…) devem permanecer.
- Meta: ALTO_RISCO ≈ 100–150 (era 329), com precisão alta.

**Parâmetros a calibrar** (começar aqui):
- limiar genérico por classe: `df_classe >= 10` ou `freq > 0.5%`
- peso semente genérico: `0.15`
- peso corpus genérico: `0.20`
- override de conjunto: `0.90`
- threshold final de colidência: `0.70`

---

## 6. Resumo executivo

- Lista estática **não resolve** — é o gargalo atual (confirmado por dados).
- A solução é uma **camada de distintividade com peso contínuo por token**, que
  combina a lista-semente (cauda longa) com frequência de corpus por classe (topo +
  auto-aprendizado), e faz a **similaridade ponderada** ignorar naturalmente o
  complemento descritivo.
- Preserva o **princípio do conjunto** (override) e o **portão de especificação**.
- Implementação em 5 fases; validação contra conjunto-ouro de 40 casos.
