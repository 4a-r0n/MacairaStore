from django.db import migrations


def backfill_ledger_metadata(apps, schema_editor):
    Movement = apps.get_model("gestion_publicidad", "MovimientoFinanciero")
    FinanceMovement = apps.get_model("Gestion_Finanzas", "FinanceMovement")
    for movement in Movement.objects.all().iterator():
        currency = movement.tipo_cuenta if movement.tipo_cuenta in ("USD", "EUR", "VES", "USDT") else "USD"
        transaction_date = movement.fecha.date()
        FinanceMovement.objects.get_or_create(
            movement_id=movement.pk,
            defaults={"transaction_date": transaction_date, "currency": currency},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("Gestion_Finanzas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_ledger_metadata, migrations.RunPython.noop),
    ]
