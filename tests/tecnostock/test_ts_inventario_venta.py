"""TecnoStock · Inventario (producto apartado no se vende) y Venta con pasarela simulada.

El Mock de la pasarela NO realiza cobros reales: es un objeto local controlado por la prueba.
"""
from decimal import Decimal
from unittest.mock import Mock

import pytest

from src.tecnostock.application import CajaService
from src.tecnostock.domain import (
    EstadoUnidad,
    EstadoVenta,
    Inventario,
    LineaVenta,
    PagoDeclinado,
    ProductoApartado,
    TransicionInvalida,
    UnidadNoDisponible,
    Venta,
)


@pytest.fixture
def inventario():
    inv = Inventario("SUC-1")
    for serie in ("SN-001", "SN-002", "SN-003"):
        inv.agregar_unidad(serie, "SKU-CEL-01")
    return inv


def venta_de(*series, precio="8500.00"):
    return Venta("V-1", [LineaVenta(s, "SKU-CEL-01", Decimal(precio)) for s in series])


# ----------------------------------------------------- R6 · producto apartado no se vende
def test_cp19_unidad_apartada_no_puede_venderse(inventario):
    inventario.apartar_unidad("SN-001", "AP-1")
    with pytest.raises(ProductoApartado):
        inventario.vender_unidad("SN-001")
    assert inventario.unidades["SN-001"].estado is EstadoUnidad.APARTADO


def test_cp20_unidad_disponible_se_vende_y_baja_la_existencia(inventario):
    assert inventario.disponibilidad("SKU-CEL-01") == 3
    inventario.vender_unidad("SN-001")
    assert inventario.unidades["SN-001"].estado is EstadoUnidad.VENDIDO
    assert inventario.disponibilidad("SKU-CEL-01") == 2


def test_cp21_unidad_en_transito_no_es_vendible(inventario):
    inventario.marcar_en_transito("SN-002")
    with pytest.raises(UnidadNoDisponible):
        inventario.vender_unidad("SN-002")


def test_cp22_serie_duplicada_o_inexistente_se_rechaza(inventario):
    with pytest.raises(ValueError):
        inventario.agregar_unidad("SN-001", "SKU-CEL-01")
    with pytest.raises(UnidadNoDisponible):
        inventario.vender_unidad("SN-999")


def test_cp23_apartar_y_liberar_devuelve_la_unidad_al_piso_de_ventas(inventario):
    inventario.apartar_unidad("SN-001", "AP-1")
    assert inventario.disponibilidad("SKU-CEL-01") == 2
    inventario.liberar_unidad("SN-001")
    assert inventario.disponibilidad("SKU-CEL-01") == 3
    with pytest.raises(UnidadNoDisponible):
        inventario.liberar_unidad("SN-001")  # ya no está apartada
    with pytest.raises(UnidadNoDisponible):
        inventario.apartar_unidad("SN-999", "AP-2")
    inventario.vender_unidad("SN-002")
    with pytest.raises(UnidadNoDisponible):
        inventario.apartar_unidad("SN-002", "AP-3")  # vendida: no se puede apartar
    with pytest.raises(UnidadNoDisponible):
        inventario.marcar_en_transito("SN-002")


# ----------------------------------------------------- R7 · cobro con pasarela (mock)
def test_cp24_pago_aprobado_genera_comprobante_y_descuenta_inventario(inventario):
    gateway = Mock()
    gateway.charge.return_value = True
    venta = venta_de("SN-001", "SN-002")

    comprobante = CajaService(gateway).cobrar_venta(venta, inventario)

    assert venta.estado is EstadoVenta.PAGADA
    assert comprobante.codigo_qr == "QR-V-1"
    assert inventario.unidades["SN-001"].estado is EstadoUnidad.VENDIDO
    assert inventario.unidades["SN-002"].estado is EstadoUnidad.VENDIDO
    gateway.charge.assert_called_once_with(Decimal("17000.00"))


def test_cp25_pago_declinado_cancela_la_venta_sin_tocar_el_inventario(inventario):
    gateway = Mock()
    gateway.charge.return_value = False
    venta = venta_de("SN-001")

    with pytest.raises(PagoDeclinado):
        CajaService(gateway).cobrar_venta(venta, inventario)

    assert venta.estado is EstadoVenta.CANCELADA
    assert venta.comprobante is None  # sin pago aprobado no hay ticket QR
    assert inventario.unidades["SN-001"].estado is EstadoUnidad.DISPONIBLE
    gateway.charge.assert_called_once_with(Decimal("8500.00"))


def test_cp26_nunca_se_cobra_un_producto_apartado(inventario):
    gateway = Mock()
    gateway.charge.return_value = True
    inventario.apartar_unidad("SN-001", "AP-1")
    venta = venta_de("SN-001")

    with pytest.raises(ProductoApartado):
        CajaService(gateway).cobrar_venta(venta, inventario)

    gateway.charge.assert_not_called()  # la validación ocurre ANTES del cobro
    assert venta.estado is EstadoVenta.PENDIENTE


def test_cp27_invariantes_de_la_venta():
    with pytest.raises(ValueError):
        Venta("V-2", [])
    venta = venta_de("SN-001")
    venta.registrar_pago()
    with pytest.raises(TransicionInvalida):
        venta.registrar_pago()
    with pytest.raises(TransicionInvalida):
        venta.cancelar()
