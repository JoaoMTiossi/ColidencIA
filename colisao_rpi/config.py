"""
Configuração global: thresholds, paths, constantes.
"""

# ---------------------------------------------------------------------------
# Thresholds de similaridade
# ---------------------------------------------------------------------------

# Regra 1 — marca idêntica (após normalização fonética)
THRESHOLD_IDENTICO: float = 1.0

# Regra 4 — marca similar (nome completo)
THRESHOLD_SIMILAR: float = 0.75

# Regra 3/7 — núcleo idêntico ou muito próximo
THRESHOLD_NUCLEO: float = 0.80

# Marcas com ≤ 2 caracteres só colidirem se idênticas
MIN_CHARS_SOFT_MATCH: int = 3

# ---------------------------------------------------------------------------
# Defaults de CLI
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_DIR = "."
