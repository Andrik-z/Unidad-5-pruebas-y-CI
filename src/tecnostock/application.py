"""Servicios de aplicación de TecnoStock: coordinan dominio, repositorios y pasarela."""
from src.tecnostock.domain import (
    Apartado,
    PagoDeclinado,
    ReglaDeNegocioError,
)


class ApartadoNoEncontrado(ReglaDeNegocioError):
    pass


class ApartadoService:
    def __init__(self, repo, monederos, session):
        self.repo = repo
        self.monederos = monederos
        self.session = session

    def iniciar_apartado(self, apartado_id, cliente_id, lineas, ahora) -> Apartado:
        activos = self.repo.contar_articulos_activos(cliente_id)
        apartado = Apartado.crear(apartado_id, cliente_id, lineas, activos, ahora)
        self.repo.guardar(apartado)
        self.session.commit()
        return apartado

    def confirmar_apartado(self, apartado_id, monto, ahora) -> Apartado:
        apartado = self.repo.obtener_por_id(apartado_id)
        if apartado is None:
            raise ApartadoNoEncontrado(apartado_id)
        apartado.aplicar_anticipo(monto, ahora)
        self.repo.guardar(apartado)
        self.session.commit()
        return apartado

    def procesar_vencimientos(self, ahora) -> int:
        """Vence apartados de 30 días y abona su anticipo al monedero, en una transacción."""
        vencidos = 0
        try:
            for apartado in self.repo.listar_confirmados():
                if apartado.vencer(ahora):
                    self.repo.guardar(apartado)
                    monedero = self.monederos.obtener_por_cliente(apartado.cliente_id)
                    monedero.abonar_anticipo(apartado.id, apartado.anticipo_pagado)
                    self.monederos.guardar(monedero)
                    vencidos += 1
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return vencidos


class CajaService:
    """Cobro de ventas con pasarela externa (se simula con Mock en las pruebas)."""

    def __init__(self, gateway):
        self.gateway = gateway

    def cobrar_venta(self, venta, inventario):
        # 1) validar ANTES de cobrar: nunca se cobra un producto apartado o no disponible
        for linea in venta.lineas:
            inventario.verificar_vendible(linea.serie)
        # 2) cobrar; si se declina, la venta se cancela sin tocar el inventario (US-14)
        if not self.gateway.charge(venta.total):
            venta.cancelar()
            raise PagoDeclinado("payment declined")
        # 3) solo con pago aprobado: comprobante con QR y salida del inventario (US-13)
        venta.registrar_pago()
        for linea in venta.lineas:
            inventario.vender_unidad(linea.serie)
        return venta.comprobante
