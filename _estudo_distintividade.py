"""
ESTUDO (não altera engine): mede a viabilidade de uma camada de distintividade
baseada em frequência de corpus (IDF por classe Nice) vs lista estática.

Objetivo: descobrir, com dados reais da RPI, qual o "peso de distintividade"
que cada token receberia automaticamente — e se isso resolve os falsos positivos
de termo comum sem depender de lista manual.
"""
import sys, os, re, math
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from collections import defaultdict, Counter
from colisao_rpi.engine.normalize import normalize
from colisao_rpi.data.loader_rpi import load_rpi_records
from colisao_rpi.data.term_common import TODOS_GENERICOS

XML_RPI  = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\RM2886.xml'
XLSX_CLI = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\Relatório_Detalhado_Marcas -18-05-2026 - Total de processos - 46.619.xlsx'

# ---------------------------------------------------------------------------
# 1. Construir tabela de frequência: token -> nº de marcas (global e por classe)
# ---------------------------------------------------------------------------
print('Carregando RPI...')
rpi, _, _ = load_rpi_records(XML_RPI)

df_global   = Counter()         # token -> nº marcas que o contêm (global)
df_classe   = defaultdict(Counter)  # classe -> token -> nº marcas
n_global    = 0
n_classe    = Counter()         # classe -> nº marcas

for r in rpi:
    nome = r['nome']
    classes = r['classes'] or [0]
    tokens = set(t for t in normalize(nome).split() if len(t) >= 3)
    n_global += 1
    for c in set(classes):
        n_classe[c] += 1
        for t in tokens:
            df_classe[c][t] += 1
    for t in tokens:
        df_global[t] += 1

print(f'  {n_global} marcas, {len(df_global)} tokens únicos')

# ---------------------------------------------------------------------------
# 2. Distintividade = IDF normalizado.  weight ~ 0 (genérico) .. 1 (distintivo)
# ---------------------------------------------------------------------------
def dist_global(token):
    df = df_global.get(token, 0)
    if df == 0:
        return 1.0  # token inédito = muito distintivo
    return math.log((n_global + 1) / (df + 1)) / math.log(n_global + 1)

def dist_classe(token, classe):
    df = df_classe[classe].get(token, 0)
    N  = n_classe.get(classe, 1)
    if df == 0:
        return 1.0
    return math.log((N + 1) / (df + 1)) / math.log(N + 1)

# ---------------------------------------------------------------------------
# 3. Mostrar os tokens MAIS genéricos por frequência global
# ---------------------------------------------------------------------------
print('\n=== TOP 40 TOKENS MAIS FREQUENTES (candidatos a genérico automático) ===')
print(f'{"TOKEN":<22}{"freq":>6}{"% marcas":>10}{"dist_global":>13}{"na_lista?":>11}')
for tok, freq in df_global.most_common(40):
    pct = freq / n_global * 100
    w   = dist_global(tok)
    na_lista = 'SIM' if tok in TODOS_GENERICOS else '--- FALTA'
    print(f'{tok:<22}{freq:>6}{pct:>9.1f}%{w:>13.3f}{na_lista:>11}')

# ---------------------------------------------------------------------------
# 4. Casos problemáticos: peso que cada token receberia
# ---------------------------------------------------------------------------
print('\n=== PESO DE DISTINTIVIDADE NOS CASOS PROBLEMÁTICOS ===')
casos = [
    ('CONTABILIDADE', 35), ('ACT', 35), ('LAMARCA', 35), ('ROTA', 35),
    ('SISTEMAS', 42), ('STAF', 42), ('ALPH', 42),
    ('CORRETORA', 36), ('SEGUROS', 36), ('AOCT', 36), ('AEROCAR', 36),
    ('MODA', 35), ('FEMININA', 35), ('IZZA', 35),
    ('PNEUS', 37), ('CENTER', 37), ('LOGISTICA', 39),
    ('EDIPHARMA', 35), ('AIKA', 35), ('RAYKA', 35),
    ('TECNOLOGIA', 35), ('VELTI', 35),
    ('SUSHI', 43), ('RESTAURANTE', 43), ('NIU', 43), ('HIRO', 43),
]
print(f'{"TOKEN":<16}{"classe":>7}{"df_global":>11}{"df_classe":>11}{"dist_glob":>11}{"dist_cl":>9}{"  lista?"}')
for tok, cl in casos:
    dg = df_global.get(tok, 0)
    dc = df_classe[cl].get(tok, 0)
    wg = dist_global(tok)
    wc = dist_classe(tok, cl)
    na = 'SIM' if tok in TODOS_GENERICOS else 'FALTA'
    print(f'{tok:<16}{cl:>7}{dg:>11}{dc:>11}{wg:>11.3f}{wc:>9.3f}{"  "+na}')

# ---------------------------------------------------------------------------
# 5. Quanto da lista estática o corpus reproduziria automaticamente?
# ---------------------------------------------------------------------------
print('\n=== COBERTURA: lista estática vs corpus ===')
# tokens da lista que aparecem com alta freq no corpus (corpus os "confirma")
LIMIAR_GENERICO = 0.6  # dist_global < 0.6 => corpus considera genérico
na_lista_e_corpus = 0
na_lista_nao_corpus = 0
for tok in TODOS_GENERICOS:
    if df_global.get(tok, 0) > 0:
        if dist_global(tok) < LIMIAR_GENERICO:
            na_lista_e_corpus += 1
        else:
            na_lista_nao_corpus += 1
fora_lista_mas_generico = [
    tok for tok, f in df_global.items()
    if dist_global(tok) < 0.45 and tok not in TODOS_GENERICOS and len(tok) >= 4
]
print(f'Termos da lista confirmados pelo corpus (dist<{LIMIAR_GENERICO}): {na_lista_e_corpus}')
print(f'Termos da lista NÃO frequentes no corpus:                      {na_lista_nao_corpus}')
print(f'Termos genéricos detectados pelo corpus FORA da lista:         {len(fora_lista_mas_generico)}')
print(f'\nExemplos de genéricos que a lista NÃO tem mas o corpus pega:')
for tok in sorted(fora_lista_mas_generico, key=lambda t: -df_global[t])[:30]:
    print(f'   {tok:<22} ({df_global[tok]} marcas, dist={dist_global(tok):.2f})')
