"""
Testes unitários para funções de normalização.
"""
import pytest
from app.utils.normalizacao import (
    bigramas,
    jaccard_bigramas,
    normalizar_base,
    normalizar_para_hash,
)


class TestNormalizacao:
    def test_remover_acentos(self):
        assert normalizar_base("Ação") == "acao"
        assert normalizar_base("Café") == "cafe"
        assert normalizar_base("São Paulo") == "sao paulo"

    def test_lowercase(self):
        assert normalizar_base("MARCA FORTE") == "marca forte"

    def test_remover_pontuacao(self):
        result = normalizar_base("A. FERNANDES CO.")
        assert "a" in result and "fernandes" in result and "co" in result
        # normalizar_para_hash remove espaços
        h = normalizar_para_hash("A. FERNANDES CO.")
        assert " " not in h

    def test_hifen_entre_palavras(self):
        assert normalizar_base("COCA-COLA") == "coca cola"

    def test_espacos_duplos(self):
        # Tokens multi-char evitam o colapso de sigla ("A B"→"AB")
        assert normalizar_base("MARCA  FORTE") == "marca forte"

    def test_hash_sem_espacos(self):
        h = normalizar_para_hash("NOVA GERACAO")
        assert " " not in h

    def test_bigramas_tamanho(self):
        bg = bigramas("CAVALINHO")
        # Todos os pares adjacentes
        assert len(bg) > 0
        for b in bg:
            assert len(b) == 2

    def test_jaccard_identicos(self):
        assert jaccard_bigramas("CAVALINHO", "CAVALINHO") == 1.0

    def test_jaccard_diferentes(self):
        assert jaccard_bigramas("CAVALINHO", "ZEBRA") < 0.3

    def test_jaccard_similares(self):
        # CAVALINHO e KAVALLO compartilham bigramas suficientes (AL, VL, etc.)
        sim = jaccard_bigramas("CAVALINHO", "KAVALLO")
        assert sim > 0.2, f"Esperado > 0.2, got {sim:.3f}"


class TestNucleoMarcario:
    def test_extrair_nucleo_com_stopword(self):
        from app.utils.nucleo_marcario import extrair_nucleo
        assert extrair_nucleo("INSPIRE STUDIO DE PILATES") == "inspire"

    def test_extrair_nucleo_sem_stopword(self):
        from app.utils.nucleo_marcario import extrair_nucleo
        assert extrair_nucleo("NOVA GERACAO") == "nova geracao"

    def test_extrair_nucleo_complemento(self):
        from app.utils.nucleo_marcario import extrair_nucleo
        # 'clinica' é complemento descritivo
        n = extrair_nucleo("INSPIRE CLINICA")
        assert n == "inspire"

    def test_is_sigla_curto(self):
        from app.utils.nucleo_marcario import is_sigla
        assert is_sigla("IBM") is True
        assert is_sigla("A") is True
        assert is_sigla("CAVALINHO") is False

    def test_is_sigla_palavra_curta_nao_e_sigla(self):
        """Palavras curtas pronunciáveis não devem ser tratadas como sigla."""
        from app.utils.nucleo_marcario import is_sigla
        assert is_sigla("NEXO") is False
        assert is_sigla("CASA") is False
        assert is_sigla("MALA") is False
        assert is_sigla("ASIA") is False
        assert is_sigla("OVOS") is False

    def test_is_sigla_real(self):
        """Abreviações genuínas continuam siglas."""
        from app.utils.nucleo_marcario import is_sigla
        assert is_sigla("MS") is True
        assert is_sigla("LK") is True
        assert is_sigla("BMW") is True
        assert is_sigla("M.S.") is True
        assert is_sigla("H.O.F") is True

    def test_is_nome_proprio_titular(self):
        """Nome próprio = marca corresponde ao nome do titular."""
        from app.utils.nucleo_marcario import is_nome_proprio
        assert is_nome_proprio(
            {"marca": "CARLOS MOTTA ADVOCACIA", "titular": "CARLOS MOTTA"}
        ) is True
        assert is_nome_proprio(
            {"marca": "NEXO", "titular": "NEXO INDUSTRIA LTDA"}
        ) is True
        assert is_nome_proprio(
            {"marca": "COCA COLA", "titular": "OUTRA EMPRESA SA"}
        ) is False
        assert is_nome_proprio({"marca": "X", "titular": ""}) is False

    def test_is_marca_generica(self):
        from app.utils.nucleo_marcario import is_marca_generica
        assert is_marca_generica("super") is True
        assert is_marca_generica("cavalinho") is False

    def test_is_desgastado(self):
        from app.utils.nucleo_marcario import is_desgastado
        assert is_desgastado("SUPER PIZZA") is True
        assert is_desgastado("CAVALINHO AZUL") is False

    def test_nucleo_protege_marca_fraca(self):
        """Não deve reduzir a um resíduo fraco (desgastado/número)."""
        from app.utils.nucleo_marcario import extrair_nucleo
        # "royal" é desgastado → mantém nome completo
        assert extrair_nucleo("CAFE ROYAL") == "cafe royal"


class TestNumeros:
    def test_numero_distintivo_por_extenso(self):
        assert normalizar_base("STUDIO 54") == "studio cinquenta quatro"

    def test_ano_removido(self):
        # 2022 removido (ano); "pizzaria"→"pizaria" pela simplificação de dobra
        assert normalizar_base("PIZZARIA DO VAQUEIRO 2022") == "pizaria do vaqueiro"

    def test_hora_servico_removida(self):
        assert normalizar_base("CLINICA 24H") == "clinica"
        assert normalizar_base("FARMACIA 24 HORAS") == "farmacia"

    def test_numero_sozinho_mantido(self):
        assert normalizar_base("2000") == "dois mil"


class TestDobras:
    def test_dobra_simplificada(self):
        assert normalizar_base("MATTOS") == "matos"
        assert normalizar_base("BELLA") == "bela"

    def test_dobra_preservada_com_flag(self):
        assert normalizar_base("MATTOS", considerar_dobra=True) == "mattos"

    def test_sigla_curta_nao_colapsa(self):
        # "LL" (de L&L) tem 2 chars → dobra preservada
        assert normalizar_base("L&L") == "ll"
