from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from gestion_publicidad.forms import MovimientoForm
from gestion_publicidad.models import MovimientoFinanciero, Trabajo
from .models import (
    CategoriaFinanciera,
    DetalleMovimientoFinanciero,
)


class FinanceAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="finance-admin",
            email="finance@example.com",
            password="test-password",
        )
        self.income_category = CategoriaFinanciera.objects.create(
            nombre="Ventas", tipo="INCOME"
        )
        self.client.force_login(self.admin)

    def test_finance_uses_custom_pages_and_legacy_admin_redirects(self):
        finance_page = self.client.get(reverse("finance_list"))
        self.assertEqual(finance_page.status_code, 200)
        self.assertContains(finance_page, "Finanzas y movimientos")
        self.assertContains(finance_page, "Registrar movimiento")

        categories_page = self.client.get(reverse("category_list"))
        self.assertEqual(categories_page.status_code, 200)
        self.assertContains(categories_page, "Categorías financieras")

        for path in ("/admin/", "/admin/login/", "/admin/Gestion_Finanzas/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(
                    response,
                    reverse("dashboard"),
                    fetch_redirect_response=False,
                )

    def test_default_finance_categories_are_created_and_active(self):
        categories = {
            category.nombre: (category.tipo, category.activa)
            for category in CategoriaFinanciera.objects.filter(
                nombre__in=[
                    "Ventas/servicios",
                    "Abonos de clientes",
                    "Otros ingresos",
                    "Materiales e insumos",
                    "Pago a empleados",
                    "Servicios",
                    "Transporte",
                    "Publicidad",
                    "Mantenimiento",
                    "Reembolsos",
                    "Otros gastos",
                ]
            )
        }

        self.assertEqual(
            categories,
            {
                "Ventas/servicios": ("INCOME", True),
                "Abonos de clientes": ("INCOME", True),
                "Otros ingresos": ("INCOME", True),
                "Materiales e insumos": ("EXPENSE", True),
                "Pago a empleados": ("EXPENSE", True),
                "Servicios": ("EXPENSE", True),
                "Transporte": ("EXPENSE", True),
                "Publicidad": ("EXPENSE", True),
                "Mantenimiento": ("EXPENSE", True),
                "Reembolsos": ("EXPENSE", True),
                "Otros gastos": ("EXPENSE", True),
            },
        )

    def test_finance_category_type_defaults_to_none(self):
        category = CategoriaFinanciera(nombre="Categoría sin tipo")

        self.assertEqual(category.tipo, "")

    def test_work_payments_use_customer_advance_finance_category(self):
        for payment_type, advance, expected_amount in (
            ("TOTAL", None, Decimal("50.00")),
            ("ABONO", Decimal("12.00"), Decimal("12.00")),
        ):
            with self.subTest(payment_type=payment_type):
                work = Trabajo.objects.create(
                    cliente=f"Cliente {payment_type}",
                    descripcion="Trabajo de prueba",
                    monto_total=Decimal("50.00"),
                    tipo_pago=payment_type,
                    monto_abono=advance,
                    metodo_pago="EFECTIVO_USD",
                )
                movement = MovimientoFinanciero.objects.get(trabajo=work)

                self.assertEqual(movement.monto, expected_amount)
                self.assertEqual(
                    movement.detalle_financiero.categoria.nombre,
                    "Abonos de clientes",
                )

    def test_custom_movement_creation_saves_shared_ledger_and_category(self):
        response = self.client.post(
            reverse("movement_create"),
            {
                "tipo": "INGRESO",
                "monto": "10.00",
                "tipo_ingreso": "OTROS_INGRESOS",
                "categoria_egreso": "",
                "fecha_transaccion": "2026-11-05",
                "tipo_cuenta": "USD",
                "descripcion": "Venta de prueba",
                "metodo_pago": "TRANSFERENCIA",
                "plataforma": "",
                "empleado": "",
                "trabajo": "",
                "categoria_financiera": self.income_category.pk,
            },
        )
        self.assertEqual(response.status_code, 302)

        ledger_entry = MovimientoFinanciero.objects.get()
        metadata = DetalleMovimientoFinanciero.objects.get(movimiento=ledger_entry)
        self.assertEqual(ledger_entry.descripcion, "Venta de prueba")
        self.assertEqual(
            metadata.categoria,
            CategoriaFinanciera.objects.get(nombre="Otros ingresos"),
        )

    def test_old_advertising_movement_gets_finance_metadata(self):
        movement = MovimientoFinanciero.objects.create(
            tipo="INGRESO",
            monto="5.00",
            metodo_pago="EFECTIVO_USD",
            tipo_cuenta="USD",
            descripcion="Movimiento previo",
        )
        metadata = DetalleMovimientoFinanciero.objects.get(movimiento=movement)
        self.assertIsNone(metadata.categoria)
        self.assertEqual(metadata.fecha_transaccion, movement.fecha.date())

    def test_cash_movement_hides_account_type_without_conversion(self):
        response = self.client.post(
            reverse("movement_create"),
            {
                "tipo": "INGRESO",
                "monto": "10.00",
                "tipo_ingreso": "OTROS_INGRESOS",
                "fecha_transaccion": "2026-11-05",
                "tipo_cuenta": "USD",
                "descripcion": "Pago en efectivo",
                "metodo_pago": "EFECTIVO_USD",
                "plataforma": "",
                "categoria_egreso": "",
                "empleado": "",
                "trabajo": "",
                "categoria_financiera": self.income_category.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        movement = MovimientoFinanciero.objects.get()
        self.assertIsNone(movement.tipo_cuenta)
        self.assertIsNone(movement.plataforma)
        self.assertEqual(
            movement.detalle_financiero.categoria,
            CategoriaFinanciera.objects.get(nombre="Otros ingresos"),
        )

    def test_mobile_payment_sets_ves_and_national_bank(self):
        response = self.client.post(
            reverse("movement_create"),
            {
                "tipo": "INGRESO",
                "monto": "10.00",
                "tipo_ingreso": "OTROS_INGRESOS",
                "fecha_transaccion": "2026-11-05",
                "tipo_cuenta": "USD",
                "descripcion": "Pago móvil",
                "metodo_pago": "PAGO_MOVIL",
                "plataforma": "PAYPAL",
                "categoria_egreso": "",
                "empleado": "",
                "trabajo": "",
                "categoria_financiera": self.income_category.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        movement = MovimientoFinanciero.objects.get()
        self.assertEqual(movement.tipo_cuenta, "VES")
        self.assertEqual(movement.plataforma, "BANCO_NACIONAL")

    def test_card_payment_is_not_available_for_expenses(self):
        expense_form = MovimientoForm(data={"tipo": "EGRESO"})
        income_form = MovimientoForm(data={"tipo": "INGRESO"})

        self.assertNotIn(
            "TARJETA",
            [value for value, _label in expense_form.fields["metodo_pago"].choices],
        )
        self.assertIn(
            "TARJETA",
            [value for value, _label in income_form.fields["metodo_pago"].choices],
        )

    def test_employee_payment_selector_only_lists_employee_group_users(self):
        employee = get_user_model().objects.create_user(username="employee")
        non_employee = get_user_model().objects.create_user(username="non-employee")
        inactive_employee = get_user_model().objects.create_user(
            username="inactive-employee",
            is_active=False,
        )
        employee_group = Group.objects.get(name="Empleado")
        employee.groups.add(employee_group)
        inactive_employee.groups.add(employee_group)
        self.admin.groups.add(employee_group)

        form = MovimientoForm()
        available_employees = form.fields["empleado"].queryset

        self.assertIn(employee, available_employees)
        self.assertNotIn(non_employee, available_employees)
        self.assertNotIn(inactive_employee, available_employees)
        self.assertNotIn(self.admin, available_employees)

    def test_custom_movement_form_exposes_required_fields(self):
        response = self.client.get(reverse("movement_create"))
        self.assertEqual(response.status_code, 200)
        for field in (
            "tipo",
            "monto",
            "tipo_ingreso",
            "categoria_egreso",
            "fecha_transaccion",
            "metodo_pago",
            "tipo_cuenta",
            "plataforma",
            "descripcion",
            "categoria_financiera",
            "empleado",
        ):
            self.assertContains(response, f'name="{field}"')
        self.assertContains(response, "Tipo de egreso")
        self.assertContains(response, "Tipo de ingreso")
