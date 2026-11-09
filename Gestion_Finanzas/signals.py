from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from gestion_publicidad.models import MovimientoFinanciero
from .models import DetalleMovimientoFinanciero


@receiver(post_save, sender=MovimientoFinanciero, dispatch_uid="finance_metadata_for_shared_ledger")
def add_finance_metadata(sender, instance, created, **kwargs):
    if not created:
        return
    transaction_date = timezone.localtime(instance.fecha).date() if timezone.is_aware(instance.fecha) else instance.fecha.date()
    DetalleMovimientoFinanciero.objects.get_or_create(
        movimiento=instance,
        defaults={"fecha_transaccion": transaction_date},
    )
