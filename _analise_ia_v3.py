"""
Análise IA v3 — raciocínio de advogado marcário.
Avalia conjunto marcário (nome completo), fonética e especificação.
Gera relatório Excel + plano de correção do algoritmo.
"""
from __future__ import annotations
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from collections import defaultdict, Counter
from rapidfuzz import fuzz as _fuzz
from colisao_rpi.engine.similarity import similarity_score
from colisao_rpi.engine.nucleus import extract_nucleus, ALL_STOPWORDS, PALAVRAS_COMUNS
from colisao_rpi.engine.normalize import normalize, apply_phonetic, phonetic_key
from colisao_rpi.engine.rules import _spec_tokens, _spec_overlap
from colisao_rpi.data.nice_matrix import classes_collide
from colisao_rpi.data.loader_rpi import load_rpi_records

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_TOKENS_DESCRITORES: frozenset[str] = frozenset({
    'MOTORS','MOTOR','MOTO','AUTO','AUTOMOVEL','VEICULOS','VEICULO','AUTOMOTIVO',
    'DELIVERY','ENTREGA','EXPRESS','EXPRESSO',
    'SEGUROS','SEGURO','CORRETORA','FINANCEIRA','CREDITO','INVESTIMENTOS',
    'MODA','MODAS','FASHION','ROUPAS','VESTUARIO',
    'PIZZA','PIZZARIA','BURGER','FOOD','LANCHE','SUSHI','RESTAURANTE',
    'SHOP','STORE','MERCADO','MARKET','COMERCIO','LOJA',
    'TECH','DIGITAL','ONLINE','SISTEMAS','SOLUCOES',
    'TUDO','GERAL','CLEAN','NOVO','NOVA','TOTAL',
    'PINK','ROSA','VERDE','AZUL','BRANCO','PRETO','DOURADO','PRATA',
    'BAR','CAFE','CAFETERIA','LANCHONETE','PADARIA','DOCERIA','CONFEITARIA',
    'POSTO','CENTRO','TOCA','SOLAR','PALACE','PLAZA','PARK',
    'BRASIL','NACIONAL','REGIONAL','NORTE','SUL','LESTE','OESTE',
    'MASTER','PRIME','GOLD','SILVER','BEAUTY','EVENTOS','CONTABILIDADE',
    'IMOVEIS','TRANSPORTES','AGRO','ACESSORIOS','ESTETICA','ODONTOLOGIA',
    'TURISMO','MUNDO','ATELIE','STUDIO','ACADEMIA','ESCOLA','INSTITUTO',
    'IMOBILIARIA','ENERGIA','GOURMET','DISTRIBUIDORA','PECAS',
    'COMUNICACAO','COSMETICOS','ADVOCACIA','CONSTRUTORA','ENGENHARIA',
})

_MIN_DIST_TOKEN = 4


def _dist_tokens(text: str) -> list[str]:
    """Tokens fonéticos DISTINTIVOS (sem descritores nem stopwords)."""
    return [
        apply_phonetic(t)
        for t in normalize(text).split()
        if len(t) >= _MIN_DIST_TOKEN
        and t not in ALL_STOPWORDS
        and t not in _TOKENS_DESCRITORES
    ]


def _best_token_pair(a: str, b: str) -> tuple[float, str, str]:
    ta, tb = _dist_tokens(a), _dist_tokens(b)
    best, pa, pb = 0.0, '', ''
    for x in ta:
        for y in tb:
            s = _fuzz.ratio(x, y) / 100.0
            if s > best:
                best, pa, pb = s, x, y
    return best, pa, pb


def get_class_num(s: str) -> int:
    m = re.search(r'NCL\(13\)\s*(\d+)', str(s))
    return int(m.group(1)) if m else 0


def _classe_label(cl: int) -> str:
    L = {
        9:'eletrônicos/software', 16:'papelaria', 18:'bolsas/acessórios',
        25:'vestuário', 28:'brinquedos/jogos', 29:'alimentos processados',
        30:'alimentos/café/confeitaria', 32:'bebidas não-alcoólicas',
        33:'bebidas alcoólicas', 35:'serviços comerciais/varejo',
        36:'serviços financeiros/seguros', 37:'construção/reparos',
        38:'telecomunicações', 39:'transporte/logística',
        40:'tratamento de materiais', 41:'educação/entretenimento',
        42:'serviços científicos/TI', 43:'alimentação/hospedagem',
        44:'serviços médicos/veterinários', 45:'serviços jurídicos/segurança',
    }
    return L.get(cl, f'classe {cl}')


# ---------------------------------------------------------------------------
# Motor de análise — raciocínio de advogado
# ---------------------------------------------------------------------------
def analisar_advogado(cli: str, rpi_n: str, cl_cli: int, cl_rpi_list: list[int],
                      spec_cli: str, spec_rpi: str) -> dict:

    cl_rpi       = cl_rpi_list[0] if cl_rpi_list else 0
    mesma_classe  = cl_cli == cl_rpi
    correlata     = any(classes_collide(cl_cli, c) for c in cl_rpi_list) and not mesma_classe

    sc_full  = similarity_score(cli, rpi_n)
    nucleo_c = extract_nucleus(cli)
    nucleo_r = extract_nucleus(rpi_n)
    sc_nuc   = similarity_score(nucleo_c, nucleo_r)
    sc_spec  = _spec_overlap(spec_cli, spec_rpi)
    sc_tok, tok_a, tok_b = _best_token_pair(cli, rpi_n)
    identico = phonetic_key(cli) == phonetic_key(rpi_n)

    cl_l_c = _classe_label(cl_cli)
    cl_l_r = _classe_label(cl_rpi)

    # Interpretação da especificação
    if sc_spec < 0:
        spec_disp = False
        spec_txt  = 'especificações não disponíveis para comparação'
    elif sc_spec >= 0.35:
        spec_disp = True
        spec_txt  = f'especificações compatíveis ({sc_spec:.0%} de sobreposição) — mesmo segmento de produtos/serviços'
    elif sc_spec >= 0.08:
        spec_disp = True
        spec_txt  = f'especificações parcialmente compatíveis ({sc_spec:.0%} de sobreposição)'
    else:
        spec_disp = True
        spec_txt  = f'especificações incompatíveis ({sc_spec:.0%} de sobreposição) — produtos/serviços distintos'

    motivo = []
    veredito  = ''
    prioridade = 4

    # ---- BLOCO 1: marcas idênticas ----
    if identico:
        if spec_disp and sc_spec < 0.05:
            veredito, prioridade = 'MEDIO_RISCO', 2
            motivo.append(
                f'Conjunto marcário foneticamente idêntico ("{cli}" ≡ "{rpi_n}"), '
                f'porém {spec_txt}. Sob o art. 124-XIX da LPI, marcas idênticas em '
                f'produtos/serviços distintos podem coexistir. Recomenda-se verificar '
                f'se há risco de associação de origem pelo consumidor médio.'
            )
        else:
            veredito, prioridade = 'ALTO_RISCO', 1
            motivo.append(
                f'Conjunto marcário foneticamente idêntico ("{cli}" ≡ "{rpi_n}") '
                f'na classe de {cl_l_c}. {spec_txt}. '
                f'Conforme art. 124-XIX da LPI e Resolução INPI 248/2019, '
                f'marcas idênticas para produtos/serviços iguais ou afins configuram '
                f'impedimento absoluto de registro. Oposição fortemente recomendada.'
            )

    # ---- BLOCO 2: mesmo núcleo distintivo ----
    elif sc_nuc >= 0.90 and mesma_classe:
        if spec_disp and sc_spec < 0.05:
            veredito, prioridade = 'BAIXO_RISCO', 3
            motivo.append(
                f'Núcleos distintivos muito similares ("{nucleo_c}" ≈ "{nucleo_r}", '
                f'score {sc_nuc:.2f}), mas {spec_txt}. '
                f'A delimitação de especificação afasta o risco de confusão no mercado. '
                f'Monitorar expansão de cobertura pelo terceiro.'
            )
        elif spec_disp and sc_spec >= 0.35:
            veredito, prioridade = 'ALTO_RISCO', 1
            motivo.append(
                f'Núcleos distintivos praticamente idênticos ("{nucleo_c}" ≈ "{nucleo_r}", '
                f'score {sc_nuc:.2f}) na mesma classe de {cl_l_c}, com {spec_txt}. '
                f'O elemento dominante das marcas é confundível e os produtos/serviços '
                f'são os mesmos — risco concreto de confusão pelo consumidor médio.'
            )
        else:
            veredito, prioridade = 'ALTO_RISCO', 1
            motivo.append(
                f'Núcleos distintivos praticamente idênticos ("{nucleo_c}" ≈ "{nucleo_r}", '
                f'score {sc_nuc:.2f}) na mesma classe de {cl_l_c}. {spec_txt}. '
                f'Alta probabilidade de confusão — analisar oposição.'
            )

    # ---- BLOCO 3: conjunto marcário similar, mesma classe ----
    elif sc_full >= 0.80 and mesma_classe:
        if spec_disp and sc_spec < 0.05:
            veredito, prioridade = 'BAIXO_RISCO', 3
            motivo.append(
                f'Conjunto marcário similar (score {sc_full:.2f}) na classe de {cl_l_c}, '
                f'mas {spec_txt}. Marcas compostas com termos comuns podem '
                f'coexistir quando as especificações são claramente distintas (INPI 248/2019, §4º).'
            )
        else:
            veredito, prioridade = 'ALTO_RISCO', 1
            motivo.append(
                f'Conjunto marcário altamente similar (score {sc_full:.2f}) na classe de {cl_l_c}. '
                f'{spec_txt}. O consumidor de atenção ordinária pode confundir as marcas '
                f'no mesmo canal de comercialização.'
            )

    # ---- BLOCO 4: núcleo similar, mesma classe ----
    elif sc_nuc >= 0.80 and mesma_classe:
        if spec_disp and sc_spec < 0.05:
            veredito, prioridade = 'BAIXO_RISCO', 3
            motivo.append(
                f'Núcleos fonéticos similares ("{nucleo_c}" ≈ "{nucleo_r}", score {sc_nuc:.2f}) '
                f'na mesma classe, mas {spec_txt}. '
                f'A diferença de cobertura atenua o risco de confusão.'
            )
        else:
            veredito, prioridade = 'MEDIO_RISCO', 2
            motivo.append(
                f'Núcleos fonéticos similares ("{nucleo_c}" ≈ "{nucleo_r}", score {sc_nuc:.2f}) '
                f'na classe de {cl_l_c} (conjunto completo: score {sc_full:.2f}). {spec_txt}. '
                f'Avaliar se o elemento dominante pode induzir o consumidor a associar as origens.'
            )

    # ---- BLOCO 5: conjunto similar, mesma classe, score médio ----
    elif sc_full >= 0.60 and mesma_classe:
        if spec_disp and sc_spec < 0.05:
            veredito, prioridade = 'FALSO_POSITIVO', 4
            motivo.append(
                f'Conjunto marcário com similaridade moderada (score {sc_full:.2f}) '
                f'e {spec_txt}. Sem identidade real entre as marcas no mercado.'
            )
        elif spec_disp and sc_spec >= 0.35:
            veredito, prioridade = 'MEDIO_RISCO', 2
            motivo.append(
                f'Similaridade moderada (score {sc_full:.2f}) na classe de {cl_l_c} '
                f'com {spec_txt}. Avaliar apresentação visual e canal de venda.'
            )
        else:
            veredito, prioridade = 'BAIXO_RISCO', 3
            motivo.append(
                f'Similaridade moderada (score {sc_full:.2f}) na classe de {cl_l_c}. '
                f'{spec_txt}. Risco baixo — acompanhar.'
            )

    # ---- BLOCO 6: conjunto similar, classes correlatas ----
    elif sc_full >= 0.75 and correlata:
        if spec_disp and sc_spec >= 0.20:
            veredito, prioridade = 'MEDIO_RISCO', 2
            motivo.append(
                f'Conjunto marcário similar (score {sc_full:.2f}) em classes correlatas '
                f'({cl_l_c} × {cl_l_r}), com {spec_txt}. '
                f'Risco de confusão indireta ou associação de origem entre segmentos afins.'
            )
        else:
            veredito, prioridade = 'BAIXO_RISCO', 3
            motivo.append(
                f'Conjunto marcário similar (score {sc_full:.2f}) em classes correlatas '
                f'({cl_l_c} × {cl_l_r}). {spec_txt}. '
                f'Risco limitado pela distinção de segmentos.'
            )

    # ---- BLOCO 7: token distintivo similar ----
    elif tok_a and sc_tok >= 0.85 and sc_full >= 0.50:
        if spec_disp and sc_spec < 0.05:
            veredito, prioridade = 'FALSO_POSITIVO', 4
            motivo.append(
                f'Token distintivo similar ("{tok_a}" ≈ "{tok_b}", score {sc_tok:.2f}), '
                f'mas {spec_txt}. Coincidência fonética sem risco real de confusão.'
            )
        elif mesma_classe:
            veredito, prioridade = 'MEDIO_RISCO', 2
            motivo.append(
                f'Elemento distintivo similar ("{tok_a}" ≈ "{tok_b}", score {sc_tok:.2f}) '
                f'na mesma classe de {cl_l_c}. {spec_txt}. '
                f'Avaliar se o elemento compartilhado é o dominante da marca.'
            )
        else:
            veredito, prioridade = 'BAIXO_RISCO', 3
            motivo.append(
                f'Token distintivo similar ("{tok_a}" ≈ "{tok_b}") em classes correlatas. '
                f'{spec_txt}. Risco baixo.'
            )

    # ---- BLOCO 8: demais ----
    elif sc_full < 0.50:
        veredito, prioridade = 'FALSO_POSITIVO', 4
        motivo.append(
            f'Conjunto marcário pouco similar (score {sc_full:.2f}, núcleo {sc_nuc:.2f}). '
            f'Não há risco real de confusão pelo consumidor.'
        )
    else:
        veredito, prioridade = 'BAIXO_RISCO', 3
        motivo.append(
            f'Similaridade borderline (conjunto: {sc_full:.2f}, núcleo: {sc_nuc:.2f}). '
            f'{spec_txt}. Monitorar sem ação imediata.'
        )

    # Complemento de classe
    if not mesma_classe and veredito not in ('FALSO_POSITIVO',):
        rel = 'correlatas' if correlata else 'não correlatas'
        motivo.append(f'[Classes {cl_cli}/{cl_rpi} são {rel} na matriz Nice.]')

    tok_info = f'{tok_a}~{tok_b}' if tok_a else '—'

    return {
        'VEREDITO':      veredito,
        'PRIORIDADE':    prioridade,
        'SCORE_NOME':    round(sc_full, 3),
        'SCORE_NUCLEO':  round(sc_nuc, 3),
        'SCORE_SPEC':    round(sc_spec, 3) if sc_spec >= 0 else 'N/D',
        'TOKEN_DIST':    tok_info,
        'ESPEC_CLIENTE': str(spec_cli)[:250] if spec_cli else '',
        'ESPEC_TERCEIRO':str(spec_rpi)[:250] if spec_rpi else '',
        'MOTIVO_IA':     ' '.join(motivo),
    }


# ---------------------------------------------------------------------------
# Carregar specs
# ---------------------------------------------------------------------------
XLSX_CLI = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\Relatório_Detalhado_Marcas -18-05-2026 - Total de processos - 46.619.xlsx'
XML_RPI  = r'C:\Users\jolut\OneDrive\Desktop\COLIDENCIA\zipppp\RM2886\RM2886.xml'

print('Carregando especificações dos clientes...')
df_cli_raw = pd.read_excel(XLSX_CLI, dtype=str)
df_cli_raw.columns = [c.strip() for c in df_cli_raw.columns]
spec_cli_map = dict(zip(
    df_cli_raw['PROCESSO'].astype(str).str.strip(),
    df_cli_raw['ESPECIFICAÇÃO'].fillna('')
))

print('Carregando especificações da RPI...')
rpi_records, _, _ = load_rpi_records(XML_RPI)
spec_rpi_map = {r['processo']: r['especificacoes'] for r in rpi_records}

# ---------------------------------------------------------------------------
# Processar v3
# ---------------------------------------------------------------------------
INPUT  = './relatorio_v3/Relatorio_Colidencia_RPI_2886_28-04-2026_A_PROVINCIA.xlsx'
OUTPUT = './relatorio_v3/Relatorio_Analisado_IA_v3_RPI2886.xlsx'
PLANO  = './relatorio_v3/Plano_Correcao_Algoritmo.txt'

print('Carregando relatório v3...')
df = pd.read_excel(INPUT, header=6)
df.columns = ['PROCESSO_CLI','MARCA_CLI','CLASSE_CLI','TITULAR_CLI',
              'PROCESSO_3O','MARCA_3O','CLASSE_3O']
df = df[df['PROCESSO_CLI'] != 'PROCESSO CLIENTE'].dropna(subset=['PROCESSO_CLI'])
print(f'  {len(df)} casos')

results = []
for i, (_, row) in enumerate(df.iterrows(), 1):
    if i % 500 == 0:
        print(f'  ... {i}/{len(df)}')

    cli        = str(row['MARCA_CLI'])
    rpi_n      = str(row['MARCA_3O'])
    cl_cli     = get_class_num(str(row['CLASSE_CLI']))
    cl_rpi_str = str(row['CLASSE_3O'])
    cls_rpi    = [get_class_num(x) for x in cl_rpi_str.split(',')]
    proc_cli   = str(row['PROCESSO_CLI']).strip()
    proc_3o    = str(row['PROCESSO_3O']).strip()
    cl_rpi_cod = str(cls_rpi[0]) if cls_rpi else ''

    espec_cli = spec_cli_map.get(proc_cli, '')
    espec_rpi_d = spec_rpi_map.get(proc_3o, {})
    espec_rpi = espec_rpi_d.get(cl_rpi_cod, '') or next(iter(espec_rpi_d.values()), '')

    analise = analisar_advogado(cli, rpi_n, cl_cli, cls_rpi, espec_cli, espec_rpi)

    results.append({
        'PROCESSO CLIENTE':   row['PROCESSO_CLI'],
        'MARCA CLIENTE':      cli,
        'CLASSE CLIENTE':     row['CLASSE_CLI'],
        'TITULAR CLIENTE':    row['TITULAR_CLI'],
        'PROCESSO TERCEIRO':  row['PROCESSO_3O'],
        'MARCA TERCEIRO':     rpi_n,
        'CLASSE TERCEIRO':    row['CLASSE_3O'],
        **analise,
    })

df_out = pd.DataFrame(results)
df_out = df_out.sort_values(['PRIORIDADE', 'SCORE_NOME'], ascending=[True, False])

# ---------------------------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------------------------
print()
contagem = df_out['VEREDITO'].value_counts()
print('=== DISTRIBUIÇÃO DE VEREDITOS ===')
for v, cnt in contagem.items():
    print(f'  {v:<20} {cnt:>5} ({cnt/len(df_out)*100:.1f}%)')

print()
print('=== TOP 15 ALTO_RISCO ===')
for _, r in df_out[df_out['VEREDITO']=='ALTO_RISCO'].head(15).iterrows():
    print(f"  [{r['SCORE_NOME']:.3f} spec={r['SCORE_SPEC']}] cl{r['CLASSE CLIENTE'][-2:]}  "
          f"{r['MARCA CLIENTE']!r:40} x {r['MARCA TERCEIRO']!r}")

# ---------------------------------------------------------------------------
# Plano de correção
# ---------------------------------------------------------------------------
fp_por_motivo = Counter()
for _, r in df_out[df_out['VEREDITO']=='FALSO_POSITIVO'].iterrows():
    m = r['MOTIVO_IA']
    if 'incompatíveis' in m:
        fp_por_motivo['Spec incompatível mas spec gate não bloqueou'] += 1
    elif 'borderline' in m or 'pouco similar' in m:
        fp_por_motivo['Score baixo remanescente'] += 1
    elif 'Token distintivo' in m:
        fp_por_motivo['Token coincidente sem contexto'] += 1
    else:
        fp_por_motivo['Outros'] += 1

baixo_analise = Counter()
for _, r in df_out[df_out['VEREDITO']=='BAIXO_RISCO'].iterrows():
    sc = r['SCORE_NOME']
    if sc < 0.55:
        baixo_analise['score < 0.55 (borderline)'] += 1
    elif r['SCORE_SPEC'] == 'N/D':
        baixo_analise['sem spec — só fonética'] += 1
    else:
        baixo_analise['baixo risco legítimo'] += 1

plano = f"""
=======================================================================
PLANO DE CORREÇÃO DO ALGORITMO — RPI 2886
Gerado automaticamente pela análise IA v3
=======================================================================

RESUMO DOS RESULTADOS (v3)
  Total de colidências detectadas : {len(df_out)}
  ALTO_RISCO                       : {contagem.get('ALTO_RISCO', 0)}
  MEDIO_RISCO                      : {contagem.get('MEDIO_RISCO', 0)}
  BAIXO_RISCO                      : {contagem.get('BAIXO_RISCO', 0)}
  FALSO_POSITIVO                   : {contagem.get('FALSO_POSITIVO', 0)}

EVOLUÇÃO DAS VERSÕES
  v1 (original)          : 60.203 colidências
  v2 (filtro tokens)     : 12.576 colidências  (-79%)
  v3 (portão de spec)    :  7.248 colidências  (-88% total)
  Após análise IA        :  {contagem.get('ALTO_RISCO',0) + contagem.get('MEDIO_RISCO',0)} casos relevantes
                            ({(contagem.get('ALTO_RISCO',0)+contagem.get('MEDIO_RISCO',0))/len(df_out)*100:.1f}% do v3)

=======================================================================
PROBLEMA 1 — Casos BAIXO_RISCO em excesso ({contagem.get('BAIXO_RISCO',0)} casos)
=======================================================================

CAUSA RAIZ:
  Marcas em mesma classe com score moderado (0.55–0.75) onde a spec
  não está disponível ou tem sobreposição parcial. O engine não tem como
  determinar se os produtos/serviços competem diretamente.

CORREÇÃO PROPOSTA:
  A) Exigir spec mínima de ambos os lados para manter no relatório.
     Se spec ausente E score < 0.70 E classe correlata (não mesma) → descartar.
  B) Ampliar o parser de specs: muitos registros têm spec vazia no XML
     mas têm descrição no despacho. Parsear campo <complemento> do XML.
  C) Elevar threshold de R4b (núcleo similar) de 0.75 para 0.78 para
     classe correlata (não mesma).

IMPACTO ESTIMADO: reduzir ~2.000–3.000 casos BAIXO_RISCO.

=======================================================================
PROBLEMA 2 — Falsos positivos remanescentes ({contagem.get('FALSO_POSITIVO',0)} casos)
=======================================================================

SUBCATEGORIAS:
{chr(10).join(f'  - {k}: {v}' for k, v in fp_por_motivo.most_common())}

CAUSA RAIZ:
  O portão de spec bloqueia quando AMBAS as specs têm >= 2 tokens.
  Quando uma das specs é muito curta (ex: "e serviços;"), o portão
  não se aplica e o caso passa pela análise fonética.

CORREÇÃO PROPOSTA:
  A) Reduzir _SPEC_MIN_TOKENS de 2 para 1 — specs de 1 token já
     são suficientes para determinar incompatibilidade.
  B) Adicionar parse de despachos INPI (campo <despacho>) para
     inferir spec quando ausente: código 1.1 = pedido de registro,
     código 6.1 = concessão, etc.
  C) Para specs em inglês (comuns em marcas internacionais), aplicar
     tradução de termos frequentes antes do overlap.

IMPACTO ESTIMADO: reduzir ~150–200 falsos positivos.

=======================================================================
PROBLEMA 3 — Casos sem spec disponível (N/D)
=======================================================================

CAUSA RAIZ:
  Parte dos registros da RPI tem <especificacao> vazia no XML.
  Sem spec, o portão não funciona e o sistema depende só da fonética.

CORREÇÃO PROPOSTA:
  A) Usar a classe Nice + subclasse (ex: 35/10) como proxy de spec:
     construir uma matriz de subclasses Nice que indica compatibilidade
     mais granular que a classe principal.
  B) Enriquecer a base de clientes com subclasse do INPI (campo CLASSE
     já tem "35/10" — extrair e usar como filtro adicional).

IMPACTO ESTIMADO: melhorar precisão em ~30% dos casos sem spec.

=======================================================================
PRIORIDADE DE IMPLEMENTAÇÃO
=======================================================================

  P1 (imediato): Correção B do Problema 1 — parsear <complemento> do XML
  P2 (curto):    Correção A do Problema 2 — _SPEC_MIN_TOKENS = 1
  P3 (médio):    Correção A do Problema 3 — subclasse Nice como proxy
  P4 (longo):    Tradução de specs em inglês para comparação

=======================================================================
AÇÃO IMEDIATA RECOMENDADA PARA O ADVOGADO
=======================================================================

  1. Revisar os {contagem.get('ALTO_RISCO',0)} casos ALTO_RISCO — oposição a avaliar
  2. Revisar os {contagem.get('MEDIO_RISCO',0)} casos MEDIO_RISCO — monitoramento ativo
  3. Ignorar BAIXO_RISCO e FALSO_POSITIVO nesta RPI
  4. Devolver lista de termos comuns confirmados (arquivo Termos_Candidatos_Comuns.xlsx)
     para atualizar _TOKENS_DESCRITORES e reprocessar

"""

with open(PLANO, 'w', encoding='utf-8') as f:
    f.write(plano)
print(plano)

# ---------------------------------------------------------------------------
# Salvar Excel
# ---------------------------------------------------------------------------
print(f'Salvando {OUTPUT} ...')
with pd.ExcelWriter(OUTPUT, engine='openpyxl') as writer:
    df_out.to_excel(writer, index=False, sheet_name='Análise IA v3')

    from openpyxl.styles import PatternFill, Font, Alignment
    ws = writer.sheets['Análise IA v3']

    cores = {
        'ALTO_RISCO':    'FF9999',
        'MEDIO_RISCO':   'FFE599',
        'BAIXO_RISCO':   'B7E1CD',
        'FALSO_POSITIVO':'D9D9D9',
    }
    hf = PatternFill('solid', fgColor='1F3864')
    for cell in ws[1]:
        cell.fill = hf
        cell.font = Font(color='FFFFFF', bold=True)
        cell.alignment = Alignment(horizontal='center', wrap_text=True)

    col_v = next(c.column for c in ws[1] if c.value == 'VEREDITO')
    for row in ws.iter_rows(min_row=2):
        v    = row[col_v - 1].value or ''
        fill = PatternFill('solid', fgColor=cores.get(v, 'FFFFFF'))
        for cell in row:
            cell.fill = fill
            cell.alignment = Alignment(wrap_text=True, vertical='top')
        row[col_v - 1].font = Font(bold=True)

    widths = {
        'PROCESSO CLIENTE':16, 'MARCA CLIENTE':38, 'CLASSE CLIENTE':14,
        'TITULAR CLIENTE':36, 'PROCESSO TERCEIRO':16, 'MARCA TERCEIRO':38,
        'CLASSE TERCEIRO':14, 'VEREDITO':16, 'PRIORIDADE':10,
        'SCORE_NOME':11, 'SCORE_NUCLEO':12, 'SCORE_SPEC':11, 'TOKEN_DIST':20,
        'ESPEC_CLIENTE':48, 'ESPEC_TERCEIRO':48, 'MOTIVO_IA':85,
    }
    for col in ws.iter_cols(1, ws.max_column):
        h = col[0].value
        ws.column_dimensions[col[0].column_letter].width = widths.get(h, 14)
        for cell in col[1:]:
            cell.alignment = Alignment(wrap_text=True, vertical='top')

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

print('Concluído.')
