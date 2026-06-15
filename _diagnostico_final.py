"""
Diagnóstico aprofundado: consistência dos vereditos, camadas ajustáveis,
e quantos casos a IA realmente enviaria ao advogado.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from collections import Counter
from colisao_rpi.engine.rules import _spec_overlap
from colisao_rpi.engine.similarity import similarity_score
from colisao_rpi.engine.nucleus import extract_nucleus

df = pd.read_excel('./relatorio_v3/Relatorio_Analisado_IA_v3_RPI2886.xlsx')

total = len(df)
print(f'Total de casos: {total}\n')

# -----------------------------------------------------------------------
# 1. CONSISTÊNCIA: o veredito da IA está alinhado com o score?
# -----------------------------------------------------------------------
print('='*70)
print('1. CONSISTÊNCIA DOS VEREDITOS')
print('='*70)

def score_num(v):
    try: return float(v)
    except: return -1.0

df['SCORE_SPEC_N'] = df['SCORE_SPEC'].apply(score_num)

for verd in ['ALTO_RISCO','MEDIO_RISCO','BAIXO_RISCO','FALSO_POSITIVO']:
    sub = df[df['VEREDITO'] == verd]
    if len(sub) == 0: continue
    sn_med = sub['SCORE_NOME'].mean()
    sn_min = sub['SCORE_NOME'].min()
    sn_max = sub['SCORE_NOME'].max()
    ss_med = sub[sub['SCORE_SPEC_N']>=0]['SCORE_SPEC_N'].mean() if (sub['SCORE_SPEC_N']>=0).any() else -1
    mc = (sub['CLASSE CLIENTE'].str.extract(r'(\d+)$')[0] ==
          sub['CLASSE TERCEIRO'].str.extract(r'(\d+),?')[0]).mean()
    print(f'\n  {verd} ({len(sub)} casos):')
    print(f'    Score nome  → min={sn_min:.3f}  med={sn_med:.3f}  max={sn_max:.3f}')
    print(f'    Score spec  → med={ss_med:.3f}' if ss_med>=0 else '    Score spec  → N/D')
    print(f'    Mesma classe → {mc:.0%} dos casos')

# -----------------------------------------------------------------------
# 2. CASOS INCONSISTENTES (score alto mas veredito baixo ou vice-versa)
# -----------------------------------------------------------------------
print()
print('='*70)
print('2. CASOS INCONSISTENTES (possíveis erros de classificação)')
print('='*70)

# Alto risco com spec baixa (deveria ser médio?)
prob_alto = df[
    (df['VEREDITO']=='ALTO_RISCO') &
    (df['SCORE_SPEC_N'] >= 0) &
    (df['SCORE_SPEC_N'] < 0.05)
]
print(f'\n  ALTO_RISCO com spec incompatível (candidatos a rebaixar): {len(prob_alto)}')
for _, r in prob_alto.head(5).iterrows():
    print(f'    [{r["SCORE_NOME"]:.3f} spec={r["SCORE_SPEC"]}]  {r["MARCA CLIENTE"]!r:35} x {r["MARCA TERCEIRO"]!r}')
    print(f'      CLI: {str(r["ESPEC_CLIENTE"])[:80]}')
    print(f'      RPI: {str(r["ESPEC_TERCEIRO"])[:80]}')

# Médio risco com score nome alto (deveria ser alto?)
prob_medio = df[
    (df['VEREDITO']=='MEDIO_RISCO') &
    (df['SCORE_NOME'] >= 0.90) &
    (df['SCORE_SPEC_N'] >= 0.30)
]
print(f'\n  MEDIO_RISCO com nome>=0.90 e spec>=0.30 (candidatos a elevar): {len(prob_medio)}')
for _, r in prob_medio.head(5).iterrows():
    print(f'    [{r["SCORE_NOME"]:.3f} spec={r["SCORE_SPEC"]}]  {r["MARCA CLIENTE"]!r:35} x {r["MARCA TERCEIRO"]!r}')

# Baixo risco com mesma classe e score > 0.75
prob_baixo = df[
    (df['VEREDITO']=='BAIXO_RISCO') &
    (df['SCORE_NOME'] >= 0.75) &
    (df['SCORE_SPEC_N'] >= 0.20)
]
print(f'\n  BAIXO_RISCO com nome>=0.75 e spec>=0.20 (candidatos a revisar): {len(prob_baixo)}')
for _, r in prob_baixo.head(5).iterrows():
    print(f'    [{r["SCORE_NOME"]:.3f} spec={r["SCORE_SPEC"]}]  {r["MARCA CLIENTE"]!r:35} x {r["MARCA TERCEIRO"]!r}')

# -----------------------------------------------------------------------
# 3. CAMADAS AJUSTÁVEIS E IMPACTO
# -----------------------------------------------------------------------
print()
print('='*70)
print('3. CAMADAS AJUSTÁVEIS E IMPACTO ESTIMADO')
print('='*70)

# Camada A: BAIXO_RISCO com score < 0.65 e sem spec → descartáveis
camada_a = df[
    (df['VEREDITO']=='BAIXO_RISCO') &
    (df['SCORE_NOME'] < 0.65) &
    (df['SCORE_SPEC_N'] < 0)   # sem spec
]
print(f'\n  [CAMADA A] BAIXO_RISCO + score<0.65 + sem spec → descartar')
print(f'    Impacto: -{len(camada_a)} casos ({len(camada_a)/total*100:.1f}%)')

# Camada B: BAIXO_RISCO com spec incompatível (<0.05)
camada_b = df[
    (df['VEREDITO']=='BAIXO_RISCO') &
    (df['SCORE_SPEC_N'] >= 0) &
    (df['SCORE_SPEC_N'] < 0.05)
]
print(f'\n  [CAMADA B] BAIXO_RISCO + spec incompatível → descartar')
print(f'    Impacto: -{len(camada_b)} casos ({len(camada_b)/total*100:.1f}%)')

# Camada C: FALSO_POSITIVO total
camada_c = df[df['VEREDITO']=='FALSO_POSITIVO']
print(f'\n  [CAMADA C] FALSO_POSITIVO → descartar')
print(f'    Impacto: -{len(camada_c)} casos ({len(camada_c)/total*100:.1f}%)')

# Camada D: BAIXO_RISCO com classes correlatas (não mesma) e score < 0.70
def get_cl(s):
    m = re.search(r'NCL\(13\)\s*(\d+)', str(s))
    return int(m.group(1)) if m else 0

df['CL_CLI_N'] = df['CLASSE CLIENTE'].apply(get_cl)
df['CL_3O_N']  = df['CLASSE TERCEIRO'].apply(get_cl)

camada_d = df[
    (df['VEREDITO']=='BAIXO_RISCO') &
    (df['CL_CLI_N'] != df['CL_3O_N']) &
    (df['SCORE_NOME'] < 0.70)
]
print(f'\n  [CAMADA D] BAIXO_RISCO + classes correlatas (≠) + score<0.70 → descartar')
print(f'    Impacto: -{len(camada_d)} casos ({len(camada_d)/total*100:.1f}%)')

# União das camadas descartáveis (sem duplicata)
idx_descartar = set(camada_a.index) | set(camada_b.index) | set(camada_c.index) | set(camada_d.index)
total_descartar = len(idx_descartar)
print(f'\n  TOTAL DESCARTÁVEL (A+B+C+D sem duplicata): -{total_descartar} casos')

# -----------------------------------------------------------------------
# 4. QUANTOS CASOS A IA ENVIARIA?
# -----------------------------------------------------------------------
print()
print('='*70)
print('4. QUANTOS CASOS A IA ENVIARIA AO ADVOGADO?')
print('='*70)

# Cenário atual (sem ajustes adicionais)
enviar_atual = df[df['VEREDITO'].isin(['ALTO_RISCO','MEDIO_RISCO'])]
print(f'\n  CENÁRIO ATUAL (ALTO + MÉDIO):')
print(f'    {len(enviar_atual)} casos  ({len(enviar_atual)/total*100:.1f}% do total)')
print(f'    ALTO_RISCO  : {len(df[df["VEREDITO"]=="ALTO_RISCO"])}')
print(f'    MEDIO_RISCO : {len(df[df["VEREDITO"]=="MEDIO_RISCO"])}')

# Cenário otimizado (aplicar camadas A+B+C+D sobre BAIXO_RISCO, manter ALTO e MÉDIO)
# + rebaixar ALTO com spec < 0.05 para MÉDIO
alto_rebaixar = prob_alto  # ALTO com spec incompatível
medio_elevar  = prob_medio  # MÉDIO com score alto e spec alta

enviar_otimizado_alto  = len(df[df['VEREDITO']=='ALTO_RISCO']) - len(alto_rebaixar) + len(medio_elevar)
enviar_otimizado_medio = len(df[df['VEREDITO']=='MEDIO_RISCO']) + len(alto_rebaixar) - len(medio_elevar)
total_otimizado = enviar_otimizado_alto + enviar_otimizado_medio

print(f'\n  CENÁRIO OTIMIZADO (após aplicar camadas A+B+C+D):')
print(f'    {total_otimizado} casos relevantes')
print(f'    ALTO_RISCO  : ~{enviar_otimizado_alto}')
print(f'    MEDIO_RISCO : ~{enviar_otimizado_medio}')
print(f'    Descartados : {total_descartar + len(camada_c)} (BAIXO + FP)')

# Cenário conservador: só ALTO_RISCO
print(f'\n  CENÁRIO CONSERVADOR (só ALTO_RISCO):')
print(f'    {len(df[df["VEREDITO"]=="ALTO_RISCO"])} casos para oposição imediata')

# Por classe — onde se concentram os riscos altos?
print()
print('  ALTO+MÉDIO RISCO POR CLASSE:')
relevantes = df[df['VEREDITO'].isin(['ALTO_RISCO','MEDIO_RISCO'])]
por_classe = relevantes.groupby('CL_CLI_N').size().sort_values(ascending=False).head(10)
for cl, cnt in por_classe.items():
    from colisao_rpi.data.nice_matrix import COLLISION_MATRIX
    labels = {35:'serviços comerciais',36:'seguros/financeiro',41:'educação/entret.',
              43:'alimentação',42:'TI/científico',44:'saúde/veterinária',
              37:'construção',40:'tratamento mat.',38:'telecom',39:'transporte'}
    print(f'    cl.{cl:2d} ({labels.get(cl,"")}): {cnt} casos')

print()
print('  RESUMO EXECUTIVO:')
print(f'    De {total} colidências detectadas pelo algoritmo:')
print(f'    → {len(df[df["VEREDITO"]=="ALTO_RISCO"]):>4} precisam de AÇÃO IMEDIATA (oposição)')
print(f'    → {len(df[df["VEREDITO"]=="MEDIO_RISCO"]):>4} precisam de MONITORAMENTO')
print(f'    → {total_descartar:>4} podem ser DESCARTADOS com os ajustes propostos')
print(f'    → {len(camada_c):>4} são FALSOS POSITIVOS')
print(f'    TOTAL ÚTIL: {len(enviar_atual)} de {total} ({len(enviar_atual)/total*100:.0f}%)')
