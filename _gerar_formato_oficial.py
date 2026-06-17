"""
Gera relatório de colidência no formato oficial (3 abas):
  Relatório      — cabeçalho + dados básicos (processo, marca, classe, despacho)
  Análise Técnica — todos os scores + especificações + campos de análise
  Resumo         — estatísticas gerais
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime, timedelta
from colisao_rpi.engine.similarity import similarity_score, weighted_similarity
from colisao_rpi.engine.nucleus import extract_nucleus
from colisao_rpi.engine.rules import _spec_overlap
from colisao_rpi.engine.distinctiveness import is_descriptive
from colisao_rpi.engine.corpus import load_spec_corpus
from colisao_rpi.engine.normalize import phonetic_key, normalize
from colisao_rpi.data.nice_matrix import classes_collide
from colisao_rpi.data.loader_rpi import load_rpi_records
from colisao_rpi.data.loader_client import load_client_brands

_SPEC_CORPUS_PATH = os.path.join(
    os.path.dirname(__file__), 'colisao_rpi', 'data', 'corpus_spec_freq.json'
)

XML  = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\RM2886.xml'
XLSX = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\Relatório_Detalhado_Marcas -18-05-2026 - Total de processos - 46.619.xlsx'
INPUT = './relatorio_algoritmo/Relatorio_Colidencia_RPI_2886_28-04-2026_A_PROVINCIA.xlsx'
OUTPUT = r'C:\Users\jolut\Downloads\Colidencia_RPI2886_28-04-2026.xlsx'

RPI_NUMERO = '2886'
RPI_DATA   = '28/04/2026'
RPI_DT     = datetime(2026, 4, 28)
EMITIDO    = datetime.now().strftime('%d/%m/%Y %H:%M')

# Prazo por tipo
PRAZO_OPOSICAO = (RPI_DT + timedelta(days=60)).strftime('%d/%m/%Y')
PRAZO_PAN      = (RPI_DT + timedelta(days=180)).strftime('%d/%m/%Y')

# Despachos que significam OPOSIÇÃO
DESPACHOS_OPOSICAO = {'IPAS009','IPAS756','IPAS421','IPAS035','IPAS036'}

def get_cl(s):
    m = re.search(r'NCL\(13\)\s*(\d+)', str(s))
    return int(m.group(1)) if m else 0

def score_num(v):
    try: return float(v)
    except: return -1.0

# ---------------------------------------------------------------------------
print('Carregando dados...')
spec_corpus = load_spec_corpus(_SPEC_CORPUS_PATH)
rpi_records, _, _ = load_rpi_records(XML)

# Maps para lookup rápido
rpi_map = {r['processo']: r for r in rpi_records}

df_cli_raw = load_client_brands(XLSX)
cli_map = {str(r['PROCESSO']).strip(): r for _, r in df_cli_raw.iterrows()}

# Specs dos clientes
df_cli_full = pd.read_excel(XLSX, dtype=str)
df_cli_full.columns = [c.strip() for c in df_cli_full.columns]
spec_cli_map = dict(zip(
    df_cli_full['PROCESSO'].astype(str).str.strip(),
    df_cli_full['ESPECIFICAÇÃO'].fillna('')
))
apres_cli_map = dict(zip(
    df_cli_full['PROCESSO'].astype(str).str.strip(),
    df_cli_full['APRESENTAÇÃO'].fillna('Nominativa')
))

# Colunas extras do cliente
titular_cli_map = {}
for _, row in df_cli_raw.iterrows():
    titular_cli_map[str(row['PROCESSO']).strip()] = str(row.get('TITULAR',''))

print('Carregando relatório do algoritmo...')
df = pd.read_excel(INPUT, header=6)
df.columns = ['PROC_CLI','MARCA_CLI','CLASSE_CLI','TITULAR_CLI',
              'PROC_3O','MARCA_3O','CLASSE_3O']
df = df[df['PROC_CLI'] != 'PROCESSO CLIENTE'].dropna(subset=['PROC_CLI'])
print(f'  {len(df)} colidências')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def tipo_acao(despachos: list[tuple]) -> tuple[str,str,str]:
    """Retorna (tipo, prazo, desc_despacho) baseado nos despachos da marca RPI."""
    for cod, desc in despachos:
        cod_upper = str(cod).upper().replace(' ','').replace('-','')[:7]
        if any(cod_upper.startswith(d) for d in DESPACHOS_OPOSICAO):
            return 'OPOSIÇÃO', PRAZO_OPOSICAO, desc
    # fallback: PAN
    desc = despachos[0][1] if despachos else ''
    return 'PAN', PRAZO_PAN, desc

def codigo_despacho(despachos: list[tuple]) -> str:
    if not despachos:
        return ''
    cod, desc = despachos[0]
    return f'{cod} — {desc}'

def is_sigla(marca: str) -> str:
    norm = normalize(marca)
    tokens = norm.split()
    if len(tokens) == 1:
        t = tokens[0]
        if len(t) <= 5 and t.isalpha() and t == t.upper():
            return 'Sim'
    return 'Não'

def is_nome_proprio(marca: str) -> str:
    norm = normalize(marca)
    tokens = [t for t in norm.split() if len(t) >= 3]
    if not tokens:
        return 'Não'
    # Heurística: marca com 1-2 palavras, não na lista de genéricos
    from colisao_rpi.data.term_common import TODOS_GENERICOS
    proprios = [t for t in tokens if t not in TODOS_GENERICOS]
    # Se tem pelo menos 1 token não-genérico com inicial maiúscula e parece nome
    if proprios and len(proprios) <= 2:
        for t in proprios:
            # Padrão de nome próprio: termina em vogal, consonância típica
            if re.match(r'^[A-Z][a-z]{2,}(a|o|e|i|u|son|ton|ane|eia)?$',
                        t.capitalize(), re.IGNORECASE):
                return 'Sim'
    return 'Não'

def is_desgastado(marca: str, classe: int) -> str:
    from colisao_rpi.engine.distinctiveness import distinctive_tokens
    dtoks = distinctive_tokens(marca, classe, spec_corpus)
    distintos = [t for t, w, is_d, _ in dtoks if not is_d and w > 0.3]
    return 'Sim' if not distintos else 'Não'

def camada(regra: str) -> int:
    if 'IDENTICA' in str(regra):
        return 1
    if 'PONDERADO' in str(regra) or 'CONJUNTO' in str(regra):
        return 2
    return 3

def classificacao(score: float, tipo: str) -> str:
    if score >= 0.85:
        return 'ALTA'
    if score >= 0.65:
        return 'MEDIA'
    return 'BAIXA'

# ---------------------------------------------------------------------------
print('Calculando scores e campos...')
rows_tec = []
oposicao_count = 0
pan_count = 0
alta = media = baixa = 0
camadas = {1:0, 2:0, 3:0}

for i, (_, r) in enumerate(df.iterrows(), 1):
    if i % 500 == 0:
        print(f'  ... {i}/{len(df)}')

    cli_nome = str(r['MARCA_CLI'])
    rpi_nome = str(r['MARCA_3O'])
    cl_c     = get_cl(str(r['CLASSE_CLI']))
    cls_r    = [get_cl(x) for x in str(r['CLASSE_3O']).split(',')]
    cl_r     = cls_r[0] if cls_r else 0
    proc_c   = str(r['PROC_CLI']).strip()
    proc_r   = str(r['PROC_3O']).strip()

    # Dados do RPI
    rpi_rec  = rpi_map.get(proc_r, {})
    despachos= rpi_rec.get('despachos', [])
    titulares= rpi_rec.get('titulares', [])
    apres_rpi= rpi_rec.get('apresentacao', 'Nominativa') or 'Nominativa'
    spec_r_d = rpi_rec.get('especificacoes', {})
    spec_r   = spec_r_d.get(str(cl_r), '') or next(iter(spec_r_d.values()), '')

    # Dados do cliente
    spec_c   = spec_cli_map.get(proc_c, '')
    apres_c  = apres_cli_map.get(proc_c, 'Nominativa')

    # Tipo de ação e despacho
    tipo, prazo, desc_desp = tipo_acao(despachos)
    cod_desp = codigo_despacho(despachos)

    # Scores
    sc_bruto = similarity_score(cli_nome, rpi_nome)
    sc_pond  = weighted_similarity(cli_nome, rpi_nome, cl_c, spec_corpus)
    sc_nuc   = similarity_score(extract_nucleus(cli_nome), extract_nucleus(rpi_nome))
    sc_spec  = _spec_overlap(spec_c, spec_r)
    sc_spec_v = round(sc_spec, 4) if sc_spec >= 0 else 0.0

    # Score final = max(ponderado, bruto*0.7)
    score_final = round(max(sc_pond, sc_bruto * 0.7), 4)
    if phonetic_key(cli_nome) == phonetic_key(rpi_nome):
        score_final = 1.0

    # Regra (camada)
    if score_final == 1.0:
        regra = 'R1-IDENTICA'
    elif sc_pond >= 0.68:
        regra = 'R2-PONDERADO'
    elif sc_nuc >= 0.80:
        regra = 'R3-NUCLEO'
    else:
        regra = 'R4-TOKEN'

    cam = camada(regra)
    cls_colidem = 'Sim' if any(classes_collide(cl_c, c) for c in cls_r) else 'Não'
    classif = classificacao(score_final, tipo)

    # Núcleos
    nuc_c = extract_nucleus(cli_nome)
    nuc_r = extract_nucleus(rpi_nome)

    # Campos qualitativos
    sig = is_sigla(cli_nome)
    desg = is_desgastado(cli_nome, cl_c)
    nom_prop = is_nome_proprio(cli_nome)

    # Contagens
    if tipo == 'OPOSIÇÃO':
        oposicao_count += 1
    else:
        pan_count += 1
    if classif == 'ALTA':    alta += 1
    elif classif == 'MEDIA': media += 1
    else:                    baixa += 1
    camadas[cam] = camadas.get(cam, 0) + 1

    rows_tec.append({
        'ID':                  i,
        'Tipo Ação':           tipo,
        'Classificação':       classif,
        'Score Final':         score_final,
        'Marca Base':          cli_nome,
        'NCL Base':            cl_c,
        'Especificação Base':  str(spec_c)[:400],
        'Marca RPI':           rpi_nome,
        'NCL RPI':             cl_r,
        'Especificação RPI':   str(spec_r)[:400],
        'Processo RPI':        proc_r,
        'Despacho':            cod_desp,
        'Titular RPI':         ', '.join(titulares),
        'Camada':              cam,
        'Score Nome':          round(sc_bruto, 4),
        'Score Fonético':      round(sc_pond, 4),
        'Score Spec':          sc_spec_v,
        'Score Núcleo':        round(sc_nuc, 4),
        'Score IA':            None,
        'Justificativa IA':    None,
        'Núcleo Base':         nuc_c,
        'Núcleo RPI':          nuc_r,
        'Classes Colidem':     cls_colidem,
        'Sigla?':              sig,
        'Desgastado?':         desg,
        'Apresent. Base':      apres_c,
        'Apresent. RPI':       apres_rpi,
        'Nome Próprio?':       nom_prop,
    })

df_tec = pd.DataFrame(rows_tec)
df_tec = df_tec.sort_values(['Classificação','Score Final'],
                             ascending=[True, False],
                             key=lambda x: x.map({'ALTA':0,'MEDIA':1,'BAIXA':2})
                             if x.name == 'Classificação' else -x)

total = len(df_tec)
print(f'\n  OPOSIÇÃO: {oposicao_count}  |  PAN: {pan_count}')
print(f'  ALTA: {alta}  MEDIA: {media}  BAIXA: {baixa}  TOTAL: {total}')

# ---------------------------------------------------------------------------
# Aba Relatório (formato legado simplificado)
# ---------------------------------------------------------------------------
rows_rel = []
for _, r in df_tec.iterrows():
    rows_rel.append({
        'PROCESSO CLIENTE':  r['ID'],
        'MARCA CLIENTE':     r['Marca Base'],
        'CLASSE CLIENTE':    f"NCL(13) {r['NCL Base']}",
        'TITULAR CLIENTE':   '',
        'PROCESSO TERCEIRO': r['Processo RPI'],
        'MARCA TERCEIRO':    r['Marca RPI'],
        'CLASSE TERCEIRO':   f"NCL(13) {r['NCL RPI']}",
        'TIPO DESPACHO':     r['Tipo Ação'],
        'PRAZO DESPACHO':    PRAZO_OPOSICAO if r['Tipo Ação']=='OPOSIÇÃO' else PRAZO_PAN,
        'DESC. DESPACHO':    r['Despacho'].split('—')[-1].strip() if '—' in str(r['Despacho']) else r['Despacho'],
    })

df_rel = pd.DataFrame(rows_rel)

# ---------------------------------------------------------------------------
# Aba Resumo
# ---------------------------------------------------------------------------
resumo_data = [
    ('', ''),
    ('Data de execução', EMITIDO),
    ('Número da RPI', RPI_NUMERO),
    ('Data da RPI', RPI_DATA),
    ('', ''),
    ('VOLUMES', ''),
    ('Total carteira de clientes', len(df_cli_raw)),
    ('Total RPI analisada', len(rpi_records)),
    ('→ Marcas para OPOSIÇÃO', sum(1 for r in rpi_records
                                    if any(str(d[0]).upper().startswith(tuple(DESPACHOS_OPOSICAO))
                                           for d in r['despachos']))),
    ('→ Marcas para PAN', sum(1 for r in rpi_records
                               if not any(str(d[0]).upper().startswith(tuple(DESPACHOS_OPOSICAO))
                                          for d in r['despachos']))),
    ('', ''),
    ('ALERTAS POR TIPO DE AÇÃO', ''),
    (f'OPOSIÇÃO (prazo 60 dias) — total', oposicao_count),
    (f'PAN (prazo 180 dias) — total', pan_count),
    ('', ''),
    ('ALERTAS POR CLASSIFICAÇÃO', ''),
    ('ALTA', alta),
    ('MÉDIA', media),
    ('BAIXA', baixa),
    ('TOTAL', total),
    ('', ''),
    ('PIPELINE — VOLUME POR CAMADA', ''),
    ('Camada 1 (Nome idêntico)', camadas.get(1,0)),
    ('Camada 2 (Fonético/Ponderado)', camadas.get(2,0)),
    ('Camada 3 (Especificação)', camadas.get(3,0)),
]
df_resumo = pd.DataFrame(resumo_data, columns=['Relatório de Colidência de Marcas', ''])

# ---------------------------------------------------------------------------
print(f'\nSalvando {OUTPUT}...')
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

wb_tmp = openpyxl.Workbook()
ws_rel = wb_tmp.active
ws_rel.title = 'Relatório'

# Linhas de cabeçalho
ws_rel.cell(1, 1, f'RPI Nº {RPI_NUMERO}  |  Data de publicação: {RPI_DATA}  |  Emitido em: {EMITIDO}')
ws_rel.cell(1, 1).font = Font(bold=True, size=11)
ws_rel.cell(2, 1, f'Marcas monitoradas: {len(df_cli_raw):,}  |  Marcas verificadas na RPI: {len(rpi_records):,}  |  Colisões selecionadas: {total:,}')
ws_rel.cell(3, 1, 'OPOSIÇÃO = prazo 60 dias  |  PAN (Pedido Administrativo de Nulidade) = prazo 180 dias')

cols_rel = ['PROCESSO CLIENTE','MARCA CLIENTE','CLASSE CLIENTE','TITULAR CLIENTE',
            'PROCESSO TERCEIRO','MARCA TERCEIRO','CLASSE TERCEIRO',
            'TIPO DESPACHO','PRAZO DESPACHO','DESC. DESPACHO']
for j, h in enumerate(cols_rel, 1):
    c = ws_rel.cell(6, j, h)
    c.fill = PatternFill('solid', fgColor='1F3864')
    c.font = Font(bold=True, color='FFFFFF')
    c.alignment = Alignment(horizontal='center')

cores_tipo = {'OPOSIÇÃO': 'FFE5E5', 'PAN': 'E5F0FF'}
for row_data in rows_rel:
    row_num = ws_rel.max_row + 1
    ws_rel.append([row_data[c] for c in cols_rel])
    cor = cores_tipo.get(str(row_data.get('TIPO DESPACHO','')), 'FFFFFF')
    fill = PatternFill('solid', fgColor=cor)
    for cell in ws_rel[row_num]:
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=False, vertical='top')

for i, w in enumerate([15,35,14,35,15,35,14,12,14,55], 1):
    ws_rel.column_dimensions[get_column_letter(i)].width = w
ws_rel.freeze_panes = 'A7'

# Aba Análise Técnica
ws_tec = wb_tmp.create_sheet('Análise Técnica')
cols_tec = list(df_tec.columns)
for j, h in enumerate(cols_tec, 1):
    c = ws_tec.cell(1, j, h)
    c.fill = PatternFill('solid', fgColor='1F3864')
    c.font = Font(bold=True, color='FFFFFF')
    c.alignment = Alignment(horizontal='center', wrap_text=True)

cores_class = {'ALTA':'FFCCCC', 'MEDIA':'FFF2CC', 'BAIXA':'E2EFDA'}
for row_idx, (_, row) in enumerate(df_tec.iterrows(), 2):
    cor = cores_class.get(str(row.get('Classificação','')), 'FFFFFF')
    fill = PatternFill('solid', fgColor=cor)
    for j, col in enumerate(cols_tec, 1):
        val = row[col]
        if pd.isna(val): val = None
        c = ws_tec.cell(row_idx, j, val)
        c.fill = fill
        c.alignment = Alignment(wrap_text=True, vertical='top')

widths_tec = {
    'ID':8,'Tipo Ação':11,'Classificação':13,'Score Final':11,
    'Marca Base':32,'NCL Base':9,'Especificação Base':50,
    'Marca RPI':32,'NCL RPI':9,'Especificação RPI':50,
    'Processo RPI':14,'Despacho':55,'Titular RPI':30,
    'Camada':9,'Score Nome':11,'Score Fonético':13,'Score Spec':11,'Score Núcleo':12,
    'Score IA':10,'Justificativa IA':50,
    'Núcleo Base':20,'Núcleo RPI':20,'Classes Colidem':13,
    'Sigla?':8,'Desgastado?':12,'Apresent. Base':14,'Apresent. RPI':13,'Nome Próprio?':13,
}
for j, col in enumerate(cols_tec, 1):
    ws_tec.column_dimensions[get_column_letter(j)].width = widths_tec.get(col, 14)
ws_tec.freeze_panes = 'E2'
ws_tec.auto_filter.ref = f'A1:{get_column_letter(len(cols_tec))}{ws_tec.max_row}'

# Aba Resumo
ws_res = wb_tmp.create_sheet('Resumo')
for i, (k, v) in enumerate(resumo_data, 1):
    ws_res.cell(i, 1, k)
    ws_res.cell(i, 2, v)
    if k and not k.startswith('→') and not k.startswith('Camada') and v == '':
        ws_res.cell(i, 1).font = Font(bold=True)
ws_res.column_dimensions['A'].width = 38
ws_res.column_dimensions['B'].width = 18

wb_tmp.save(OUTPUT)

print(f'Arquivo salvo: {OUTPUT}')
print(f'  Aba Relatório     : {total} linhas')
print(f'  Aba Análise Técnica: {total} linhas, {len(df_tec.columns)} colunas')
print(f'  Aba Resumo        : estatísticas')
