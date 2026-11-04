from unittest.mock import Mock

import pytest

from src.application import OrderService
from src.domain import Order


def test_gateway_approved():
    gateway = Mock()
    gateway.charge.return_value = True
    assert OrderService(gateway).checkout(Order(100)) == 100
    gateway.charge.assert_called_once_with(100)

def test_gateway_rejected():
    gateway = Mock()
    gateway.charge.return_value = False
    with pytest.raises(RuntimeError):
        OrderService(gateway).checkout(Order(100))

def test_gateway_rejected_vip_200_charges_170():
    gateway = Mock()
    gateway.charge.return_value = False
    order = Order(200, vip=True)
    with pytest.raises(RuntimeError, match="payment rejected"):
        OrderService(gateway).checkout(order)
    gateway.charge.assert_called_once_with(170)


def test_known_risk_order_confirmed_even_if_payment_rejected():
    gateway = Mock()
    gateway.charge.return_value = False
    order = Order(100)
    with pytest.raises(RuntimeError):
        OrderService(gateway).checkout(order)
    assert order.status == "CONFIRMED"