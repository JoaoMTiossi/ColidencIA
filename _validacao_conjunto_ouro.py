"""
FASE 5 — Validação do score ponderado contra o conjunto-ouro de 40 casos.
Esperado: 13 falsos positivos CAEM; 5 legítimos PERMANECEM.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from colisao_rpi.engine.similarity import similarity_score, weighted_similarity
from colisao_rpi.engine.nucleus import extract_nucleus
from colisao_rpi.engine.normalize import phonetic_key
from colisao_rpi.engine.rules import (check_collision, _CONJUNTO_OVERRIDE,
    _THRESHOLD_PONDERADO_MESMA, _THRESHOLD_PONDERADO_CORRELATA)
from colisao_rpi.engine.corpus import load_corpus
from colisao_rpi.data.nice_matrix import classes_collide

import os
_corpus_path = os.path.join(os.path.dirname(__file__),
                             'colisao_rpi', 'data', 'corpus_freq.json')
corpus = load_corpus(_corpus_path)
print(f'Corpus: {sum(corpus.get("_N",{}).values())} marcas acumuladas\n')

# Conjunto-ouro: (CLI, CL_CLI, RPI, CL_RPI, SPEC_CLI, SPEC_RPI, ESPERADO)
OURO = [
    # ---- DEVE COLIDIR ----
    ('VELTI TECNOLOGIA',          35, 'VELTI TECNOLOGIA',          35,
     'comercio de aparelhos instrumentos controle',
     'consultoria suporte manutencao projetos',      'DEVE'),
    ('VET CLINICA VETERINARIA',   44, 'Vero Clinica Veterinaria',  44,
     'animais estimacao toalete criacao',
     'assistencia veterinaria clinica',              'DEVE'),
    ('FAC EMBALAGENS',            40, 'UFA EMBALAGENS',            40,
     'triagem reciclagem materiais metalicos',
     'fabricacao embalagens plasticas',              'NAO'),   # specs distintas dentro cl.40
    ('DOCERIA MI',                43, 'Maia Doceria',              43,
     'doceria fornecimento comida bebida',
     'decoracao bolos padaria cafeteria',            'NAO'),   # MI vs MAIA: núcleos distintos
    ('EDIPHARMA',                 35, 'Edith Farma',               35,
     'drogaria comercio cosmeticos',
     'comercio cosmeticos escovas',                  'DEVE'),
    ('AIKA',                      35, 'RAYKA',                     35,
     'comercio lubrificantes materia tintorial',
     'comercio colchoes camas travesseiros',         'DEVE'),
    ('AGRICOL MATERIAIS',         35, 'GEL MATERIAIS',             35,
     'comercio materiais construcao',
     'comercio materiais construcao metalicos',      'DEVE'),

    # ---- NÃO DEVE COLIDIR (falsos positivos de complemento) ----
    ('AOCT CORRETORA DE SEGUROS', 36, 'AEROCAR CORRETORA DE SEGUROS', 36,
     'seguros consultoria corretagem informacoes',
     'administracao seguro saude assessoria',         'NAO'),
    ('AOCT CORRETORA DE SEGUROS', 36, 'IMA CORRETORA DE SEGUROS',  36,
     'seguros consultoria corretagem',
     'servicos corretagem seguros',                   'NAO'),
    ('AOCT CORRETORA DE SEGUROS', 36, 'HJ CORRETORA DE SEGUROS',   36,
     'seguros consultoria corretagem',
     'administracao seguro saude analise',            'NAO'),
    ('DK INFORMATICA',            35, 'CLM INFORMATICA',           35,
     'comercio equipamento processamento dados',
     'servicos pesquisas desenvolvimento',            'NAO'),
    ('STAF SISTEMAS',             42, 'ALPH SISTEMAS',             42,
     'consultoria hardware software manutencao',
     'aluguel software analise processamento',        'NAO'),
    ('AIZA ENGENHARIA',           42, 'YBA ENGENHARIA',            42,
     'arquitetura desenho plantas engenharia',
     'assessoria consultoria construcao predial',     'NAO'),
    ('TTC LOGISTICA',             39, 'K2R LOGISTICA',             39,
     'aluguel conteiner armazenagem veiculo',
     'agenciamento veiculo carga transporte',         'NAO'),
    ('LESSA MOVEIS PLANEJADOS',   20, 'RESERVA MOVEIS PLANEJADOS', 20,
     'almofadas moveis cozinha armarios',
     'aparadores armarios bancadas balcoes',          'NAO'),
    ('NIU SUSHI RESTAURANTE',     43, 'HIRO RESTAURANTE SUSHI',    43,
     'restaurantes autoservico',
     'autoservico bar bufe cafeteria restaurante',    'NAO'),
    ('ACT CONTABILIDADE',         35, 'LAMARCA CONTABILIDADE',     35,
     'contabilidade assessoria pericias',
     'administracao financeira analise gestao',       'NAO'),
    ('ACT CONTABILIDADE',         35, 'ROTA CONTABILIDADE',        36,
     'contabilidade assessoria pericias',
     'administracao financeira analise',              'NAO'),
    ('JP PNEUS AUTO CENTER',      37, 'PAULINHO PNEUS AUTO CENTER', 12,
     'manutencao veiculos assistencia tecnica',
     'amortecedores molas anti-roubo',               'NAO'),
    ('IZZA MODA FEMININA',        35, 'LA BIA MODA FEMININA',      25,
     'comercio artigos vestuario bijuteria',
     'artigos malha vestuario bermudas calcados',     'NAO'),
]

print(f'{"#":<3} {"CLI":<32} {"RPI":<32} {"CL":>4} {"sc_pond":>8} {"sc_bruto":>9} {"REGRA":<18} {"ESPERADO":<8} {"RESULTADO"}')
print('-'*145)

acertos = 0
for i, (cli, cl_c, rpi, cl_r, spec_c, spec_r, esperado) in enumerate(OURO, 1):
    nuc_c = extract_nucleus(cli)
    nuc_r = extract_nucleus(rpi)
    cl_match = any(classes_collide(cl_c, c) for c in [cl_r])

    colide, regra, score = check_collision(
        cli, nuc_c, cl_c, rpi, nuc_r, [cl_r], cl_match,
        spec_cli=spec_c, spec_rpi=spec_r, corpus=corpus
    )

    sc_pond  = weighted_similarity(cli, rpi, cl_c, corpus)
    sc_bruto = similarity_score(cli, rpi)

    resultado = 'DEVE' if colide else 'NAO'
    ok = '✓' if resultado == esperado else '✗ ERRO'
    if resultado == esperado:
        acertos += 1

    print(f'{i:<3} {cli:<32} {rpi:<32} {cl_c:>4} {sc_pond:>8.3f} {sc_bruto:>9.3f} {str(regra):<18} {esperado:<8} {ok}')

print(f'\nAcertos: {acertos}/{len(OURO)} ({acertos/len(OURO)*100:.0f}%)')
print(f'Threshold mesma={_THRESHOLD_PONDERADO_MESMA} correlata={_THRESHOLD_PONDERADO_CORRELATA}  |  Override={_CONJUNTO_OVERRIDE}')
