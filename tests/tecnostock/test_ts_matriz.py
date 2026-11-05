"""La matriz de casos (CSV) debe ser fiel al código: cada fila apunta a una prueba que existe."""
import csv
from pathlib import Path

CARPETA = Path(__file__).parent


def _filas():
    with (CARPETA / "data" / "matriz_pia_tecnostock.csv").open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_matriz_tiene_al_menos_9_casos_y_los_tres_tipos():
    filas = _filas()
    assert len(filas) >= 9
    assert {"Éxito", "Error", "Límite"} <= {fila["tipo"] for fila in filas}


def test_matriz_cubre_al_menos_3_reglas_distintas():
    reglas = {fila["regla"].split(" ")[0] for fila in _filas()}
    assert len(reglas) >= 3


def test_cada_caso_de_la_matriz_tiene_su_prueba_automatizada():
    codigo = "".join(p.read_text(encoding="utf-8") for p in CARPETA.glob("test_ts_*.py"))
    faltantes = [f["id"] for f in _filas() if f"def {f['prueba']}(" not in codigo]
    assert faltantes == []
