"""
Testes para extração de núcleo da marca.
"""

import pytest

from colisao_rpi.engine.nucleus import extract_nucleus, is_common_mark


class TestExtractNucleus:
    def test_stopword_cuts_complement(self):
        # "E" é stopword
        assert extract_nucleus('RAMOS E RAMOS ADVOCACIA') == 'RAMOS'

    def test_descriptor_stopword(self):
        assert extract_nucleus('INSPIRE STUDIO DE PILATES E LPF') == 'INSPIRE'

    def test_prime_participacoes(self):
        assert extract_nucleus('PRIME PARTICIPACOES') == 'PRIME'

    def test_no_stopword_returns_all(self):
        # NOVA GERACAO — sem stopword → retorna tudo
        result = extract_nucleus('NOVA GERACAO')
        assert result == 'NOVA GERACAO'

    def test_single_word(self):
        assert extract_nucleus('INSPIRE') == 'INSPIRE'

    def test_empty_string(self):
        assert extract_nucleus('') == ''

    def test_super_plus(self):
        # SUPER é preservado (não é stopword) — + vira espaço após normalização
        result = extract_nucleus('SUPER + SUPERMERCADOS')
        assert result.startswith('SUPER')


class TestIsCommonMark:
    def test_super_is_common(self):
        assert is_common_mark('SUPER') is True

    def test_prime_is_common(self):
        assert is_common_mark('PRIME') is True

    def test_distinctive_not_common(self):
        assert is_common_mark('INSPIRE') is False

    def test_two_common_tokens(self):
        assert is_common_mark('SUPER TOP') is True

    def test_three_tokens_not_common(self):
        # Mais de 2 tokens → False mesmo que um seja comum
        assert is_common_mark('SUPER MEGA ULTRA') is False
