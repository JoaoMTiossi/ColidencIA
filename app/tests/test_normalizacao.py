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
        assert normalizar_base("A  B") == "a b"

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

    def test_is_marca_generica(self):
        from app.utils.nucleo_marcario import is_marca_generica
        assert is_marca_generica("super") is True
        assert is_marca_generica("cavalinho") is False

    def test_is_desgastado(self):
        from app.utils.nucleo_marcario import is_desgastado
        assert is_desgastado("SUPER PIZZA") is True
        assert is_desgastado("CAVALINHO AZUL") is False
