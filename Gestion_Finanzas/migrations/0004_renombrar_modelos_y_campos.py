from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("Gestion_Finanzas", "0003_seed_default_finance_categories"),
        ("gestion_publicidad", "0023_alter_movimientofinanciero_plataforma"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="exchangeratequote",
            name="Gestion_Fin_currenc_a818b9_idx",
        ),
        migrations.RemoveIndex(
            model_name="financemovement",
            name="Gestion_Fin_transac_6f7e48_idx",
        ),
        migrations.RenameModel(
            old_name="FinanceCategory",
            new_name="CategoriaFinanciera",
        ),
        migrations.RenameModel(
            old_name="ExchangeRateQuote",
            new_name="CotizacionTasaCambio",
        ),
        migrations.RenameModel(
            old_name="FinanceMovement",
            new_name="DetalleMovimientoFinanciero",
        ),
        migrations.RenameField(
            model_name="categoriafinanciera",
            old_name="name",
            new_name="nombre",
        ),
        migrations.RenameField(
            model_name="categoriafinanciera",
            old_name="kind",
            new_name="tipo",
        ),
        migrations.RenameField(
            model_name="categoriafinanciera",
            old_name="active",
            new_name="activa",
        ),
        migrations.RenameField(
            model_name="cotizaciontasacambio",
            old_name="currency",
            new_name="moneda",
        ),
        migrations.RenameField(
            model_name="cotizaciontasacambio",
            old_name="rate",
            new_name="tasa",
        ),
        migrations.RenameField(
            model_name="cotizaciontasacambio",
            old_name="source",
            new_name="fuente",
        ),
        migrations.RenameField(
            model_name="cotizaciontasacambio",
            old_name="effective_date",
            new_name="fecha_vigencia",
        ),
        migrations.RenameField(
            model_name="cotizaciontasacambio",
            old_name="confirmed_by",
            new_name="confirmada_por",
        ),
        migrations.RenameField(
            model_name="cotizaciontasacambio",
            old_name="confirmed_at",
            new_name="confirmada_en",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="movement",
            new_name="movimiento",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="transaction_date",
            new_name="fecha_transaccion",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="currency",
            new_name="moneda",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="category",
            new_name="categoria",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="quote",
            new_name="cotizacion",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="rate_snapshot",
            new_name="tasa_snapshot",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="rate_source_snapshot",
            new_name="fuente_tasa_snapshot",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="rate_effective_date_snapshot",
            new_name="fecha_vigencia_tasa_snapshot",
        ),
        migrations.RenameField(
            model_name="detallemovimientofinanciero",
            old_name="equivalent_ves",
            new_name="equivalente_ves",
        ),
        migrations.AlterField(
            model_name="cotizaciontasacambio",
            name="confirmada_por",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cotizaciones_tasa_cambio",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="detallemovimientofinanciero",
            name="movimiento",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="detalle_financiero",
                to="gestion_publicidad.movimientofinanciero",
            ),
        ),
        migrations.AlterField(
            model_name="detallemovimientofinanciero",
            name="categoria",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="movimientos_financieros",
                to="Gestion_Finanzas.categoriafinanciera",
            ),
        ),
        migrations.AlterField(
            model_name="detallemovimientofinanciero",
            name="cotizacion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="movimientos_financieros",
                to="Gestion_Finanzas.cotizaciontasacambio",
            ),
        ),
        migrations.AlterModelOptions(
            name="categoriafinanciera",
            options={
                "ordering": ["nombre"],
                "verbose_name": "categoría financiera",
                "verbose_name_plural": "categorías financieras",
            },
        ),
        migrations.AlterModelOptions(
            name="cotizaciontasacambio",
            options={
                "ordering": ["-fecha_vigencia", "-confirmada_en"],
                "verbose_name": "tasa de cambio",
                "verbose_name_plural": "tasas de cambio",
            },
        ),
        migrations.AlterModelOptions(
            name="detallemovimientofinanciero",
            options={"ordering": ["-fecha_transaccion", "-movimiento_id"]},
        ),
        migrations.AddIndex(
            model_name="cotizaciontasacambio",
            index=models.Index(
                fields=["moneda", "-fecha_vigencia"],
                name="Gestion_Fin_moneda_4f4878_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="detallemovimientofinanciero",
            index=models.Index(
                fields=["fecha_transaccion", "moneda"],
                name="Gestion_Fin_fecha_t_005315_idx",
            ),
        ),
    ]
