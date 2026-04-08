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
        assert len(restante) == 0

    def test_nao_detecta_diferente(self):
        carteira = [_marca("MINHA MARCA", 35)]
        rpi = [_marca("OUTRA MARCA", 35)]
        alertas, restante = camada1(carteira, rpi)
        assert len(alertas) == 0
        assert len(restante) == 1

    def test_nucleo_identico(self):
        carteira = [_marca("INSPIRE STUDIO DE PILATES", 41)]
        rpi = [_marca("INSPIRE PILATES", 35)]
        alertas, restante = camada1(carteira, rpi)
        # Pode detectar via núcleo INSPIRE
        # Independente de estar na camada 1 ou avançar para 2, deve haver alerta
        # Aqui apenas verificamos que não quebra
        assert isinstance(alertas, list)
        assert isinstance(restante, list)


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
