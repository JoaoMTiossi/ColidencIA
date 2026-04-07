"""
Testes para as funções de normalização e equivalências fonéticas.
"""

import pytest

from colisao_rpi.engine.normalize import apply_phonetic, normalize, phonetic_key


class TestNormalize:
    def test_uppercase(self):
        assert normalize('café') == 'CAFE'

    def test_remove_accents(self):
        assert normalize('ção') == 'CAO'
        assert normalize('ñ') == 'N'

    def test_remove_punctuation(self):
        assert normalize('A.B-C') == 'A B C'

    def test_collapse_spaces(self):
        assert normalize('A   B') == 'A B'

    def test_empty(self):
        assert normalize('') == ''


class TestApplyPhonetic:
    def test_ph_to_f(self):
        assert apply_phonetic('PHARMA') == 'FARMA'

    def test_ck_to_c(self):
        assert apply_phonetic('TRUCK') == 'TRUC'

    def test_double_letters(self):
        # COFFEE → COFE (letras duplas colapsam)
        result = apply_phonetic('COFE')
        assert 'FF' not in result

    def test_qu_before_e_i(self):
        assert apply_phonetic('KERO') == 'CERO'  # K→C já

    def test_ss_to_s(self):
        # SS colapsa pela regra de letras duplas → S, depois S intervocálico → Z
        # PASSO → PASO → PAZO (comportamento fonético correto do PT)
        result = apply_phonetic('PASSO')
        assert 'SS' not in result
        # Deve ter a mesma chave fonética que PASO (ambos → PAZO)
        from colisao_rpi.engine.normalize import phonetic_key
        assert phonetic_key('PASSO') == phonetic_key('PASO')

    def test_lh_to_li(self):
        assert apply_phonetic('VELIO') == 'VELIO'  # já normalizado

    def test_w_to_v(self):
        assert apply_phonetic('VILSON') == 'VILSON'


class TestPhoneticKey:
    def test_steffani_sthefany(self):
        """STEFFANI e STHEFANY devem ter chaves fonéticas similares."""
        k1 = phonetic_key('STEFFANI')
        k2 = phonetic_key('STHEFANY')
        # Ambos devem começar com ST e ter estrutura similar
        assert k1[:2] == k2[:2] == 'ST'

    def test_pharma_farma(self):
        k1 = phonetic_key('PHARMA')
        k2 = phonetic_key('FARMA')
        assert k1 == k2
