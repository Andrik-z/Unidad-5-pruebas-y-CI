"""TecnoStock · Integración con SQLAlchemy (SQLite en memoria): commit, rollback y servicios.

Cada prueba crea su propio motor en memoria: no se toca ninguna base de datos real.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from src.tecnostock.application import ApartadoNoEncontrado, ApartadoService
from src.tecnostock.domain import (
    Apartado,
    EstadoApartado,
    LimiteArticulosExcedido,
    LineaApartado,
)
from src.tecnostock.repository import (
    InMemoryMonederoRepository,
    SqlApartadoRepository,
    make_engine,
)

AHORA = datetime(2026, 11, 3, 12, 0)


def lineas(cantidad, precio="1000.00"):
    return [LineaApartado("SKU-LAP-01", cantidad, Decimal(precio))]


def test_cp28_commit_persiste_el_apartado_y_otra_sesion_lo_ve():
    engine = make_engine()
    with Session(engine) as s1:
        apartado = Apartado.crear("AP-1", "C-1", lineas(2), 0, AHORA)
        SqlApartadoRepository(s1).guardar(apartado)
        s1.commit()
    with Session(engine) as s2:
        leido = SqlApartadoRepository(s2).obtener_por_id("AP-1")
    assert leido.estado is EstadoApartado.RESERVA_TEMPORAL
    assert leido.total == Decimal("2000.00")
    assert leido.articulos == 2
    assert leido.vigencia.creado_en == AHORA


def test_cp29_rollback_descarta_el_apartado():
    engine = make_engine()
    with Session(engine) as s1:
        repo = SqlApartadoRepository(s1)
        repo.guardar(Apartado.crear("AP-1", "C-1", lineas(1), 0, AHORA))
        s1.rollback()
    with Session(engine) as s2:
        assert SqlApartadoRepository(s2).obtener_por_id("AP-1") is None


def test_cp30_el_limite_de_5_articulos_considera_los_apartados_guardados():
    engine = make_engine()
    with Session(engine) as session:
        servicio = ApartadoService(
            SqlApartadoRepository(session), InMemoryMonederoRepository(), session
        )
        servicio.iniciar_apartado("AP-1", "C-1", lineas(3), AHORA)
        with pytest.raises(LimiteArticulosExcedido):
            servicio.iniciar_apartado("AP-2", "C-1", lineas(3), AHORA)  # 3 + 3 = 6
        assert servicio.repo.obtener_por_id("AP-2") is None  # no quedó nada guardado
        servicio.iniciar_apartado("AP-3", "C-1", lineas(2), AHORA)  # 3 + 2 = 5: límite
        assert servicio.repo.contar_articulos_activos("C-1") == 5
        servicio.iniciar_apartado("AP-4", "C-2", lineas(5), AHORA)  # otro cliente, aparte
        assert servicio.repo.contar_articulos_activos("C-2") == 5


def test_cp31_confirmar_apartado_persiste_el_estado_y_la_fecha_de_vencimiento():
    engine = make_engine()
    with Session(engine) as session:
        servicio = ApartadoService(
            SqlApartadoRepository(session), InMemoryMonederoRepository(), session
        )
        servicio.iniciar_apartado("AP-1", "C-1", lineas(1), AHORA)
        servicio.confirmar_apartado("AP-1", Decimal("200.00"), AHORA + timedelta(minutes=3))
    with Session(engine) as nueva:
        leido = SqlApartadoRepository(nueva).obtener_por_id("AP-1")
    assert leido.estado is EstadoApartado.CONFIRMADO
    assert leido.anticipo_pagado == Decimal("200.00")
    assert leido.vigencia.vence_en == AHORA + timedelta(minutes=3, days=30)
    with Session(engine) as otra:
        sin_registro = ApartadoService(
            SqlApartadoRepository(otra), InMemoryMonederoRepository(), otra
        )
        with pytest.raises(ApartadoNoEncontrado):
            sin_registro.confirmar_apartado("AP-X", Decimal("1.00"), AHORA)


def test_cp32_vencimiento_abona_al_monedero_una_sola_vez():
    engine = make_engine()
    monederos = InMemoryMonederoRepository()
    with Session(engine) as session:
        servicio = ApartadoService(SqlApartadoRepository(session), monederos, session)
        servicio.iniciar_apartado("AP-1", "C-1", lineas(1), AHORA)
        servicio.confirmar_apartado("AP-1", Decimal("200.00"), AHORA)

        assert servicio.procesar_vencimientos(AHORA + timedelta(days=29)) == 0  # aún vigente
        assert servicio.procesar_vencimientos(AHORA + timedelta(days=30)) == 1
        assert servicio.procesar_vencimientos(AHORA + timedelta(days=31)) == 0  # sin doble abono

        assert servicio.repo.obtener_por_id("AP-1").estado is EstadoApartado.VENCIDO
        assert monederos.obtener_por_cliente("C-1").saldo == Decimal("200.00")
        # un apartado vencido ya no cuenta para el límite de 5 artículos
        assert servicio.repo.contar_articulos_activos("C-1") == 0


def test_cp33_si_falla_el_monedero_se_hace_rollback_y_el_apartado_sigue_confirmado():
    engine = make_engine()
    with Session(engine) as session:
        repo = SqlApartadoRepository(session)
        base = ApartadoService(repo, InMemoryMonederoRepository(), session)
        base.iniciar_apartado("AP-1", "C-1", lineas(1), AHORA)
        base.confirmar_apartado("AP-1", Decimal("200.00"), AHORA)

        monederos_roto = Mock()
        monederos_roto.guardar.side_effect = RuntimeError("falla al guardar monedero")
        servicio = ApartadoService(repo, monederos_roto, session)
        with pytest.raises(RuntimeError):
            servicio.procesar_vencimientos(AHORA + timedelta(days=30))

    with Session(engine) as nueva:
        leido = SqlApartadoRepository(nueva).obtener_por_id("AP-1")
    assert leido.estado is EstadoApartado.CONFIRMADO  # el cambio a VENCIDO se revirtió
