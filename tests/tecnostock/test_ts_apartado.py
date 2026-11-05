"""TecnoStock · Aggregates Apartado y Monedero (pruebas unitarias, sin BD ni red).

Patrón Arrange-Act-Assert. Fecha fija AHORA: ninguna prueba depende del reloj real.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.tecnostock.domain import (
    AnticipoInsuficiente,
    Apartado,
    EstadoApartado,
    LimiteArticulosExcedido,
    LineaApartado,
    Monedero,
    PlazoVencido,
    ReservaExpirada,
    SaldoIncompleto,
    SaldoInsuficiente,
    TransicionInvalida,
)

AHORA = datetime(2026, 11, 3, 12, 0)


def nuevo(precio="1000.00", cantidad=1, activos=0):
    lineas = [LineaApartado("SKU-LAP-01", cantidad, Decimal(precio))]
    return Apartado.crear("AP-1", "C-1", lineas, activos, AHORA)


def confirmado(precio="1000.00", pago="200.00"):
    apartado = nuevo(precio)
    apartado.aplicar_anticipo(Decimal(pago), AHORA + timedelta(minutes=5))
    return apartado


# ----------------------------------------------------- R1 · anticipo mínimo del 20 %
def test_cp01_anticipo_exacto_20_por_ciento_confirma():
    apartado = nuevo("1000.00")
    apartado.aplicar_anticipo(Decimal("200.00"), AHORA)
    assert apartado.estado is EstadoApartado.CONFIRMADO
    assert apartado.vigencia.vence_en == AHORA + timedelta(days=30)
    assert apartado.saldo == Decimal("800.00")
    assert "ApartadoConfirmado" in apartado.eventos


def test_cp02_un_centavo_menos_del_20_por_ciento_se_rechaza():
    apartado = nuevo("1000.00")
    with pytest.raises(AnticipoInsuficiente):
        apartado.aplicar_anticipo(Decimal("199.99"), AHORA)
    assert apartado.estado is EstadoApartado.RESERVA_TEMPORAL


def test_cp03_anticipo_mayor_al_minimo_reduce_el_saldo():
    apartado = nuevo("1000.00")
    apartado.aplicar_anticipo(Decimal("350.00"), AHORA)
    assert apartado.anticipo_pagado == Decimal("350.00")
    assert apartado.saldo == Decimal("650.00")


def test_cp04_redondeo_del_minimo_a_centavos():
    # 20 % de 999.99 = 199.998 -> mínimo 200.00
    assert nuevo("999.99").anticipo_minimo == Decimal("200.00")
    with pytest.raises(AnticipoInsuficiente):
        nuevo("999.99").aplicar_anticipo(Decimal("199.99"), AHORA)
    ok = nuevo("999.99")
    ok.aplicar_anticipo(Decimal("200.00"), AHORA)
    assert ok.estado is EstadoApartado.CONFIRMADO


# ----------------------------------------------------- R2 · máximo 5 artículos
def test_cp05_cinco_articulos_es_el_limite_permitido():
    assert nuevo(cantidad=5, activos=0).articulos == 5


def test_cp06_seis_articulos_excede_el_limite():
    with pytest.raises(LimiteArticulosExcedido):
        nuevo(cantidad=6, activos=0)


def test_cp07_cuenta_los_articulos_activos_previos_del_cliente():
    assert nuevo(cantidad=2, activos=3).articulos == 2  # 3 + 2 = 5: permitido
    with pytest.raises(LimiteArticulosExcedido):
        nuevo(cantidad=3, activos=3)  # 3 + 3 = 6: rechazado


def test_cp08_cantidad_cero_o_lista_vacia_es_invalida():
    with pytest.raises(ValueError):
        nuevo(cantidad=0)
    with pytest.raises(ValueError):
        Apartado.crear("AP-2", "C-1", [], 0, AHORA)


# ----------------------------------------------------- R3 · reserva de 15 min
def test_cp09_pago_un_segundo_antes_de_15_min_confirma():
    apartado = nuevo()
    apartado.aplicar_anticipo(Decimal("200.00"), AHORA + timedelta(minutes=14, seconds=59))
    assert apartado.estado is EstadoApartado.CONFIRMADO


def test_cp10_pago_a_los_15_min_exactos_ya_no_es_valido():
    apartado = nuevo()
    with pytest.raises(ReservaExpirada):
        apartado.aplicar_anticipo(Decimal("200.00"), AHORA + timedelta(minutes=15))


def test_cp11_la_reserva_temporal_expira_a_los_15_min():
    apartado = nuevo()
    assert apartado.expirar_reserva(AHORA + timedelta(minutes=14)) is False
    assert apartado.estado is EstadoApartado.RESERVA_TEMPORAL
    assert apartado.expirar_reserva(AHORA + timedelta(minutes=15)) is True
    assert apartado.estado is EstadoApartado.EXPIRADO
    assert "ReservaTemporalExpirada" in apartado.eventos


# ----------------------------------------------------- R4 · vencimiento a 30 días
def test_cp12_liquidar_el_dia_29_con_saldo_exacto():
    apartado = confirmado()
    apartado.liquidar(Decimal("800.00"), AHORA + timedelta(minutes=5) + timedelta(days=29))
    assert apartado.estado is EstadoApartado.LIQUIDADO
    assert "ApartadoLiquidado" in apartado.eventos


def test_cp13_liquidar_a_los_30_dias_exactos_ya_es_extemporaneo():
    apartado = confirmado()
    with pytest.raises(PlazoVencido):
        apartado.liquidar(Decimal("800.00"), AHORA + timedelta(minutes=5) + timedelta(days=30))


def test_cp14_liquidar_exige_el_saldo_completo():
    apartado = confirmado()
    with pytest.raises(SaldoIncompleto):
        apartado.liquidar(Decimal("799.99"), AHORA + timedelta(days=1))
    assert apartado.estado is EstadoApartado.CONFIRMADO


def test_cp15_vencer_solo_cuando_cumple_30_dias():
    apartado = confirmado()
    confirmacion = AHORA + timedelta(minutes=5)
    assert apartado.vencer(confirmacion + timedelta(days=29, hours=23)) is False
    assert apartado.vencer(confirmacion + timedelta(days=30)) is True
    assert apartado.estado is EstadoApartado.VENCIDO
    assert "ApartadoVencido" in apartado.eventos


def test_cp16_transiciones_invalidas_se_rechazan():
    ya_confirmado = confirmado()
    with pytest.raises(TransicionInvalida):
        ya_confirmado.aplicar_anticipo(Decimal("200.00"), AHORA)
    with pytest.raises(TransicionInvalida):
        nuevo().liquidar(Decimal("800.00"), AHORA)
    assert nuevo().vencer(AHORA + timedelta(days=60)) is False  # reserva temporal no vence


def test_cp34_una_reserva_temporal_aun_no_tiene_fecha_de_vencimiento():
    apartado = nuevo()
    assert apartado.vigencia.vence_en is None
    assert apartado.vigencia.vencida(AHORA + timedelta(days=90)) is False


# ----------------------------------------------------- R5 · Monedero
def test_cp17_un_apartado_vencido_abona_una_sola_vez():
    monedero = Monedero("C-1")
    assert monedero.abonar_anticipo("AP-1", Decimal("200.00")) is True
    assert monedero.abonar_anticipo("AP-1", Decimal("200.00")) is False  # idempotente
    assert monedero.saldo == Decimal("200.00")


def test_cp18_el_saldo_del_monedero_nunca_es_negativo():
    monedero = Monedero("C-1")
    monedero.abonar_anticipo("AP-1", Decimal("200.00"))
    monedero.descontar(Decimal("200.00"))  # límite: queda exactamente en cero
    assert monedero.saldo == Decimal("0.00")
    with pytest.raises(SaldoInsuficiente):
        monedero.descontar(Decimal("0.01"))
