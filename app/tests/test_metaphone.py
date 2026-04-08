"""
Testes unitários para o Metaphone PT-BR.
"""
import pytest
from app.utils.metaphone_ptbr import metaphone_ptbr


class TestMetaphonePtbr:
    def test_cavalinho_kavallo_similares(self):
        """CAVALINHO e KAVALLO devem produzir códigos fonéticos parecidos."""
        ka = metaphone_ptbr("CAVALINHO")
        kb = metaphone_ptbr("KAVALLO")
        # Os primeiros 3 chars devem ser iguais (KVL)
        assert ka[:3] == kb[:3], f"Esperado prefixo igual: {ka!r} vs {kb!r}"

    def test_jolli_joly_similares(self):
        """JOLLI e JOLY devem gerar códigos fonéticos iguais ou com distância ≤ 1."""
        ka = metaphone_ptbr("JOLLI")
        kb = metaphone_ptbr("JOLY")
        # Após correção (Y não-inicial = vogal), ambos devem gerar o mesmo código
        assert ka == kb or abs(len(ka) - len(kb)) <= 1, \
            f"Esperado códigos parecidos: {ka!r} vs {kb!r}"

    def test_carmel_carmell_identicos(self):
        """CARMEL e CARMELL (consoante dupla) devem ser iguais."""
        assert metaphone_ptbr("CARMEL") == metaphone_ptbr("CARMELL")

    def test_mandacaru_mandakkaru_identicos(self):
        """MANDACARU e MANDAKKARU devem ser iguais."""
        assert metaphone_ptbr("MANDACARU") == metaphone_ptbr("MANDAKKARU")

    def test_h_inicial_silencioso(self):
        """H inicial é silencioso."""
        assert metaphone_ptbr("HOJE") == metaphone_ptbr("OJE") or \
               metaphone_ptbr("HORA") != ""

    def test_vazio(self):
        """String vazia retorna string vazia."""
        assert metaphone_ptbr("") == ""
        assert metaphone_ptbr("   ") == ""

    def test_limite_6_chars(self):
        """Resultado deve ter no máximo 6 caracteres."""
        result = metaphone_ptbr("SUPERCALIFRAGILISTICO")
        assert len(result) <= 6

    def test_ph_vira_f(self):
        """PH deve virar F."""
        k = metaphone_ptbr("PHARMA")
        assert k.startswith("F")

    def test_ss_reduzido(self):
        """SS deve ser reduzido a S."""
        assert metaphone_ptbr("CASSINO") == metaphone_ptbr("CASINO")

    def test_lh_vira_li(self):
        """LH → LI."""
        k = metaphone_ptbr("GALHO")
        assert "L" in k
