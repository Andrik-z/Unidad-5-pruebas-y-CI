import csv
import re
from pathlib import Path

import pytest

from src.domain import CustomerHasDebt, Order

DATA = Path(__file__).parent / "data"


def _read(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


PEDIDOS = {int(r["pedido_id"]): r for r in _read("pedidos_prueba.csv")}
CASOS = [c for c in _read("casos_de_prueba.csv") if c["pedido_id"]]

ESPERADO_POST_TDD = {"CP08": "ValueError"}


def _expected(caso):
    return ESPERADO_POST_TDD.get(caso["caso_id"], caso["resultado_esperado"])


@pytest.mark.parametrize("caso", CASOS, ids=[c["caso_id"] for c in CASOS])
def test_confirm_from_csv(caso):
    row = PEDIDOS[int(caso["pedido_id"])]
    order = Order(float(row["total"]), vip=row["es_vip"] == "1", status=row["estado_inicial"])
    debt = float(row["deuda_cliente"])
    expected = _expected(caso)

    if expected == "CustomerHasDebt":
        with pytest.raises(CustomerHasDebt):
            order.confirm(customer_debt=debt)
    elif expected == "ValueError":
        with pytest.raises(ValueError):
            order.confirm(customer_debt=debt)
    else:
        amount = float(re.search(r"cobro ([\d.]+)", expected).group(1))
        assert order.confirm(customer_debt=debt) == pytest.approx(amount, abs=0.005)
        assert order.status == "CONFIRMED"
