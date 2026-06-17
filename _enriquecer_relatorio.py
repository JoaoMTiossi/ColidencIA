"""
Enriquece o relatório do algoritmo com scores e especificações.
Sem veredito de IA — só dados para a IA externa analisar.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from colisao_rpi.engine.similarity import similarity_score, weighted_similarity
from colisao_rpi.engine.nucleus import extract_nucleus
from colisao_rpi.engine.rules import _spec_overlap
from colisao_rpi.engine.distinctiveness import distinctive_tokens
from colisao_rpi.engine.corpus import load_spec_corpus
from colisao_rpi.data.loader_rpi import load_rpi_records
from colisao_rpi.engine.normalize import phonetic_key

_SPEC_CORPUS_PATH = os.path.join(
    os.path.dirname(__file__), 'colisao_rpi', 'data', 'corpus_spec_freq.json'
)

def get_cl(s):
    m = re.search(r'NCL\(13\)\s*(\d+)', str(s))
    return int(m.group(1)) if m else 0

def score_num(v):
    try: return float(v)
    except: return -1.0

print('Carregando spec corpus...')
spec_corpus = load_spec_corpus(_SPEC_CORPUS_PATH)
print(f'  {sum(spec_corpus.get("_N",{}).values())} registros')

print('Carregando specs da RPI...')
XML = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\RM2886.xml'
rpi_records, _, _ = load_rpi_records(XML)
spec_rpi_map = {r['processo']: r['especificacoes'] for r in rpi_records}

print('Carregando specs dos clientes...')
XLSX = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\Relatório_Detalhado_Marcas -18-05-2026 - Total de processos - 46.619.xlsx'
df_cli = pd.read_excel(XLSX, dtype=str)
df_cli.columns = [c.strip() for c in df_cli.columns]
spec_cli_map = dict(zip(
    df_cli['PROCESSO'].astype(str).str.strip(),
    df_cli['ESPECIFICAÇÃO'].fillna('')
))

print('Carregando relatório do algoritmo...')
INPUT  = './relatorio_algoritmo/Relatorio_Colidencia_RPI_2886_28-04-2026_A_PROVINCIA.xlsx'
OUTPUT = './relatorio_algoritmo/Relatorio_Com_Scores_RPI2886.xlsx'

df = pd.read_excel(INPUT, header=6)
df.columns = ['PROC_CLI','MARCA_CLI','CLASSE_CLI','TITULAR_CLI',
              'PROC_3O','MARCA_3O','CLASSE_3O']
df = df[df['PROC_CLI'] != 'PROCESSO CLIENTE'].dropna(subset=['PROC_CLI'])
print(f'  {len(df)} casos')

rows = []
for i, (_, r) in enumerate(df.iterrows(), 1):
    if i % 500 == 0:
        print(f'  ... {i}/{len(df)}')

    cli    = str(r['MARCA_CLI'])
    rpi_n  = str(r['MARCA_3O'])
    cl_c   = get_cl(str(r['CLASSE_CLI']))
    cls_r  = [get_cl(x) for x in str(r['CLASSE_3O']).split(',')]
    cl_r   = cls_r[0] if cls_r else 0
    proc_c = str(r['PROC_CLI']).strip()
    proc_r = str(r['PROC_3O']).strip()
    cl_r0  = str(cl_r)

    # Specs
    spec_c   = spec_cli_map.get(proc_c, '')
    spec_r_d = spec_rpi_map.get(proc_r, {})
    spec_r   = spec_r_d.get(cl_r0, '') or next(iter(spec_r_d.values()), '')

    # Núcleos
    nuc_c = extract_nucleus(cli)
    nuc_r = extract_nucleus(rpi_n)

    # Scores
    sc_bruto = similarity_score(cli, rpi_n)
    sc_pond  = weighted_similarity(cli, rpi_n, cl_c, spec_corpus)
    sc_nuc   = similarity_score(nuc_c, nuc_r)
    sc_spec  = _spec_overlap(spec_c, spec_r)

    # Tokens distintivos vs descritores
    dtoks_c = distinctive_tokens(cli, cl_c, spec_corpus)
    dtoks_r = distinctive_tokens(rpi_n, cl_r, spec_corpus)
    elem_c = ' '.join(t for t, w, is_d, _ in dtoks_c if not is_d and w > 0.3) or nuc_c
    elem_r = ' '.join(t for t, w, is_d, _ in dtoks_r if not is_d and w > 0.3) or nuc_r
    descr_c = ', '.join(t for t, _, is_d, _ in dtoks_c if is_d)
    descr_r = ', '.join(t for t, _, is_d, _ in dtoks_r if is_d)
    sc_elem  = similarity_score(elem_c, elem_r)

    identico = phonetic_key(cli) == phonetic_key(rpi_n)

    rows.append({
        'PROCESSO CLIENTE':   r['PROC_CLI'],
        'MARCA CLIENTE':      cli,
        'CLASSE CLIENTE':     r['CLASSE_CLI'],
        'TITULAR CLIENTE':    r['TITULAR_CLI'],
        'PROCESSO TERCEIRO':  r['PROC_3O'],
        'MARCA TERCEIRO':     rpi_n,
        'CLASSE TERCEIRO':    r['CLASSE_3O'],
        # Núcleos
        'NUCLEO_CLI':         nuc_c,
        'NUCLEO_RPI':         nuc_r,
        # Elementos distintivos
        'ELEM_DISTINT_CLI':   elem_c,
        'ELEM_DISTINT_RPI':   elem_r,
        # Descritores identificados
        'DESCRITORES_CLI':    descr_c,
        'DESCRITORES_RPI':    descr_r,
        # Scores
        'SC_POND':            round(sc_pond, 3),
        'SC_BRUTO':           round(sc_bruto, 3),
        'SC_NUCLEO':          round(sc_nuc, 3),
        'SC_ELEM_DISTINT':    round(sc_elem, 3),
        'SC_SPEC':            round(sc_spec, 3) if sc_spec >= 0 else 'N/D',
        'IDENTICAS':          'SIM' if identico else 'NÃO',
        # Especificações completas
        'ESPEC_CLIENTE':      str(spec_c)[:500],
        'ESPEC_TERCEIRO':     str(spec_r)[:500],
    })

df_out = pd.DataFrame(rows)
df_out = df_out.sort_values(['SC_POND', 'SC_BRUTO'], ascending=[False, False])

print(f'\nSalvando {OUTPUT}...')

with pd.ExcelWriter(OUTPUT, engine='openpyxl') as writer:
    df_out.to_excel(writer, index=False, sheet_name='Colidências')

    from openpyxl.styles import PatternFill, Font, Alignment

    ws = writer.sheets['Colidências']

    # Header
    hf = PatternFill('solid', fgColor='1F3864')
    for cell in ws[1]:
        cell.fill = hf
        cell.font = Font(color='FFFFFF', bold=True)
        cell.alignment = Alignment(horizontal='center', wrap_text=True)

    # Colorir por score ponderado
    col_pond = next(c.column for c in ws[1] if c.value == 'SC_POND')
    col_id   = next(c.column for c in ws[1] if c.value == 'IDENTICAS')

    for row in ws.iter_rows(min_row=2):
        sc = row[col_pond - 1].value or 0
        id_ = row[col_id - 1].value or ''
        if id_ == 'SIM' or (isinstance(sc, float) and sc >= 0.85):
            cor = 'FFCCCC'   # vermelho — alta prioridade
        elif isinstance(sc, float) and sc >= 0.68:
            cor = 'FFF2CC'   # amarelo — média prioridade
        else:
            cor = 'FFFFFF'   # branco
        fill = PatternFill('solid', fgColor=cor)
        for cell in row:
            cell.fill = fill
            cell.alignment = Alignment(wrap_text=True, vertical='top')

    widths = {
        'PROCESSO CLIENTE':15, 'MARCA CLIENTE':32, 'CLASSE CLIENTE':13,
        'TITULAR CLIENTE':30, 'PROCESSO TERCEIRO':15, 'MARCA TERCEIRO':32,
        'CLASSE TERCEIRO':13, 'NUCLEO_CLI':20, 'NUCLEO_RPI':20,
        'ELEM_DISTINT_CLI':22, 'ELEM_DISTINT_RPI':22,
        'DESCRITORES_CLI':22, 'DESCRITORES_RPI':22,
        'SC_POND':10, 'SC_BRUTO':10, 'SC_NUCLEO':10,
        'SC_ELEM_DISTINT':14, 'SC_SPEC':10, 'IDENTICAS':10,
        'ESPEC_CLIENTE':55, 'ESPEC_TERCEIRO':55,
    }
    for col in ws.iter_cols(1, ws.max_column):
        h = col[0].value or ''
        ws.column_dimensions[col[0].column_letter].width = widths.get(h, 14)

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

# Estatísticas
print()
print('=== RESUMO ===')
total = len(df_out)
identicas = (df_out['IDENTICAS'] == 'SIM').sum()
alta = (df_out['SC_POND'] >= 0.85).sum()
media = ((df_out['SC_POND'] >= 0.68) & (df_out['SC_POND'] < 0.85)).sum()
baixa = (df_out['SC_POND'] < 0.68).sum()
print(f'  Total colidências         : {total}')
print(f'  Marcas idênticas          : {identicas}')
print(f'  Score ponderado >= 0.85   : {alta}  (vermelho)')
print(f'  Score ponderado 0.68-0.85 : {media}  (amarelo)')
print(f'  Score ponderado < 0.68    : {baixa}  (branco)')
print(f'\nArquivo: {OUTPUT}')
print('Concluído.')
