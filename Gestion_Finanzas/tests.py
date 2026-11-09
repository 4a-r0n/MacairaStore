from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .admin import MovementFinanceForm
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

    def test_finance_category_choices_match_movement_type_and_put_empty_last(self):
        expense = CategoriaFinanciera.objects.create(
            nombre="Servicios de prueba", tipo="EXPENSE"
        )
        both = CategoriaFinanciera.objects.create(nombre="Compartida", tipo="BOTH")
        form = MovementFinanceForm()
        rendered = str(form["finance_category"])
        choices = list(form.fields["finance_category"].choices)

        self.assertIn(f'value="{self.income_category.pk}" data-kind="INCOME"', rendered)
        self.assertIn(f'value="{expense.pk}" data-kind="EXPENSE"', rendered)
        self.assertIn(f'value="{both.pk}" data-kind="BOTH"', rendered)
        self.assertEqual(choices[-1], ("", "Sin categoría"))
        income_choices = [
            choice[1]
            for choice in choices
            if choice[0]
            and choice[0] != str(expense.pk)
            and choice[1] != "Otros gastos"
        ]
        expense_form = MovementFinanceForm(data={"tipo": "EGRESO"})
        expense_choices = list(expense_form.fields["finance_category"].choices)
        expense_names = [
            choice[1]
            for choice in expense_choices
            if choice[0]
            and choice[0] != str(self.income_category.pk)
            and choice[1] != "Otros ingresos"
        ]
        self.assertEqual(income_choices[-1], "Otros ingresos")
        self.assertEqual(expense_names[-1], "Otros gastos")

    def test_employee_expense_selects_matching_finance_category(self):
        employee_category = CategoriaFinanciera.objects.get(nombre="Pago a empleados")
        employee = get_user_model().objects.create_user(username="finance-employee")
        employee.groups.add(Group.objects.get(name="Empleado"))
        form = MovementFinanceForm(data={
            "tipo": "EGRESO",
            "monto": "20",
            "metodo_pago": "TRANSFERENCIA",
            "tipo_cuenta": "USD",
            "plataforma": "",
            "descripcion": "Pago de empleado",
            "categoria_egreso": "PAGO_EMPLEADOS",
            "empleado": employee.pk,
            "trabajo": "",
            "finance_category": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["finance_category"], employee_category)

    def test_employee_finance_category_option_is_marked_for_auto_selection(self):
        employee_category = CategoriaFinanciera.objects.get(nombre="Pago a empleados")
        form = MovementFinanceForm()

        self.assertIn(
            f'value="{employee_category.pk}" data-kind="EXPENSE" '
            'data-expense-category="PAGO_EMPLEADOS"',
            str(form["finance_category"]),
        )

    def test_customer_refund_sets_finance_category_and_preserves_related_work(self):
        refund_category = CategoriaFinanciera.objects.get(nombre="Reembolsos")
        work = Trabajo.objects.create(
            cliente="Cliente reembolsado",
            descripcion="Trabajo con reembolso",
            monto_total=Decimal("50.00"),
        )
        form = MovementFinanceForm(data={
            "tipo": "EGRESO",
            "monto": "20",
            "metodo_pago": "TRANSFERENCIA",
            "tipo_cuenta": "USD",
            "plataforma": "",
            "descripcion": "Reembolso al cliente",
            "categoria_egreso": "REEMBOLSO_CLIENTE",
            "empleado": "",
            "trabajo": work.pk,
            "finance_category": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["finance_category"], refund_category)
        movement = form.save()
        self.assertEqual(movement.trabajo, work)

    def test_customer_refund_finance_category_is_marked_for_auto_selection(self):
        refund_category = CategoriaFinanciera.objects.get(nombre="Reembolsos")
        form = MovementFinanceForm()

        self.assertIn(
            f'value="{refund_category.pk}" data-kind="EXPENSE" '
            'data-expense-category="REEMBOLSO_CLIENTE"',
            str(form["finance_category"]),
        )

    def test_customer_advance_sets_finance_category_without_default(self):
        advance_category = CategoriaFinanciera.objects.get(nombre="Abonos de clientes")
        form = MovementFinanceForm()
        self.assertEqual(form.fields["tipo_ingreso"].initial, None)

        form = MovementFinanceForm(data={
            "tipo": "INGRESO",
            "tipo_ingreso": "ABONO_CLIENTES",
            "monto": "20",
            "metodo_pago": "TRANSFERENCIA",
            "tipo_cuenta": "USD",
            "plataforma": "",
            "descripcion": "Abono de cliente",
            "categoria_egreso": "",
            "empleado": "",
            "trabajo": "",
            "finance_category": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["finance_category"], advance_category)
        movement = form.save()
        self.assertEqual(movement.tipo_ingreso, "ABONO_CLIENTES")

    def test_other_income_sets_finance_category_without_default(self):
        other_income_category = CategoriaFinanciera.objects.get(nombre="Otros ingresos")
        form = MovementFinanceForm(data={
            "tipo": "INGRESO",
            "tipo_ingreso": "OTROS_INGRESOS",
            "monto": "20",
            "metodo_pago": "TRANSFERENCIA",
            "tipo_cuenta": "USD",
            "plataforma": "",
            "descripcion": "Ingreso no relacionado",
            "categoria_egreso": "",
            "empleado": "",
            "trabajo": "",
            "finance_category": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["finance_category"], other_income_category)
        movement = form.save()
        self.assertEqual(movement.tipo_ingreso, "OTROS_INGRESOS")

    def test_customer_advance_finance_category_is_marked_for_auto_selection(self):
        advance_category = CategoriaFinanciera.objects.get(nombre="Abonos de clientes")
        form = MovementFinanceForm()

        self.assertIn(
            f'value="{advance_category.pk}" data-kind="INCOME" '
            'data-income-category="ABONO_CLIENTES"',
            str(form["finance_category"]),
        )

    def test_finance_category_cannot_be_used_for_the_other_movement_type(self):
        expense = CategoriaFinanciera.objects.create(
            nombre="Servicios de prueba", tipo="EXPENSE"
        )
        form = MovementFinanceForm(data={
            "tipo": "INGRESO",
            "monto": "10",
            "metodo_pago": "EFECTIVO_USD",
            "tipo_cuenta": "",
            "plataforma": "",
            "descripcion": "Ingreso de prueba",
            "categoria_egreso": "",
            "empleado": "",
            "trabajo": "",
            "finance_category": expense.pk,
        })

        self.assertFalse(form.is_valid())
        self.assertIn("finance_category", form.errors)

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
        expense_form = MovementFinanceForm(data={"tipo": "EGRESO"})
        income_form = MovementFinanceForm(data={"tipo": "INGRESO"})

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

        form = MovementFinanceForm()
        available_employees = form.fields["empleado"].queryset

        self.assertIn(employee, available_employees)
        self.assertNotIn(non_employee, available_employees)
        self.assertNotIn(inactive_employee, available_employees)
        self.assertNotIn(self.admin, available_employees)

    def test_custom_movement_form_exposes_required_fields(self):
        response = self.client.get(reverse("movement_create"))
        html = response.content.decode()
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
