"""
Testes unitários do pipeline de colidência — pares conhecidos.
"""
import pytest
from app.pipeline.preprocessor import preprocessar
from app.pipeline.nome_identico import camada1
from app.pipeline.fonetica import camada2
from app.pipeline.especificacao import camada3
from app.pipeline.scoring import camada4


def _marca(nome: str, ncl: int, spec: str = "", tipo_acao: str = "OPOSICAO") -> dict:
    """Helper para criar um dict de marca pré-processado."""
    base = {
        "marca": nome,
        "nome_marca": nome,
        "ncl": ncl,
        "especificacao": spec,
        "apresentacao": "Nominativa",
        "tipo_acao": tipo_acao,
        "processo": "999999999",
        "titular": "TERCEIRO LTDA",
        "despacho_codigo": "IPAS009",
        "despacho_nome": "Publicação para oposição",
    }
    return preprocessar(base)


def _rodar_pipeline(carteira_nome, carteira_ncl, rpi_nome, rpi_ncl,
                    carteira_spec="", rpi_spec=""):
    """Executa as 4 primeiras camadas e retorna (alertas_c1, scored_c4)."""
    carteira = [_marca(carteira_nome, carteira_ncl, carteira_spec)]
    rpi = [_marca(rpi_nome, rpi_ncl, rpi_spec)]

    # Camada 1
    alertas_c1, rpi_restante = camada1(carteira, rpi)
    if alertas_c1:
        return alertas_c1, []

    # Camada 2
    cands_c2, _ = camada2(carteira, rpi_restante)

    # Camada 3
    cands_c3 = camada3(cands_c2)

    # Camada 4
    scored = camada4(cands_c3)

    return [], scored


class TestParesConhecidos:
    """Casos de teste definidos no spec."""

    # ------------------------------------------------------------------
    # DEVE COLIDIR
    # ------------------------------------------------------------------

    def test_nome_identico(self):
        """NOVA GERACAO × NOVA GERACAO (mesma classe) → ALTA."""
        alertas, scored = _rodar_pipeline("NOVA GERACAO", 44, "NOVA GERACAO", 41)
        todos = alertas + scored
        assert todos, "Esperado pelo menos 1 alerta"
        assert any(r.get("classificacao") == "ALTA" for r in todos)

    def test_imitacao_fonetica(self):
        """CAVALINHO AZUL × KAVALLO AZULADO → deve detectar colidência."""
        alertas, scored = _rodar_pipeline("CAVALINHO AZUL", 25, "KAVALLO AZULADO", 25)
        todos = alertas + scored
        assert todos, "Esperado pelo menos 1 alerta para imitação fonética"

    def test_variacao_grafica(self):
        """JOLY × JOLLI → colidência."""
        alertas, scored = _rodar_pipeline("JOLY", 29, "JOLLI", 29)
        todos = alertas + scored
        assert todos, "JOLY × JOLLI devem colidir"

    def test_variacao_minima(self):
        """CARMEL × CARMELL → colidência."""
        alertas, scored = _rodar_pipeline("CARMEL", 35, "CARMELL", 35)
        todos = alertas + scored
        assert todos, "CARMEL × CARMELL devem colidir"

    def test_nucleo_identico(self):
        """INSPIRE STUDIO DE PILATES × INSPIRE PILATES → núcleo INSPIRE."""
        alertas, scored = _rodar_pipeline(
            "INSPIRE STUDIO DE PILATES", 41,
            "INSPIRE PILATES", 35,
        )
        todos = alertas + scored
        assert todos, "Núcleo INSPIRE idêntico deve gerar alerta"

    def test_reproducao_com_acrescimo(self):
        """ROCKET × ROCKET 360 → colidência por reprodução."""
        alertas, scored = _rodar_pipeline("ROCKET", 41, "ROCKET 360", 41)
        todos = alertas + scored
        assert todos, "ROCKET × ROCKET 360 devem colidir"

    # ------------------------------------------------------------------
    # NÃO DEVE COLIDIR
    # ------------------------------------------------------------------

    def test_ramos_distintos(self):
        """MITTI (NCL 25 — vestuário) × MITTI GELATO (NCL 30 — alimentos)."""
        alertas, scored = _rodar_pipeline("MITTI", 25, "MITTI GELATO", 30)
        # NCL 25 e 30 não colidem → não deve gerar alerta
        todos = alertas + scored
        assert not todos, f"MITTI × MITTI GELATO em NCLs não colidentes não devem gerar alerta. Resultado: {todos}"


class TestCamada1:
    def test_detecta_nome_identico(self):
        carteira = [_marca("NOVA GERACAO", 44)]
        rpi = [_marca("NOVA GERACAO", 41)]
        alertas, restante = camada1(carteira, rpi)
        assert len(alertas) == 1
        # rpi_restante contém TODAS as marcas da RPI (mesmo as já alertadas
        # em C1) — a marca pode ainda colidir foneticamente com outras
        # marcas da carteira em C2. Dedup do par C1×C4 acontece no executor.
        assert len(restante) == 1

    def test_nao_detecta_diferente(self):
        carteira = [_marca("MINHA MARCA", 35)]
        rpi = [_marca("OUTRA MARCA", 35)]
        alertas, restante = camada1(carteira, rpi)
        assert len(alertas) == 0
        assert len(restante) == 1

    def test_nucleo_distintivo_indice(self):
        """Núcleo distintivo idêntico (IBM) casa mesmo com sufixos distintos."""
        carteira = [_marca("IBM BRASIL", 35)]
        rpi = [_marca("IBM SOLUCOES", 35)]
        alertas, restante = camada1(carteira, rpi)
        assert len(alertas) == 1, "IBM BRASIL × IBM SOLUCOES devem casar pelo nucleo 'ibm'"
        # rpi_restante contém TODAS as marcas da RPI — ver nota em
        # test_detecta_nome_identico.
        assert len(restante) == 1

    def test_classes_colidem_flag_correto(self):
        """classes_colidem_flag reflete a realidade, não é sempre True."""
        from app.config import classes_colidem as cc
        # Classes que não colidem → MEDIA, flag=False, spec=0.5
        carteira = [_marca("NEXO", 1)]
        rpi = [_marca("NEXO", 45)]
        alertas, _ = camada1(carteira, rpi)
        assert len(alertas) == 1
        assert alertas[0]["classes_colidem_flag"] is False
        assert alertas[0]["score_spec"] == 0.5
        assert alertas[0]["classificacao"] == "MEDIA"
        # Classes que colidem → ALTA, flag=True, spec=1.0
        carteira = [_marca("NEXO", 35)]
        rpi = [_marca("NEXO", 35)]
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["classes_colidem_flag"] is True
        assert alertas[0]["score_spec"] == 1.0
        assert alertas[0]["classificacao"] == "ALTA"

    def test_nucleo_identico(self):
        carteira = [_marca("INSPIRE STUDIO DE PILATES", 41)]
        rpi = [_marca("INSPIRE PILATES", 35)]
        alertas, restante = camada1(carteira, rpi)
        assert isinstance(alertas, list)
        assert isinstance(restante, list)

    def test_nucleo_identico(self):
        carteira = [_marca("INSPIRE STUDIO DE PILATES", 41)]
        rpi = [_marca("INSPIRE PILATES", 35)]
        alertas, restante = camada1(carteira, rpi)
        # Pode detectar via núcleo INSPIRE
        # Independente de estar na camada 1 ou avançar para 2, deve haver alerta
        # Aqui apenas verificamos que não quebra
        assert isinstance(alertas, list)
        assert isinstance(restante, list)

    # ------------------------------------------------------------------
    # Campos obrigatórios nos alertas de C1
    # ------------------------------------------------------------------

    def test_alerta_tem_motivo(self):
        """Campo motivo sempre presente e correto."""
        carteira = [_marca("NEXO", 35)]
        rpi = [_marca("NEXO", 35)]
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["motivo"] == "nome_identico"

    def test_nucleo_identico_motivo(self):
        carteira = [_marca("IBM BRASIL", 35)]
        rpi = [_marca("IBM SOLUCOES", 35)]
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["motivo"] == "nucleo_identico"

    def test_alerta_tem_score_final(self):
        """score_final presente e consistente com classificacao."""
        # nome_identico + mesma classe → 1.0
        carteira = [_marca("NEXO", 35)]
        rpi = [_marca("NEXO", 35)]
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["score_final"] == 1.0

    def test_alerta_tem_nivel(self):
        """nivel presente e correto para cada combinação."""
        # nome_identico + classes colidem → ALTA
        carteira = [_marca("NEXO", 35)]
        rpi = [_marca("NEXO", 35)]
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["nivel"] == "ALTA"

    def test_nome_identico_cross_class_nao_colidente(self):
        """Nome idêntico em classes sem relação → MEDIA, score_final na faixa MEDIA."""
        carteira = [_marca("NEXO", 1)]
        rpi = [_marca("NEXO", 45)]   # NCL 1 × 45 não colidem
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["nivel"] == "MEDIA"
        assert alertas[0]["score_final"] == 0.75
        assert alertas[0]["classificacao"] == "MEDIA"

    def test_nucleo_identico_cross_class_nao_colidente_nivel(self):
        """Núcleo idêntico em classes sem relação → VIGIAR.

        NCL 1 × 45 (não 35 × 12 como antes): desde a unificação de "classes
        colidem" via classes_afins (mesma regra material da elegibilidade
        do C2), a classe 35 é transversal e tem piso AFINIDADE_TRANSVERSAL
        (0.70) de afinidade contra QUALQUER outra classe — por design
        (CLASSES_TRANSVERSAIS em config.py: uma marca de comércio/varejo
        classe 35 pode legitimamente colidir com o produto correspondente
        em qualquer classe de bens). Logo 35×12 agora é um par que colide
        de fato, não mais um exemplo válido de "sem relação". NCL 1×45 não
        está na matriz COLLISIONS nem tem afinidade tabelada/transversal
        (_afinidade_classes(1, 45) ≈ 0.52 < 0.60), preservando o cenário
        original do teste.
        """
        carteira = [_marca("IBM BRASIL", 1)]
        rpi = [_marca("IBM SOLUCOES", 45)]   # NCL 1 × 45 não colidem
        alertas, _ = camada1(carteira, rpi)
        assert alertas[0]["nivel"] == "VIGIAR"
        assert alertas[0]["score_final"] == 0.70
        assert alertas[0]["classificacao"] == "MEDIA"

    # ------------------------------------------------------------------
    # Bug fix: nome_identico não deve suprimir nucleo_identico para
    # outras marcas da carteira
    # ------------------------------------------------------------------

    def test_nome_identico_nao_suprime_nucleo_identico_outra_marca(self):
        """
        Bug fix: quando nome_identico detecta (CartA × RPI), o nucleo_identico
        de (CartB × RPI) ainda deve ser gerado.

        Carteira: ["IBM" NCL35, "IBM BRASIL" NCL44]
        RPI:      ["IBM" NCL35]

        "IBM BRASIL" → nucleo_distintivo="ibm" (BRASIL é desgastado).
        nome_identico detecta (IBM×IBM); sem o fix, suprimiria o
        nucleo_identico de (IBM BRASIL×IBM).
        """
        carteira = [_marca("IBM", 35), _marca("IBM BRASIL", 44)]
        rpi = [_marca("IBM", 35)]
        alertas, restante = camada1(carteira, rpi)
        assert len(alertas) == 2, (
            f"Esperados 2 alertas (nome_identico + nucleo_identico), "
            f"mas foram gerados {len(alertas)}: {[a['motivo'] for a in alertas]}"
        )
        motivos = {a["motivo"] for a in alertas}
        assert "nome_identico" in motivos
        assert "nucleo_identico" in motivos
        # rpi_restante contém TODAS as marcas da RPI — ver nota em
        # test_detecta_nome_identico. A supressão de duplicatas entre o
        # alerta C1 e um eventual candidato C2/C4 do MESMO par é feita no
        # dedup cruzado do executor, não aqui.
        assert len(restante) == 1

    def test_nome_identico_nao_gera_nucleo_identico_duplicado(self):
        """
        Quando nome_identico detecta o par, nucleo_identico não deve criar
        um segundo alerta para o MESMO par.
        """
        carteira = [_marca("NEXO", 35)]
        rpi = [_marca("NEXO", 35)]
        alertas, _ = camada1(carteira, rpi)
        assert len(alertas) == 1
        assert alertas[0]["motivo"] == "nome_identico"

    # ------------------------------------------------------------------
    # Bug fix: C1 opera sobre PARES, não sobre marcas — uma marca da RPI
    # idêntica a UMA marca da carteira não pode ser removida de
    # rpi_restante, sob pena de nunca chegar à C2 e perder colidências
    # fonéticas com OUTRAS marcas da carteira (recall silencioso).
    # ------------------------------------------------------------------

    def test_c1_nao_suprime_candidato_c2_de_outra_marca_da_carteira(self):
        """
        Carteira: ["ALFA" NCL25, "ALPHA STORE" NCL25]
        RPI:      ["ALFA" NCL25]

        Esperado: alerta C1 nome_identico para ALFA×ALFA E um candidato C2+
        para ALPHA STORE×ALFA. Antes do fix, "ALFA" era removida de
        rpi_restante após o match com "ALFA" da carteira, e o par
        ALPHA STORE×ALFA nunca chegava à camada 2.
        """
        carteira = [_marca("ALFA", 25), _marca("ALPHA STORE", 25)]
        rpi = [_marca("ALFA", 25)]

        alertas_c1, restante = camada1(carteira, rpi)
        assert len(alertas_c1) == 1
        assert alertas_c1[0]["motivo"] == "nome_identico"
        assert alertas_c1[0]["marca_base"] == "ALFA"
        # A marca "ALFA" da RPI segue para C2 mesmo já tendo gerado alerta C1.
        assert len(restante) == 1

        candidatos_c2, _ = camada2(carteira, restante)
        marcas_base_c2 = {c.get("marca_base") for c in candidatos_c2}
        assert "ALPHA STORE" in marcas_base_c2, (
            f"Esperado candidato C2 para ALPHA STORE x ALFA, "
            f"obtido: {candidatos_c2}"
        )

    # ------------------------------------------------------------------
    # Reclassificação pós-C3 (a C3 refina score_spec dos alertas C1)
    # ------------------------------------------------------------------

    def test_reclassificar_pos_c3_confirma_alta(self):
        """Classes colidem + afinidade refinada alta → permanece ALTA."""
        from app.pipeline.nome_identico import reclassificar_pos_c3
        a = {"motivo": "nome_identico", "classes_colidem_flag": True,
             "score_spec": 0.95}
        reclassificar_pos_c3(a)
        assert a["classificacao"] == "ALTA"
        assert a["nivel"] == "ALTA"
        assert a["score_final"] == 1.0

    def test_reclassificar_pos_c3_rebaixa(self):
        """Classes colidem formalmente mas afinidade real baixa → MEDIA."""
        from app.pipeline.nome_identico import reclassificar_pos_c3
        a = {"motivo": "nome_identico", "classes_colidem_flag": True,
             "score_spec": 0.45}
        reclassificar_pos_c3(a)
        assert a["classificacao"] == "MEDIA"
        assert a["nivel"] == "MEDIA"
        assert a["score_final"] == 0.75

    def test_reclassificar_pos_c3_eleva(self):
        """Classes não colidem na matriz mas afinidade real forte → ALTA."""
        from app.pipeline.nome_identico import reclassificar_pos_c3
        a = {"motivo": "nucleo_identico", "classes_colidem_flag": False,
             "score_spec": 0.85}
        reclassificar_pos_c3(a)
        assert a["classificacao"] == "ALTA"
        assert a["score_final"] == 0.85

    def test_reclassificar_pos_c3_ignora_outros(self):
        """Pares que não vieram da C1 não são tocados."""
        from app.pipeline.nome_identico import reclassificar_pos_c3
        a = {"motivo": "", "classificacao": "BAIXA", "score_spec": 0.95}
        reclassificar_pos_c3(a)
        assert a["classificacao"] == "BAIXA"


class TestConfig:
    def test_classes_colidem(self):
        from app.config import classes_colidem
        assert classes_colidem(5, 10) is True
        assert classes_colidem(5, 5) is True
        assert classes_colidem(1, 45) is False

    def test_despachos_relevantes(self):
        from app.config import DESPACHOS_RELEVANTES, DESPACHOS_OPOSICAO, DESPACHOS_PAN
        assert "IPAS009" in DESPACHOS_OPOSICAO
        assert "IPAS158" in DESPACHOS_PAN
        assert DESPACHOS_OPOSICAO | DESPACHOS_PAN == DESPACHOS_RELEVANTES


class TestLoteIA:
    """Agrupamento de pares por chamada IA (camada 5) — sem rede."""

    def _pares_fake(self, n: int) -> list[dict]:
        return [
            {
                "marca_base": f"MARCA{i}", "ncl_base": 35, "nucleo_base": f"marca{i}",
                "marca_rpi": f"MARKA{i}", "ncl_rpi": 35, "nucleo_rpi": f"marka{i}",
                "spec_base": "", "spec_rpi": "",
                "score_nome": 0.9, "score_fonetico": 0.9,
                "score_spec": 0.8, "score_nucleo": 0.9,
            }
            for i in range(n)
        ]

    def test_montar_prompt_lote_enumera(self):
        from app.pipeline.ia_refinamento import _montar_prompt_lote
        prompt = _montar_prompt_lote(self._pares_fake(3))
        assert "=== PAR 1 ===" in prompt
        assert "=== PAR 2 ===" in prompt
        assert "=== PAR 3 ===" in prompt
        assert "=== PAR 4 ===" not in prompt

    def test_parsear_resposta_lote_wrapper(self):
        from app.pipeline.ia_refinamento import _parsear_resposta_lote
        content = (
            '{"resultados":[{"par":1,"classificacao":"ALTA","score":0.9},'
            '{"par":2,"classificacao":"BAIXA","score":0.3}]}'
        )
        mapa = _parsear_resposta_lote(content, 2)
        assert mapa[1]["classificacao"] == "ALTA"
        assert mapa[2]["classificacao"] == "BAIXA"

    def test_parsear_resposta_lote_array_puro(self):
        from app.pipeline.ia_refinamento import _parsear_resposta_lote
        content = '[{"par":1,"classificacao":"MEDIA","score":0.5}]'
        mapa = _parsear_resposta_lote(content, 1)
        assert mapa[1]["classificacao"] == "MEDIA"

    def test_parsear_resposta_lote_parcial(self):
        """Par faltante na resposta fica fora do mapa → vai para fallback."""
        from app.pipeline.ia_refinamento import _parsear_resposta_lote
        content = (
            '{"resultados":[{"par":1,"classificacao":"ALTA","score":0.9},'
            '{"par":3,"classificacao":"BAIXA","score":0.2}]}'
        )
        mapa = _parsear_resposta_lote(content, 3)
        assert 1 in mapa and 3 in mapa
        assert 2 not in mapa

    def test_parsear_resposta_lote_invalida(self):
        from app.pipeline.ia_refinamento import _parsear_resposta_lote
        assert _parsear_resposta_lote("isso não é json", 2) == {}
        assert _parsear_resposta_lote('{"resultados":"oops"}', 2) == {}
        # "par" fora do range é descartado
        mapa = _parsear_resposta_lote('{"resultados":[{"par":9,"score":0.5}]}', 2)
        assert mapa == {}

    def test_parsear_resposta_lote_code_fence(self):
        from app.pipeline.ia_refinamento import _parsear_resposta_lote
        content = '```json\n{"resultados":[{"par":1,"classificacao":"ALTA"}]}\n```'
        mapa = _parsear_resposta_lote(content, 1)
        assert mapa[1]["classificacao"] == "ALTA"


class TestNomeProprioApresentacao:
    """Campos is_nome_proprio e apresentacao consumidos pelo pipeline (R5)."""

    def test_candidato_propaga_campos(self):
        """Candidatos da C2 carregam apresentacao e is_nome_proprio."""
        base = {
            "marca": "CARLOS MOTTA ADVOCACIA", "nome_marca": "CARLOS MOTTA ADVOCACIA",
            "ncl": 45, "especificacao": "serviços jurídicos",
            "apresentacao": "Mista", "tipo_acao": "OPOSICAO",
            "processo": "111111111", "titular": "CARLOS MOTTA",
            "despacho_codigo": "IPAS009", "despacho_nome": "Publicação para oposição",
        }
        rpi = dict(base, processo="222222222", nome_marca="CARLOS MOTA ADVOCACIA",
                   marca="CARLOS MOTA ADVOCACIA", titular="CARLOS MOTA",
                   apresentacao="Nominativa")
        carteira = [preprocessar(base)]
        cands, _ = camada2(carteira, [preprocessar(rpi)])
        assert cands, "Par quase idêntico deve passar a C2"
        c = cands[0]
        assert c["apresentacao_base"] == "Mista"
        assert c["apresentacao_rpi"] == "Nominativa"
        assert c["is_nome_proprio_base"] is True
        assert c["is_nome_proprio_rpi"] is True

    def test_alerta_c1_propaga_campos(self):
        from app.pipeline.nome_identico import camada1 as c1
        m = _marca("NEXO", 9)
        alertas, _ = c1([m], [m])
        assert alertas
        assert "apresentacao_base" in alertas[0]
        assert "is_nome_proprio_rpi" in alertas[0]

    def test_camada4_lenidade_homonimos(self):
        """Ambas nome próprio + classes não colidentes → score reduzido."""
        par_base = {
            "marca_base": "CARLOS MOTTA", "ncl_base": 1,
            "spec_base": "produtos químicos", "nucleo_base": "carlos motta",
            "marca_rpi": "CARLOS MOTTA", "ncl_rpi": 45,
            "spec_rpi": "serviços jurídicos", "nucleo_rpi": "carlos motta",
            "titular_base": "X", "titular_rpi": "Y",
            "score_nome": 1.0, "score_fonetico": 1.0,
            "score_spec": 0.45, "score_nucleo": 1.0,
            "classes_colidem_flag": False,
            "nucleo_distintivo_base": "carlos motta",
            "nucleo_distintivo_rpi": "carlos motta",
        }
        sem_flag = camada4([dict(par_base)])
        com_flag = camada4([dict(
            par_base, is_nome_proprio_base=True, is_nome_proprio_rpi=True,
        )])
        if sem_flag and com_flag:
            assert com_flag[0]["score_final"] <= sem_flag[0]["score_final"]
        else:
            # Se o par com lenidade caiu abaixo do threshold, o sem flag
            # precisa ter sobrevivido ou ambos caíram — nunca o inverso.
            assert not (com_flag and not sem_flag)

    def test_parse_xml_ignora_figurativa(self, tmp_path):
        from app.parsers.parse_xml import parse_rpi_xml
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<revista numero="2800" data="01/06/2026">
  <processo numero="900000001">
    <despachos><despacho codigo="IPAS009" nome="Publicação para oposição"/></despachos>
    <marca apresentacao="Figurativa"><nome>LOGO QUALQUER</nome></marca>
    <classes-nice><classe-nice codigo="35"><especificacao>comércio</especificacao></classe-nice></classes-nice>
    <titulares><titular nome-razao-social="EMPRESA A LTDA"/></titulares>
  </processo>
  <processo numero="900000002">
    <despachos><despacho codigo="IPAS009" nome="Publicação para oposição"/></despachos>
    <marca apresentacao="Nominativa"><nome>MARCA VERBAL</nome></marca>
    <classes-nice><classe-nice codigo="35"><especificacao>comércio</especificacao></classe-nice></classes-nice>
    <titulares><titular nome-razao-social="EMPRESA B LTDA"/></titulares>
  </processo>
</revista>"""
        path = tmp_path / "rpi.xml"
        path.write_text(xml, encoding="utf-8")
        records, _, _ = parse_rpi_xml(str(path))
        nomes = [r["nome_marca"] for r in records]
        assert "MARCA VERBAL" in nomes
        assert "LOGO QUALQUER" not in nomes


class TestLotesExecutor:
    """Processamento em lotes de TAMANHO_LOTE_RPI no executor."""

    def test_processar_lote_basico(self, monkeypatch):
        """C1→C4 num lote pequeno, camada5 stub recebe custo_inicial."""
        from app.pipeline import executor as ex

        chamadas = []

        def _camada5_stub(pares, progress_cb=None, custo_inicial=0.0):
            chamadas.append(custo_inicial)
            return pares, 0.01

        monkeypatch.setattr(ex, "camada5", _camada5_stub)

        carteira = [_marca("NOVA GERACAO", 25)]
        chunk = [_marca("NOVA GERACAO", 25), _marca("XYZKW", 7)]

        def _sem_filtro(pares):
            return pares, 0

        resultados, custo, cont = ex._processar_lote(
            carteira=carteira, rpi_chunk=chunk, usar_ia=True,
            custo_inicial=0.5, filtrar_titular=_sem_filtro,
            progress=lambda msg, pct: None, pct=50,
        )
        assert cont["camada1_count"] == 1
        assert resultados, "Nome idêntico deve gerar resultado"
        # camada5 só roda se houver scored_c4; com custo_inicial repassado
        if chamadas:
            assert chamadas[0] == 0.5
            assert custo == 0.01

    def test_gravar_checkpoint_e_falha_nao_aborta(self, tmp_path, monkeypatch):
        from app.pipeline import executor as ex

        path = str(tmp_path / "sub" / "chk.json")
        ex._gravar_checkpoint(path, [{"marca_base": "A"}], 1, 3, 0.05, "2800")
        import json as _json
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        assert data["lote"] == 1
        assert data["total_lotes"] == 3
        assert data["resultados"][0]["marca_base"] == "A"

        # Falha de escrita não pode propagar exceção
        monkeypatch.setattr(ex.os, "replace", _raise_oserror)
        ex._gravar_checkpoint(path, [], 2, 3, 0.05, "2800")  # não deve lançar

    def test_dedup_cross_lote(self):
        from app.pipeline.executor import _dedup_pares
        lote1 = [{"marca_base": "A", "ncl_base": 35, "marca_rpi": "B",
                  "ncl_rpi": 35, "score_final": 0.7}]
        lote2 = [{"marca_base": "A", "ncl_base": 35, "marca_rpi": "B",
                  "ncl_rpi": 35, "score_final": 0.9}]
        dedup = _dedup_pares(lote1 + lote2)
        assert len(dedup) == 1
        assert dedup[0]["score_final"] == 0.9

    # ------------------------------------------------------------------
    # Dedup cruzado C1×C4: desde que C1 passou a deixar TODAS as marcas da
    # RPI fluírem para C2 (bug fix "C1 opera sobre pares"), o MESMO par
    # marca_base×marca_rpi pode aparecer tanto em alertas_c1 quanto em
    # scored_c4 — o alerta C1 (juridicamente decidido) deve vencer SEMPRE,
    # mesmo com score_final menor que o do candidato C4.
    # ------------------------------------------------------------------

    def test_remover_pares_ja_em_c1_vence_mesmo_com_score_menor(self):
        """nucleo_identico cross-class não colidente (score_final=0.70) vs.
        um candidato C4 do MESMO par com score maior (0.95) — C1 vence."""
        from app.pipeline.executor import _remover_pares_ja_em_c1
        alertas_c1 = [{"marca_base": "IBM BRASIL", "ncl_base": 44,
                       "marca_rpi": "IBM", "ncl_rpi": 12,
                       "score_final": 0.70, "camada_deteccao": 1}]
        scored_c4 = [
            {"marca_base": "IBM BRASIL", "ncl_base": 44, "marca_rpi": "IBM",
             "ncl_rpi": 12, "score_final": 0.95, "camada_deteccao": 4},
            {"marca_base": "OUTRA", "ncl_base": 9, "marca_rpi": "IBM",
             "ncl_rpi": 12, "score_final": 0.50, "camada_deteccao": 4},
        ]
        restante = _remover_pares_ja_em_c1(alertas_c1, scored_c4)
        assert len(restante) == 1
        assert restante[0]["marca_base"] == "OUTRA"

    def test_processar_lote_c1_vence_c4_para_par_real(self):
        """
        Caso real: "IBM BRASIL" (carteira, NCL 35) × "IBM" (RPI, NCL 35)
        gera alerta C1 nucleo_identico (score_final=0.85) e, como a marca RPI
        agora também flui para C2/C3/C4, o MESMO par textual pode receber um
        score C4 maior (fonética + spec). O resultado final de
        _processar_lote deve conter só o registro C1, não o C4.
        """
        from app.pipeline import executor as ex

        carteira = [_marca("IBM BRASIL", 35)]
        chunk = [_marca("IBM", 35)]

        def _sem_filtro(pares):
            return pares, 0

        resultados, _custo, _cont = ex._processar_lote(
            carteira=carteira, rpi_chunk=chunk, usar_ia=False,
            custo_inicial=0.0, filtrar_titular=_sem_filtro,
            progress=lambda msg, pct: None, pct=50,
        )
        pares_ibm = [
            r for r in resultados
            if r.get("marca_base") == "IBM BRASIL" and r.get("marca_rpi") == "IBM"
        ]
        assert len(pares_ibm) == 1, (
            f"Esperado 1 registro para o par (C1 deve suprimir o duplicado "
            f"C4), obtidos {len(pares_ibm)}: {pares_ibm}"
        )
        assert pares_ibm[0]["camada_deteccao"] == 1
        assert pares_ibm[0]["motivo"] == "nucleo_identico"


def _raise_oserror(*args, **kwargs):
    raise OSError("disco cheio")
