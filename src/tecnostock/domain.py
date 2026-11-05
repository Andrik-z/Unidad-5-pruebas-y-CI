"""Dominio de TecnoStock (diseño de la Unidad 3, Equipo 5).

Reglas implementadas (BRD sección 5 y User Stories US-08 a US-16):
  Apartado   : máximo 5 artículos, anticipo mínimo 20 %, reserva temporal 15 min,
               vencimiento a 30 días, transiciones válidas.
  Monedero   : un apartado vencido abona su anticipo una sola vez.
  Inventario : un producto apartado (o en tránsito) no puede venderse.
  Venta      : el comprobante con QR solo existe con pago aprobado.

Las fechas son datetime sin zona (UTC) y siempre se reciben como parámetro `ahora`:
nunca se llama a datetime.now() dentro del dominio, para que las pruebas sean deterministas.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MAX_ARTICULOS = 5
TASA_ANTICIPO = Decimal("0.20")
RESERVA_TEMPORAL = timedelta(minutes=15)
VENCIMIENTO_APARTADO = timedelta(days=30)
CENTAVO = Decimal("0.01")


def dinero(valor) -> Decimal:
    """Normaliza a 2 decimales (redondeo comercial: mitad hacia arriba)."""
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- errores de negocio
class ReglaDeNegocioError(Exception):
    pass


class LimiteArticulosExcedido(ReglaDeNegocioError):
    pass


class AnticipoInsuficiente(ReglaDeNegocioError):
    pass


class ReservaExpirada(ReglaDeNegocioError):
    pass


class PlazoVencido(ReglaDeNegocioError):
    pass


class SaldoIncompleto(ReglaDeNegocioError):
    pass


class TransicionInvalida(ReglaDeNegocioError):
    pass


class ProductoApartado(ReglaDeNegocioError):
    pass


class UnidadNoDisponible(ReglaDeNegocioError):
    pass


class SaldoInsuficiente(ReglaDeNegocioError):
    pass


class PagoDeclinado(ReglaDeNegocioError):
    pass


# ---------------------------------------------------------------- estados
class EstadoApartado(StrEnum):
    RESERVA_TEMPORAL = "RESERVA_TEMPORAL"
    CONFIRMADO = "CONFIRMADO"
    LIQUIDADO = "LIQUIDADO"
    VENCIDO = "VENCIDO"
    EXPIRADO = "EXPIRADO"  # la reserva temporal de 15 min terminó sin pago


class EstadoUnidad(StrEnum):
    DISPONIBLE = "DISPONIBLE"
    APARTADO = "APARTADO"
    VENDIDO = "VENDIDO"
    EN_TRANSITO = "EN_TRANSITO"


class EstadoVenta(StrEnum):
    PENDIENTE = "PENDIENTE"
    PAGADA = "PAGADA"
    CANCELADA = "CANCELADA"


# ---------------------------------------------------------------- Value Objects
@dataclass(frozen=True)
class Anticipo:
    monto: Decimal

    @staticmethod
    def minimo_para(total) -> Decimal:
        return dinero(dinero(total) * TASA_ANTICIPO)


@dataclass(frozen=True)
class VigenciaApartado:
    creado_en: datetime
    confirmado_en: datetime | None = None

    @property
    def fin_reserva_temporal(self) -> datetime:
        return self.creado_en + RESERVA_TEMPORAL

    @property
    def vence_en(self) -> datetime | None:
        if self.confirmado_en is None:
            return None
        return self.confirmado_en + VENCIMIENTO_APARTADO

    def reserva_expirada(self, ahora: datetime) -> bool:
        # SUPUESTO: al cumplirse exactamente 15 min la reserva ya expiró (US-09).
        return ahora >= self.fin_reserva_temporal

    def vencida(self, ahora: datetime) -> bool:
        # SUPUESTO: al cumplirse exactamente 30 días el apartado ya venció (US-12).
        return self.vence_en is not None and ahora >= self.vence_en


@dataclass(frozen=True)
class LineaApartado:
    sku: str
    cantidad: int
    precio_unitario: Decimal

    @property
    def subtotal(self) -> Decimal:
        return dinero(self.precio_unitario * self.cantidad)


@dataclass(frozen=True)
class Comprobante:
    folio: str
    codigo_qr: str


# ---------------------------------------------------------------- Aggregate: Apartado
@dataclass
class Apartado:
    id: str
    cliente_id: str
    lineas: list[LineaApartado]
    vigencia: VigenciaApartado
    estado: EstadoApartado = EstadoApartado.RESERVA_TEMPORAL
    anticipo_pagado: Decimal = Decimal("0.00")
    eventos: list[str] = field(default_factory=list)

    @classmethod
    def crear(cls, id, cliente_id, lineas, articulos_activos_cliente, ahora):
        if not lineas or any(linea.cantidad <= 0 for linea in lineas):
            raise ValueError("el apartado requiere artículos con cantidad positiva")
        articulos = sum(linea.cantidad for linea in lineas)
        if articulos_activos_cliente + articulos > MAX_ARTICULOS:
            raise LimiteArticulosExcedido(f"máximo {MAX_ARTICULOS} artículos por cliente")
        return cls(id, cliente_id, list(lineas), VigenciaApartado(creado_en=ahora))

    @property
    def articulos(self) -> int:
        return sum(linea.cantidad for linea in self.lineas)

    @property
    def total(self) -> Decimal:
        return dinero(sum((linea.subtotal for linea in self.lineas), Decimal(0)))

    @property
    def anticipo_minimo(self) -> Decimal:
        return Anticipo.minimo_para(self.total)

    @property
    def saldo(self) -> Decimal:
        return dinero(self.total - self.anticipo_pagado)

    def aplicar_anticipo(self, monto, ahora):
        if self.estado is not EstadoApartado.RESERVA_TEMPORAL:
            raise TransicionInvalida("solo una reserva temporal admite anticipo")
        if self.vigencia.reserva_expirada(ahora):
            raise ReservaExpirada("la reserva temporal de 15 minutos terminó")
        monto = dinero(monto)
        if monto < self.anticipo_minimo:
            raise AnticipoInsuficiente(f"anticipo mínimo {self.anticipo_minimo}")
        self.anticipo_pagado = monto
        self.vigencia = replace(self.vigencia, confirmado_en=ahora)
        self.estado = EstadoApartado.CONFIRMADO
        self.eventos.append("ApartadoConfirmado")

    def expirar_reserva(self, ahora) -> bool:
        if self.estado is EstadoApartado.RESERVA_TEMPORAL and self.vigencia.reserva_expirada(ahora):
            self.estado = EstadoApartado.EXPIRADO
            self.eventos.append("ReservaTemporalExpirada")
            return True
        return False

    def liquidar(self, monto, ahora):
        if self.estado is not EstadoApartado.CONFIRMADO:
            raise TransicionInvalida("solo un apartado confirmado puede liquidarse")
        if self.vigencia.vencida(ahora):
            raise PlazoVencido("el apartado ya superó los 30 días")
        if dinero(monto) != self.saldo:
            raise SaldoIncompleto(f"se requiere liquidar el saldo completo: {self.saldo}")
        self.estado = EstadoApartado.LIQUIDADO
        self.eventos.append("ApartadoLiquidado")

    def vencer(self, ahora) -> bool:
        if self.estado is EstadoApartado.CONFIRMADO and self.vigencia.vencida(ahora):
            self.estado = EstadoApartado.VENCIDO
            self.eventos.append("ApartadoVencido")
            return True
        return False


# ---------------------------------------------------------------- Aggregate: Monedero
@dataclass
class Monedero:
    cliente_id: str
    saldo: Decimal = Decimal("0.00")
    apartados_abonados: set[str] = field(default_factory=set)

    def abonar_anticipo(self, apartado_id, monto) -> bool:
        """Idempotente por apartado_id: un apartado vencido abona una sola vez."""
        if apartado_id in self.apartados_abonados:
            return False
        self.saldo = dinero(self.saldo + dinero(monto))
        self.apartados_abonados.add(apartado_id)
        return True

    def descontar(self, monto):
        monto = dinero(monto)
        if monto > self.saldo:
            raise SaldoInsuficiente("el saldo nunca puede ser negativo")
        self.saldo = dinero(self.saldo - monto)


# ---------------------------------------------------------------- Aggregate: Inventario
@dataclass
class UnidadSeriada:
    serie: str
    sku: str
    estado: EstadoUnidad = EstadoUnidad.DISPONIBLE
    apartado_id: str | None = None


class Inventario:
    """Inventario de UNA sucursal, con unidades identificadas por número de serie."""

    def __init__(self, sucursal_id: str):
        self.sucursal_id = sucursal_id
        self.unidades: dict[str, UnidadSeriada] = {}

    def agregar_unidad(self, serie, sku):
        if serie in self.unidades:
            raise ValueError("el número de serie es único")
        self.unidades[serie] = UnidadSeriada(serie, sku)

    def _unidad(self, serie) -> UnidadSeriada:
        if serie not in self.unidades:
            raise UnidadNoDisponible(f"serie {serie} no existe en la sucursal")
        return self.unidades[serie]

    def disponibilidad(self, sku) -> int:
        return sum(
            1 for u in self.unidades.values()
            if u.sku == sku and u.estado is EstadoUnidad.DISPONIBLE
        )

    def apartar_unidad(self, serie, apartado_id):
        unidad = self._unidad(serie)
        if unidad.estado is not EstadoUnidad.DISPONIBLE:
            raise UnidadNoDisponible(f"serie {serie} no está disponible")
        unidad.estado = EstadoUnidad.APARTADO
        unidad.apartado_id = apartado_id

    def liberar_unidad(self, serie):
        unidad = self._unidad(serie)
        if unidad.estado is not EstadoUnidad.APARTADO:
            raise UnidadNoDisponible(f"serie {serie} no está apartada")
        unidad.estado = EstadoUnidad.DISPONIBLE
        unidad.apartado_id = None

    def marcar_en_transito(self, serie):
        unidad = self._unidad(serie)
        if unidad.estado is not EstadoUnidad.DISPONIBLE:
            raise UnidadNoDisponible(f"serie {serie} no está disponible")
        unidad.estado = EstadoUnidad.EN_TRANSITO

    def verificar_vendible(self, serie):
        unidad = self._unidad(serie)
        if unidad.estado is EstadoUnidad.APARTADO:
            raise ProductoApartado("un producto apartado no puede venderse a otro cliente")
        if unidad.estado is not EstadoUnidad.DISPONIBLE:
            raise UnidadNoDisponible(f"serie {serie} está {unidad.estado}")

    def vender_unidad(self, serie):
        self.verificar_vendible(serie)
        self._unidad(serie).estado = EstadoUnidad.VENDIDO


# ---------------------------------------------------------------- Aggregate: Venta
@dataclass(frozen=True)
class LineaVenta:
    serie: str
    sku: str
    precio: Decimal


@dataclass
class Venta:
    id: str
    lineas: list[LineaVenta]
    estado: EstadoVenta = EstadoVenta.PENDIENTE
    comprobante: Comprobante | None = None

    def __post_init__(self):
        if not self.lineas:
            raise ValueError("una venta requiere al menos un artículo")

    @property
    def total(self) -> Decimal:
        return dinero(sum((linea.precio for linea in self.lineas), Decimal(0)))

    def registrar_pago(self):
        if self.estado is not EstadoVenta.PENDIENTE:
            raise TransicionInvalida("solo una venta pendiente puede pagarse")
        self.estado = EstadoVenta.PAGADA
        self.comprobante = Comprobante(folio=f"T-{self.id}", codigo_qr=f"QR-{self.id}")

    def cancelar(self):
        if self.estado is not EstadoVenta.PENDIENTE:
            raise TransicionInvalida("solo una venta pendiente puede cancelarse")
        self.estado = EstadoVenta.CANCELADA
