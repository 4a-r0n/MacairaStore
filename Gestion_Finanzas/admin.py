from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils import timezone

from gestion_publicidad.admin_mixins import DashboardReturnMixin
from gestion_publicidad.models import MovimientoFinanciero
from .models import (
    CategoriaFinanciera,
    DetalleMovimientoFinanciero,
)


class FinanceCategorySelect(forms.Select):
    def __init__(
        self,
        *args,
        category_kinds=None,
        employee_payment_category_id=None,
        customer_refund_category_id=None,
        customer_advance_category_id=None,
        other_income_category_id=None,
        **kwargs,
    ):
        self.category_kinds = category_kinds or {}
        self.employee_payment_category_id = employee_payment_category_id
        self.customer_refund_category_id = customer_refund_category_id
        self.customer_advance_category_id = customer_advance_category_id
        self.other_income_category_id = other_income_category_id
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        category_id = getattr(value, "value", value)
        category_kind = self.category_kinds.get(str(category_id))
        if category_kind:
            option["attrs"]["data-kind"] = category_kind
        if str(category_id) == str(self.employee_payment_category_id):
            option["attrs"]["data-expense-category"] = "PAGO_EMPLEADOS"
        if str(category_id) == str(self.customer_refund_category_id):
            option["attrs"]["data-expense-category"] = "REEMBOLSO_CLIENTE"
        if str(category_id) == str(self.customer_advance_category_id):
            option["attrs"]["data-income-category"] = "ABONO_CLIENTES"
        if str(category_id) == str(self.other_income_category_id):
            option["attrs"]["data-income-category"] = "OTROS_INGRESOS"
        return option


class FinanceCategoryAdmin(DashboardReturnMixin, admin.ModelAdmin):
    list_display = ("nombre", "tipo", "activa")
    list_filter = ("tipo", "activa")
    search_fields = ("nombre",)
    ordering = ("nombre",)


class MovementFinanceForm(forms.ModelForm):
    finance_category = forms.ModelChoiceField(
        label="Categoría financiera",
        queryset=CategoriaFinanciera.objects.filter(activa=True),
        required=False,
        empty_label="Sin categoría",
    )
    class Meta:
        model = MovimientoFinanciero
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empleado"].queryset = get_user_model().objects.filter(
            groups__name="Empleado",
            is_active=True,
            is_superuser=False,
        ).order_by("first_name", "last_name", "username")
        categories = list(
            CategoriaFinanciera.objects.filter(activa=True).order_by("nombre")
        )
        categories.sort(
            key=lambda category: category.nombre in ("Otros ingresos", "Otros gastos")
        )
        employee_payment_category = next(
            (
                category
                for category in categories
                if category.nombre == "Pago a empleados"
                and category.tipo in ("EXPENSE", "BOTH")
            ),
            None,
        )
        customer_refund_category = next(
            (
                category
                for category in categories
                if category.nombre == "Reembolsos"
                and category.tipo in ("EXPENSE", "BOTH")
            ),
            None,
        )
        customer_advance_category = next(
            (
                category
                for category in categories
                if category.nombre == "Abonos de clientes"
                and category.tipo in ("INCOME", "BOTH")
            ),
            None,
        )
        other_income_category = next(
            (
                category
                for category in categories
                if category.nombre == "Otros ingresos"
                and category.tipo in ("INCOME", "BOTH")
            ),
            None,
        )
        self.fields["finance_category"].queryset = CategoriaFinanciera.objects.filter(
            activa=True
        )
        self.fields["finance_category"].empty_label = None
        self.fields["finance_category"].widget = FinanceCategorySelect(
            category_kinds={
                str(category.pk): category.tipo for category in categories
            },
            employee_payment_category_id=(
                employee_payment_category.pk if employee_payment_category else None
            ),
            customer_refund_category_id=(
                customer_refund_category.pk if customer_refund_category else None
            ),
            customer_advance_category_id=(
                customer_advance_category.pk if customer_advance_category else None
            ),
            other_income_category_id=(
                other_income_category.pk if other_income_category else None
            ),
        )
        self.fields["finance_category"].choices = [
            (str(category.pk), category.nombre) for category in categories
        ] + [("", "Sin categoría")]
        movimiento_tipo = (
            self.data.get("tipo")
            if self.is_bound
            else self.initial.get("tipo", self.instance.tipo or "INGRESO")
        )
        metodos_pago = [
            choice for choice in self.fields["metodo_pago"].choices if choice[0]
        ]
        if movimiento_tipo == "EGRESO":
            metodos_pago = [
                choice for choice in metodos_pago if choice[0] != "TARJETA"
            ]
        self.fields["metodo_pago"].choices = [
            ("", "- Select an option -"),
            *metodos_pago,
        ]
        if self.instance.pk:
            metadata = DetalleMovimientoFinanciero.objects.filter(
                movimiento=self.instance
            ).first()
            if metadata:
                self.fields["finance_category"].initial = metadata.categoria_id

    def clean(self):
        data = super().clean()
        category = data.get("finance_category")
        if data.get("tipo") == "INGRESO" and data.get("tipo_ingreso") == "ABONO_CLIENTES":
            category = self.fields["finance_category"].queryset.filter(
                nombre="Abonos de clientes",
                tipo__in=("INCOME", "BOTH"),
            ).first()
            if category is None:
                self.add_error(
                    "finance_category",
                    "Activa la categoría financiera 'Abonos de clientes' para continuar.",
                )
            else:
                data["finance_category"] = category
        elif data.get("tipo") == "INGRESO" and data.get("tipo_ingreso") == "OTROS_INGRESOS":
            category = self.fields["finance_category"].queryset.filter(
                nombre="Otros ingresos",
                tipo__in=("INCOME", "BOTH"),
            ).first()
            if category is None:
                self.add_error(
                    "finance_category",
                    "Activa la categoría financiera 'Otros ingresos' para continuar.",
                )
            else:
                data["finance_category"] = category
        elif (
            data.get("tipo") == "EGRESO"
            and data.get("categoria_egreso")
            in ("PAGO_EMPLEADOS", "REEMBOLSO_CLIENTE")
        ):
            finance_category_name = {
                "PAGO_EMPLEADOS": "Pago a empleados",
                "REEMBOLSO_CLIENTE": "Reembolsos",
            }[data["categoria_egreso"]]
            category = self.fields["finance_category"].queryset.filter(
                nombre=finance_category_name,
                tipo__in=("EXPENSE", "BOTH"),
            ).first()
            if category is None:
                self.add_error(
                    "finance_category",
                    f"Activa la categoría financiera '{finance_category_name}' para continuar.",
                )
            else:
                data["finance_category"] = category
        else:
            category = data.get("finance_category")
        category_kind = "INCOME" if data.get("tipo") == "INGRESO" else "EXPENSE"
        if category and category.tipo not in (category_kind, "BOTH"):
            self.add_error(
                "finance_category",
                "Selecciona una categoría correspondiente al tipo de movimiento.",
            )
        if data.get("metodo_pago") == "EFECTIVO_USD":
            data["tipo_cuenta"] = None
            data["plataforma"] = None
        elif data.get("metodo_pago") == "PAGO_MOVIL":
            data["tipo_cuenta"] = "VES"
            data["plataforma"] = "BANCO_NACIONAL"
        if data.get("tipo") == "EGRESO" and data.get("metodo_pago") == "TARJETA":
            self.add_error("metodo_pago", "Tarjeta no está disponible para egresos.")
        return data


class MovimientoFinancieroAdmin(DashboardReturnMixin, admin.ModelAdmin):
    form = MovementFinanceForm
    list_display = (
        "id",
        "tipo",
        "categoria_egreso",
        "tipo_ingreso",
        "empleado",
        "monto",
        "tipo_cuenta",
        "metodo_pago",
        "descripcion",
        "trabajo",
        "fecha",
    )
    list_filter = ("tipo", "metodo_pago", "tipo_cuenta", "fecha")
    search_fields = ("descripcion", "trabajo__cliente", "empleado__username", "empleado__first_name", "empleado__last_name")
    fieldsets = (
        ("Movimiento", {"fields": (
            "tipo", "categoria_egreso", "trabajo", "empleado", "monto", "tipo_ingreso",
            "metodo_pago", "tipo_cuenta", "plataforma", "descripcion",
        )}),
        ("Finanzas", {"fields": ("finance_category",)}),
    )

    class Media:
        js = (
            "gestion_publicidad/js/gestion_pagos.js",
            "gestion_finanzas/finance_categories.js",
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        metadata, _ = DetalleMovimientoFinanciero.objects.get_or_create(
            movimiento=obj,
            defaults={
                "fecha_transaccion": timezone.localtime(obj.fecha).date(),
            },
        )
        metadata.categoria = form.cleaned_data.get("finance_category")
        metadata.save()


def register_finance_models(admin_site):
    admin_site.unregister(MovimientoFinanciero)
    admin_site.register(CategoriaFinanciera, FinanceCategoryAdmin)
    admin_site.register(MovimientoFinanciero, MovimientoFinancieroAdmin)
