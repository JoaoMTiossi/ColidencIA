"""
Derivação dos pesos do score composto via AHP (Analytic Hierarchy Process).

Os pesos em config.py NÃO são arbitrários: foram derivados das comparações
par-a-par fornecidas pelo especialista, usando a escala de Saaty (1-9) e o
método do autovetor (aproximado pela média geométrica das linhas).

Estrutura hierárquica (2 níveis):

  Score
  ├── Similaridade do sinal   (macro)
  │     ├── Nome (ortográfico)
  │     ├── Núcleo marcário
  │     └── Fonética
  ├── Afinidade mercadológica (macro)
  │     ├── Especificação
  │     └── Bônus de classe (NCL)
  └── Apresentação (tipo de marca)  (macro)

Rode `python -m app.tests.ahp_pesos` para reproduzir os pesos e os índices
de consistência (CR). CR < 0.10 indica julgamentos coerentes.

Julgamentos do especialista (sessão de calibração):
  MACRO   Sinal = Afinidade (1×);  Sinal = 3× Apresentação;  Afinidade = 3× Apresentação
  SINAL   Nome = Fonética (1×);    Núcleo = 5× Nome;          Núcleo = 3× Fonética
  AFIN    Especificação = 5× Classe
"""
from __future__ import annotations

import math

# Índice aleatório de Saaty por dimensão da matriz
_RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32}


def ahp(matriz: list[list[float]], nomes: list[str]) -> tuple[dict[str, float], float, float]:
    """Retorna (pesos, lambda_max, CR) de uma matriz de comparação par-a-par."""
    n = len(matriz)
    gm = [math.prod(matriz[i][j] for j in range(n)) ** (1 / n) for i in range(n)]
    soma = sum(gm)
    pesos = [g / soma for g in gm]
    col_sum = [sum(matriz[i][j] for i in range(n)) for j in range(n)]
    lambda_max = sum(col_sum[j] * pesos[j] for j in range(n))
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    cr = ci / _RI[n] if _RI[n] > 0 else 0.0
    return dict(zip(nomes, pesos)), lambda_max, cr


# Macro: Sinal, Afinidade, Apresentação
MACRO = [
    [1, 1, 3],
    [1, 1, 3],
    [1 / 3, 1 / 3, 1],
]

# Sinal: Nome, Núcleo, Fonética  (Núcleo 5× Nome, Núcleo 3× Fonética, Nome = Fonética)
SINAL = [
    [1, 1 / 5, 1],
    [5, 1, 3],
    [1, 1 / 3, 1],
]

# Afinidade: Especificação, Classe  (Spec 5× Classe)
AFIN = [
    [1, 5],
    [1 / 5, 1],
]


def derivar_pesos() -> dict[str, float]:
    """Compõe os pesos globais (config.py) a partir das matrizes AHP."""
    wm, _, _ = ahp(MACRO, ["Sinal", "Afinidade", "Apresentacao"])
    ws, _, _ = ahp(SINAL, ["Nome", "Nucleo", "Fonetica"])
    wa, _, _ = ahp(AFIN, ["Spec", "Classe"])
    return {
        "PESO_SIMILARIDADE_NOME": wm["Sinal"] * ws["Nome"],
        "PESO_NUCLEO_MARCARIO": wm["Sinal"] * ws["Nucleo"],
        "PESO_FONETICA": wm["Sinal"] * ws["Fonetica"],
        "PESO_AFINIDADE_SPEC": wm["Afinidade"] * wa["Spec"],
        "PESO_BONUS": wm["Afinidade"] * wa["Classe"],
        "PESO_TIPO_MARCA": wm["Apresentacao"],
    }


if __name__ == "__main__":
    wm, _, crm = ahp(MACRO, ["Sinal", "Afinidade", "Apresentacao"])
    ws, _, crs = ahp(SINAL, ["Nome", "Nucleo", "Fonetica"])
    wa, _, cra = ahp(AFIN, ["Spec", "Classe"])
    print(f"MACRO  CR={crm:.4f}  {dict((k, round(v, 4)) for k, v in wm.items())}")
    print(f"SINAL  CR={crs:.4f}  {dict((k, round(v, 4)) for k, v in ws.items())}")
    print(f"AFIN   CR={cra:.4f}  {dict((k, round(v, 4)) for k, v in wa.items())}")
    print("\nPesos globais (config.py):")
    g = derivar_pesos()
    for k, v in g.items():
        print(f"  {k:25s} = {round(v, 4)}")
    print(f"  soma = {round(sum(g.values()), 4)}")
