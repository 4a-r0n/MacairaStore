from django.db import models
from django.utils import timezone


class CategoriaFinanciera(models.Model):
    TIPOS = [("INCOME", "Ingreso"), ("EXPENSE", "Egreso"), ("BOTH", "Ambos")]

    nombre = models.CharField("nombre", max_length=100, unique=True)
    tipo = models.CharField("tipo", max_length=8, choices=TIPOS, default="", blank=True)
    activa = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría financiera"
        verbose_name_plural = "categorías financieras"

    def __str__(self):
        return self.nombre


class DetalleMovimientoFinanciero(models.Model):
    """Detalles financieros asociados al registro de movimientos compartido."""

    movimiento = models.OneToOneField(
        "gestion_publicidad.MovimientoFinanciero",
        on_delete=models.CASCADE,
        related_name="detalle_financiero",
    )
    fecha_transaccion = models.DateField(default=timezone.localdate, db_index=True)
    categoria = models.ForeignKey(
        CategoriaFinanciera,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movimientos_financieros",
    )

    class Meta:
        ordering = ["-fecha_transaccion", "-movimiento_id"]

    def __str__(self):
        return f"{self.movimiento} ({self.fecha_transaccion})"
