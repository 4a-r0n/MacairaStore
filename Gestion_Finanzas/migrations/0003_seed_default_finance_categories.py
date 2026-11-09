from django.db import migrations


DEFAULT_CATEGORIES = (
    ("Ventas/servicios", "INCOME"),
    ("Abonos de clientes", "INCOME"),
    ("Otros ingresos", "INCOME"),
    ("Materiales e insumos", "EXPENSE"),
    ("Pago a empleados", "EXPENSE"),
    ("Servicios", "EXPENSE"),
    ("Transporte", "EXPENSE"),
    ("Publicidad", "EXPENSE"),
    ("Mantenimiento", "EXPENSE"),
    ("Reembolsos", "EXPENSE"),
    ("Otros gastos", "EXPENSE"),
)


def create_default_categories(apps, schema_editor):
    FinanceCategory = apps.get_model("Gestion_Finanzas", "FinanceCategory")
    for name, kind in DEFAULT_CATEGORIES:
        FinanceCategory.objects.get_or_create(
            name=name,
            defaults={"kind": kind, "active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("Gestion_Finanzas", "0002_backfill_shared_ledger_metadata"),
    ]

    operations = [
        migrations.RunPython(create_default_categories, migrations.RunPython.noop),
    ]
