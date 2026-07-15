"""Testes do peso IDF de token compartilhado (app/utils/idf_corpus.py)."""
from __future__ import annotations

from app.utils.idf_corpus import PESO_IDF_MAX, PESO_IDF_MIN, peso_idf


def test_token_vazio_devolve_peso_maximo():
    assert peso_idf("") == PESO_IDF_MAX
    assert peso_idf(None) == PESO_IDF_MAX


def test_token_desgastado_cai_no_piso():
    for tok in ("mega", "top", "max", "king", "gold"):
        assert peso_idf(tok) == PESO_IDF_MIN


def test_token_raro_fica_proximo_do_maximo():
    # Token cunhado, não existe em descrições NICE nem é desgastado.
    assert peso_idf("xhqzvbklaw") == PESO_IDF_MAX


def test_peso_sempre_no_intervalo():
    for tok in ("mega", "top", "capricho", "calcado", "software", "abc123xyz"):
        assert PESO_IDF_MIN <= peso_idf(tok) <= PESO_IDF_MAX
