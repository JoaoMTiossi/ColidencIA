"""
Testes das regras de colidência com os casos de ground truth do spec (RPI 2878).
"""

import pytest

from colisao_rpi.data.nice_matrix import classes_collide
from colisao_rpi.engine.nucleus import extract_nucleus
from colisao_rpi.engine.rules import check_collision


def _check(nome_cli, cls_cli, nome_rpi, classes_rpi):
    """Helper: monta e executa check_collision."""
    nucleo_cli = extract_nucleus(nome_cli)
    nucleo_rpi = extract_nucleus(nome_rpi)
    classe_match = any(classes_collide(cls_cli, c) for c in classes_rpi)
    return check_collision(
        nome_cli, nucleo_cli, cls_cli,
        nome_rpi, nucleo_rpi, classes_rpi,
        classe_match,
    )


# ---------------------------------------------------------------------------
# Regra 1 — Idêntica (independente de classe)
# ---------------------------------------------------------------------------

class TestRegra1:
    def test_nova_geracao_diferentes_classes(self):
        colide, regra, score = _check('NOVA GERACAO', 44, 'NOVA GERACAO', [41])
        assert colide is True
        assert regra == 'R1-IDENTICA'


# ---------------------------------------------------------------------------
# Regra 2 — NÃO marcar (ramos distintos)
# ---------------------------------------------------------------------------

class TestRegra2:
    def test_mitti_gelato_nao_colide(self):
        # Cl 25 (vestuário) × Cl 30 (sorvetes) — ramos completamente distintos
        colide, _, _ = _check('MITTI', 25, 'MITTI GELATO', [30])
        assert colide is False


# ---------------------------------------------------------------------------
# Regra 3 — Núcleo idêntico, classes correlatas
# ---------------------------------------------------------------------------

class TestRegra3:
    def test_inspire_pilates(self):
        # Cl 41 × Cl 35 são afins; núcleo de ambas = INSPIRE → R3
        colide, regra, score = _check('INSPIRE STUDIO DE PILATES E LPF', 41, 'INSPIRE PILATES', [35])
        assert colide is True
        assert regra in ('R3-NUCLEO-IDENTICO', 'R4-SIMILAR-FONETICO', 'R4b-NUCLEO-SIMILAR', 'R4c-TOKEN-SIMILAR')


# ---------------------------------------------------------------------------
# Regra 4 — Similar fonético, mesma classe / classes correlatas
# ---------------------------------------------------------------------------

class TestRegra4:
    def test_rottas_rota_calhas(self):
        colide, regra, score = _check('ROTTAS', 37, 'ROTA CALHAS', [37])
        assert colide is True

    def test_steffani_sthefany(self):
        colide, regra, score = _check('STEFFANI', 35, 'OTICAS STHEFANY', [35])
        assert colide is True

    def test_forty_ave_forte(self):
        # Cl 31 × Cl 5 são afins
        colide, regra, score = _check('FORTY', 31, 'AVE FORTE', [5])
        assert colide is True

    def test_tropical_tropi_carnes(self):
        # Cl 35 × Cl 29 são afins
        colide, regra, score = _check('TROPICAL', 35, 'TROPI CARNES', [29])
        assert colide is True


# ---------------------------------------------------------------------------
# Regra 7 — Mesmo núcleo, complementos distintos
# ---------------------------------------------------------------------------

class TestRegra7:
    def test_super_supermercados(self):
        # Cl 35 × Cl 43 são afins
        colide, regra, score = _check('SUPER + SUPERMERCADOS', 35, 'SUPERMERCADO SUPER PANE PADARIA', [43])
        assert colide is True

    def test_prime_participacoes_truck(self):
        colide, _, _ = _check('PRIME PARTICIPACOES', 36, 'PRIME TRUCK', [36])
        assert colide is True

    def test_prime_participacoes_saude(self):
        # Cl 36 × Cl 44 NÃO estão na matriz de colisão (NCL 13).
        # O analista pode identificar colisão de negócio, mas o motor não marca.
        colide, _, _ = _check('PRIME PARTICIPACOES', 36, 'PRIME SAUDE', [44])
        assert colide is False

    def test_link_monitoramento(self):
        colide, _, _ = _check('LINK MONITORAMENTO', 42, 'LINK SPORT CLUB PODCAST', [42])
        assert colide is True

    def test_teatro_faces(self):
        colide, _, _ = _check('TEATRO FACES', 41, 'FACES TEAM CONGRESS', [41])
        assert colide is True

    def test_mineracao_panorama(self):
        # Cl 40 × Cl 2 são afins
        colide, _, _ = _check('MINERACAO PANORAMA', 40, 'PANORAMA TINTAS', [2])
        assert colide is True

    def test_sorveteria_ideal(self):
        colide, _, _ = _check('SORVETERIA IDEAL', 43, 'CASA DE CARNES IDEAL', [43])
        assert colide is True

    def test_fly_protocolo(self):
        colide, _, _ = _check('FLY PROTOCOLO', 42, 'FLY AGENCY', [42])
        assert colide is True


# ---------------------------------------------------------------------------
# Matriz de colisão de classes
# ---------------------------------------------------------------------------

class TestClassMatrix:
    def test_mesma_classe(self):
        assert classes_collide(35, 35) is True

    def test_35_colide_41(self):
        assert classes_collide(35, 41) is True

    def test_25_colide_14(self):
        assert classes_collide(25, 14) is True

    def test_1_nao_colide_35(self):
        # 1 (químicos) × 35 (serviços comerciais) — não estão na matriz
        assert classes_collide(1, 35) is False

    def test_simetria(self):
        # A colisão deve ser simétrica
        assert classes_collide(40, 2) == classes_collide(2, 40)
