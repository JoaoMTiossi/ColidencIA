"""
Análise dos 40 casos (20 ALTO + 20 MÉDIO) com núcleo distintivo corrigido.
Raciocínio explícito linha a linha: POR QUE entra ou não.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from colisao_rpi.engine.similarity import similarity_score
from colisao_rpi.engine.nucleus import extract_nucleus, ALL_STOPWORDS
from colisao_rpi.engine.normalize import normalize, apply_phonetic, phonetic_key
from colisao_rpi.engine.rules import _spec_overlap

def score_num(v):
    try: return float(v)
    except: return -1.0

def get_cl(s):
    m = re.search(r'NCL\(13\)\s*(\d+)', str(s))
    return int(m.group(1)) if m else 0

def raciocinio(cli: str, rpi: str, cl_cli: int, cl_rpi: int,
               spec_cli: str, spec_rpi: str) -> dict:

    # Núcleo distintivo (com stopwords corrigidas)
    nuc_c = extract_nucleus(cli)
    nuc_r = extract_nucleus(rpi)

    # Scores
    sc_full = similarity_score(cli, rpi)
    sc_nuc  = similarity_score(nuc_c, nuc_r)
    sc_spec = _spec_overlap(spec_cli, spec_rpi)

    identico   = phonetic_key(cli) == phonetic_key(rpi)
    nuc_id     = phonetic_key(nuc_c) == phonetic_key(nuc_r)
    mesma_cl   = cl_cli == cl_rpi

    # Detectar se similaridade vem só do complemento
    complemento_c = cli.replace(nuc_c, '').strip()
    complemento_r = rpi.replace(nuc_r, '').strip()
    comp_sim = similarity_score(complemento_c, complemento_r) if complemento_c and complemento_r else 0.0
    nuc_diferente = sc_nuc < 0.65

    # ---- Raciocínio passo a passo ----
    passos = []
    decisao = ''

    # Passo 1: núcleos
    passos.append(f'NÚCLEO CLI: "{nuc_c}" | NÚCLEO RPI: "{nuc_r}" → similaridade {sc_nuc:.2f}')

    # Passo 2: complemento
    if complemento_c or complemento_r:
        passos.append(f'COMPLEMENTO CLI: "{complemento_c}" | COMPLEMENTO RPI: "{complemento_r}"')

    # Passo 3: spec
    if sc_spec >= 0:
        passos.append(f'SPEC overlap: {sc_spec:.0%}{"  — compatíveis" if sc_spec>=0.30 else "  — parcial" if sc_spec>=0.08 else "  — INCOMPATÍVEIS"}')
    else:
        passos.append('SPEC: não disponível')

    # Passo 4: classes
    passos.append(f'CLASSES: {cl_cli} {"=" if mesma_cl else "≠"} {cl_rpi}{"  (mesma)" if mesma_cl else "  (distintas)"}')

    # ---- Decisão ----
    if identico and sc_spec >= 0.10:
        decisao = 'DEVE_COLIDIR'
        passos.append(f'→ ENTRA: marcas foneticamente idênticas com spec compatível ({sc_spec:.0%})')

    elif identico and (sc_spec < 0.05 and sc_spec >= 0):
        decisao = 'BORDERLINE'
        passos.append(f'→ BORDERLINE: marcas idênticas mas specs incompatíveis — risco de associação de origem depende do segmento')

    elif identico:
        decisao = 'DEVE_COLIDIR'
        passos.append('→ ENTRA: marcas idênticas, spec não disponível — análise fonética prevalece')

    elif nuc_diferente and nuc_c and nuc_r:
        # Núcleos distintos — a similaridade vem do complemento
        if comp_sim >= 0.70:
            decisao = 'NAO_DEVE'
            passos.append(f'→ NÃO ENTRA: núcleos "{nuc_c}" ≠ "{nuc_r}" (score {sc_nuc:.2f}) — similaridade vem do complemento descritivo ("{complemento_c}" ≈ "{complemento_r}", {comp_sim:.2f}), que não pode ser monopolizado')
        else:
            decisao = 'NAO_DEVE'
            passos.append(f'→ NÃO ENTRA: núcleos distintos ("{nuc_c}" vs "{nuc_r}", score {sc_nuc:.2f}) — não há elemento distintivo em comum')

    elif nuc_id:
        if sc_spec >= 0 and sc_spec < 0.05:
            decisao = 'NAO_DEVE'
            passos.append(f'→ NÃO ENTRA: núcleos idênticos mas specs INCOMPATÍVEIS ({sc_spec:.0%}) — produtos/serviços distintos, sem risco de confusão')
        elif mesma_cl:
            decisao = 'DEVE_COLIDIR'
            passos.append(f'→ ENTRA: núcleos idênticos ("{nuc_c}" ≡ "{nuc_r}") na mesma classe {cl_cli}')
        else:
            decisao = 'BORDERLINE'
            passos.append(f'→ BORDERLINE: núcleos idênticos mas classes distintas ({cl_cli}≠{cl_rpi}) — avaliar risco de associação')

    elif sc_nuc >= 0.80:
        if sc_spec >= 0 and sc_spec < 0.05:
            decisao = 'NAO_DEVE'
            passos.append(f'→ NÃO ENTRA: núcleos similares ({sc_nuc:.2f}) mas specs INCOMPATÍVEIS ({sc_spec:.0%})')
        elif mesma_cl and sc_spec >= 0.20:
            decisao = 'DEVE_COLIDIR'
            passos.append(f'→ ENTRA: núcleos similares ("{nuc_c}" ≈ "{nuc_r}", {sc_nuc:.2f}), mesma classe, spec {sc_spec:.0%}')
        elif mesma_cl:
            decisao = 'DEVE_COLIDIR'
            passos.append(f'→ ENTRA: núcleos similares ({sc_nuc:.2f}), mesma classe {cl_cli} — spec insuficiente mas fonética forte')
        else:
            decisao = 'BORDERLINE'
            passos.append(f'→ BORDERLINE: núcleos similares ({sc_nuc:.2f}) em classes distintas ({cl_cli}≠{cl_rpi})')

    elif sc_nuc >= 0.65 and mesma_cl and sc_spec >= 0.35:
        decisao = 'DEVE_COLIDIR'
        passos.append(f'→ ENTRA: núcleos moderadamente similares ({sc_nuc:.2f}) + mesma classe + spec compatível ({sc_spec:.0%})')

    else:
        decisao = 'NAO_DEVE'
        passos.append(f'→ NÃO ENTRA: sem elemento distintivo similar suficiente (nuc={sc_nuc:.2f}, full={sc_full:.2f})')

    emoji = {'DEVE_COLIDIR': '✅', 'NAO_DEVE': '❌', 'BORDERLINE': '⚠️ '}
    return {
        'decisao':  decisao,
        'emoji':    emoji.get(decisao, '?'),
        'passos':   passos,
        'nuc_c':    nuc_c,
        'nuc_r':    nuc_r,
        'sc_full':  sc_full,
        'sc_nuc':   sc_nuc,
        'sc_spec':  sc_spec,
    }


# ---------------------------------------------------------------------------
print('Carregando relatório final...')
df = pd.read_excel('./relatorio_final/Relatorio_Final_IA_RPI2886.xlsx', sheet_name='Todos')
df['SCORE_SPEC_N'] = df['SCORE_SPEC'].apply(score_num)
df['CL_CLI_N']     = df['CLASSE CLIENTE'].apply(get_cl)
df['CL_3O_N']      = df['CLASSE TERCEIRO'].apply(get_cl)

resultados = []

for verd in ['ALTO_RISCO', 'MEDIO_RISCO']:
    grupo = df[df['VEREDITO'] == verd].head(20)
    deve = nao = border = 0

    print(f'\n{"="*75}')
    print(f'  {verd} — 20 casos | análise com núcleo distintivo corrigido')
    print(f'{"="*75}')

    for _, r in grupo.iterrows():
        res = raciocinio(
            str(r['MARCA CLIENTE']), str(r['MARCA TERCEIRO']),
            r['CL_CLI_N'], r['CL_3O_N'],
            str(r['ESPEC_CLIENTE']), str(r['ESPEC_TERCEIRO'])
        )

        if res['decisao'] == 'DEVE_COLIDIR':   deve += 1
        elif res['decisao'] == 'NAO_DEVE':     nao += 1
        else:                                   border += 1

        cl = str(r['CLASSE CLIENTE']).replace('NCL(13) ','cl.')
        print(f'\n  {res["emoji"]} {res["decisao"]}  [{cl}]')
        print(f'  CLI: {r["MARCA CLIENTE"]}')
        print(f'  RPI: {r["MARCA TERCEIRO"]}')
        for p in res['passos']:
            print(f'       {p}')

        resultados.append({
            'VEREDITO_ALGO': r['VEREDITO'],
            'DECISAO_IA':    res['decisao'],
            'MARCA CLIENTE': r['MARCA CLIENTE'],
            'MARCA TERCEIRO':r['MARCA TERCEIRO'],
            'CLASSE':        r['CLASSE CLIENTE'],
            'NUCLEO_CLI':    res['nuc_c'],
            'NUCLEO_RPI':    res['nuc_r'],
            'SC_FULL':       round(res['sc_full'],3),
            'SC_NUCLEO':     round(res['sc_nuc'],3),
            'SC_SPEC':       round(res['sc_spec'],3) if res['sc_spec']>=0 else 'N/D',
            'RACIOCINIO':    ' | '.join(res['passos']),
            'ESPEC_CLI':     str(r['ESPEC_CLIENTE'])[:200],
            'ESPEC_RPI':     str(r['ESPEC_TERCEIRO'])[:200],
        })

    print(f'\n  RESUMO: DEVE={deve}  NÃO DEVE={nao}  BORDERLINE={border}')

# ---------------------------------------------------------------------------
# Salvar
# ---------------------------------------------------------------------------
OUTPUT = './relatorio_final/Analise_nucleos_corrigidos.xlsx'
print(f'\nSalvando {OUTPUT}...')
df_out = pd.DataFrame(resultados)

with pd.ExcelWriter(OUTPUT, engine='openpyxl') as writer:
    df_out.to_excel(writer, index=False, sheet_name='Análise Núcleo Corrigido')
    from openpyxl.styles import PatternFill, Font, Alignment
    ws = writer.sheets['Análise Núcleo Corrigido']

    cores = {'DEVE_COLIDIR':'FF9999','NAO_DEVE':'C6EFCE','BORDERLINE':'FFEB9C'}
    hf = PatternFill('solid', fgColor='1F3864')
    for cell in ws[1]:
        cell.fill = hf
        cell.font = Font(color='FFFFFF', bold=True)
        cell.alignment = Alignment(horizontal='center', wrap_text=True)

    col_d = next(c.column for c in ws[1] if c.value == 'DECISAO_IA')
    for row in ws.iter_rows(min_row=2):
        v = row[col_d-1].value or ''
        fill = PatternFill('solid', fgColor=cores.get(v,'FFFFFF'))
        for cell in row:
            cell.fill = fill
            cell.alignment = Alignment(wrap_text=True, vertical='top')
        row[col_d-1].font = Font(bold=True)

    widths = {
        'VEREDITO_ALGO':14,'DECISAO_IA':16,'MARCA CLIENTE':34,'MARCA TERCEIRO':34,
        'CLASSE':13,'NUCLEO_CLI':20,'NUCLEO_RPI':20,
        'SC_FULL':10,'SC_NUCLEO':11,'SC_SPEC':10,
        'RACIOCINIO':80,'ESPEC_CLI':45,'ESPEC_RPI':45,
    }
    for col in ws.iter_cols(1, ws.max_column):
        h = col[0].value or ''
        ws.column_dimensions[col[0].column_letter].width = widths.get(h, 14)

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

print('Concluído.')
