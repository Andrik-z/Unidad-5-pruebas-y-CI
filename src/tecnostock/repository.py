"""Infraestructura de TecnoStock: persistencia SQLAlchemy (SQLite en memoria en pruebas)."""
import json
from decimal import Decimal

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Session

from src.tecnostock.domain import (
    Apartado,
    EstadoApartado,
    LineaApartado,
    Monedero,
    VigenciaApartado,
)

ESTADOS_ACTIVOS = (EstadoApartado.RESERVA_TEMPORAL, EstadoApartado.CONFIRMADO)


class Base(DeclarativeBase):
    pass


class ApartadoRow(Base):
    __tablename__ = "apartados"
    id = Column(String, primary_key=True)
    cliente_id = Column(String, nullable=False)
    estado = Column(String, nullable=False)
    anticipo_pagado = Column(String, nullable=False)  # Decimal como texto (sin pérdida)
    creado_en = Column(DateTime, nullable=False)
    confirmado_en = Column(DateTime, nullable=True)
    articulos = Column(Integer, nullable=False)
    lineas = Column(Text, nullable=False)  # JSON


class SqlApartadoRepository:
    def __init__(self, session: Session):
        self.session = session

    def guardar(self, apartado: Apartado):
        lineas = [
            {"sku": ln.sku, "cantidad": ln.cantidad, "precio": str(ln.precio_unitario)}
            for ln in apartado.lineas
        ]
        self.session.merge(ApartadoRow(
            id=apartado.id,
            cliente_id=apartado.cliente_id,
            estado=str(apartado.estado),
            anticipo_pagado=str(apartado.anticipo_pagado),
            creado_en=apartado.vigencia.creado_en,
            confirmado_en=apartado.vigencia.confirmado_en,
            articulos=apartado.articulos,
            lineas=json.dumps(lineas),
        ))

    def obtener_por_id(self, apartado_id) -> Apartado | None:
        row = self.session.get(ApartadoRow, apartado_id)
        return self._a_dominio(row) if row else None

    def contar_articulos_activos(self, cliente_id) -> int:
        total = self.session.scalar(
            select(func.coalesce(func.sum(ApartadoRow.articulos), 0)).where(
                ApartadoRow.cliente_id == cliente_id,
                ApartadoRow.estado.in_([str(e) for e in ESTADOS_ACTIVOS]),
            )
        )
        return int(total)

    def listar_confirmados(self) -> list[Apartado]:
        rows = self.session.scalars(
            select(ApartadoRow).where(ApartadoRow.estado == str(EstadoApartado.CONFIRMADO))
        )
        return [self._a_dominio(r) for r in rows]

    @staticmethod
    def _a_dominio(row: ApartadoRow) -> Apartado:
        lineas = [
            LineaApartado(d["sku"], d["cantidad"], Decimal(d["precio"]))
            for d in json.loads(row.lineas)
        ]
        return Apartado(
            id=row.id,
            cliente_id=row.cliente_id,
            lineas=lineas,
            vigencia=VigenciaApartado(row.creado_en, row.confirmado_en),
            estado=EstadoApartado(row.estado),
            anticipo_pagado=Decimal(row.anticipo_pagado),
        )


class InMemoryMonederoRepository:
    """Adaptador simulado (el monedero real no forma parte del alcance de pruebas de BD)."""

    def __init__(self):
        self._monederos: dict[str, Monedero] = {}

    def obtener_por_cliente(self, cliente_id) -> Monedero:
        return self._monederos.setdefault(cliente_id, Monedero(cliente_id))

    def guardar(self, monedero: Monedero):
        self._monederos[monedero.cliente_id] = monedero


def make_engine(url: str = "sqlite+pysqlite:///:memory:"):
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


