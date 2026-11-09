from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from Gestion_Finanzas.models import CategoriaFinanciera
from .forms import MovimientoForm, TrabajoForm
from .forms import PersonalUserForm
from .models import (
    DEFAULT_EMPLOYEE_PERMISSION_CODENAMES,
    Insumo,
    Trabajo,
    TrabajoDia,
    TareaTrabajoDia,
)


class PaymentFormWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="ui-admin",
            email="ui-admin@example.com",
            password="Secure-test-password-2026!",
        )
        self.client.force_login(self.user)
        self.work = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100.00"),
        )
        categories = (
            ("Abonos de clientes", "INCOME"),
            ("Otros ingresos", "INCOME"),
            ("Materiales e insumos", "EXPENSE"),
            ("Pago a empleados", "EXPENSE"),
            ("Reembolsos", "EXPENSE"),
        )
        self.categories = {}
        for name, kind in categories:
            category, _ = CategoriaFinanciera.objects.update_or_create(
                nombre=name,
                defaults={"tipo": kind, "activa": True},
            )
            self.categories[name] = category

    def test_job_payment_fields_match_the_movement_payment_choices(self):
        job_form = TrabajoForm()
        movement_form = MovimientoForm()
        for field in ("metodo_pago", "plataforma", "tipo_cuenta"):
            self.assertEqual(
                list(job_form.fields[field].choices),
                list(movement_form.fields[field].choices),
            )

    def test_job_form_cleans_hidden_payment_values(self):
        form_data = {
            "cliente": "Sin pago",
            "descripcion": "Trabajo pendiente de pago",
            "monto_total": "100.00",
            "tipo_pago": "NADA",
            "monto_abono": "30.00",
            "metodo_pago": "PAGO_MOVIL",
            "plataforma": "BANCO_NACIONAL",
            "tipo_cuenta": "VES",
            "estado": "PENDIENTE",
            "fecha_limite": "",
        }
        form = TrabajoForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["monto_abono"])
        self.assertIsNone(form.cleaned_data["metodo_pago"])

        form_data["tipo_pago"] = "TOTAL"
        form = TrabajoForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["monto_abono"])

    def test_new_work_page_renders_payment_fields_hidden_for_no_payment(self):
        response = self.client.get(reverse("work_create"))

        self.assertEqual(response.status_code, 200)
        for field in ("monto_abono", "metodo_pago", "plataforma", "tipo_cuenta"):
            self.assertContains(response, f'hidden style="display: none;" data-field="{field}"')
        self.assertContains(response, 'src="/static/gestion_publicidad/js/app_forms.js?v=20261106-3"')
        stylesheet = (
            Path(__file__).parent
            / "static"
            / "gestion_publicidad"
            / "css"
            / "dashboard.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".form-field[hidden] { display: none !important; }", stylesheet)

    def test_total_payment_hides_only_the_advance_amount(self):
        form = TrabajoForm(data={
            "cliente": "",
            "descripcion": "",
            "monto_total": "",
            "tipo_pago": "TOTAL",
            "monto_abono": "",
            "metodo_pago": "",
            "plataforma": "",
            "tipo_cuenta": "",
            "estado": "PENDIENTE",
            "fecha_limite": "",
        })
        self.assertEqual(form.initially_hidden_fields, {"monto_abono"})
        html = render_to_string(
            "gestion_publicidad/partials/form_fields.html",
            {"form": form},
        )
        self.assertIn('hidden style="display: none;" data-field="monto_abono"', html)
        for field in ("metodo_pago", "plataforma", "tipo_cuenta"):
            self.assertNotIn(f'hidden style="display: none;" data-field="{field}"', html)

    def test_other_income_uses_its_category_and_mobile_payment_defaults(self):
        form = MovimientoForm(data={
            "tipo": "INGRESO",
            "monto": "30.00",
            "tipo_ingreso": "OTROS_INGRESOS",
            "categoria_egreso": "",
            "fecha_transaccion": date.today().isoformat(),
            "metodo_pago": "PAGO_MOVIL",
            "plataforma": "PAYPAL",
            "tipo_cuenta": "USD",
            "descripcion": "Ingreso de prueba",
            "trabajo": self.work.pk,
            "empleado": "",
            "categoria_financiera": self.categories["Abonos de clientes"].pk,
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["categoria_financiera"],
            self.categories["Otros ingresos"],
        )
        self.assertEqual(form.cleaned_data["plataforma"], "BANCO_NACIONAL")
        self.assertEqual(form.cleaned_data["tipo_cuenta"], "VES")
        self.assertIsNone(form.cleaned_data["trabajo"])

    def test_customer_refund_sets_financial_category_and_keeps_selected_work(self):
        form = MovimientoForm(data={
            "tipo": "EGRESO",
            "monto": "10.00",
            "tipo_ingreso": "",
            "categoria_egreso": "REEMBOLSO_CLIENTE",
            "fecha_transaccion": date.today().isoformat(),
            "metodo_pago": "TRANSFERENCIA",
            "plataforma": "BANCO_NACIONAL",
            "tipo_cuenta": "USD",
            "descripcion": "Reembolso",
            "trabajo": self.work.pk,
            "empleado": "",
            "categoria_financiera": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["categoria_financiera"],
            self.categories["Reembolsos"],
        )
        self.assertEqual(form.cleaned_data["trabajo"], self.work)

    def test_expense_category_and_payment_panels_are_rendered_for_dynamic_rules(self):
        response = self.client.get(reverse("movement_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-movement-type')
        self.assertContains(response, 'data-category-kind="INCOME"')
        self.assertContains(response, 'data-category-kind="EXPENSE"')
        self.assertContains(response, 'data-payment-method')


class PersonalManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="personal-admin",
            email="personal-admin@example.com",
            password="Secure-test-password-2026!",
        )
        self.client.force_login(self.admin)

    def test_administrator_can_create_edit_view_and_delete_an_employee(self):
        view_work = Permission.objects.get(
            content_type__app_label="gestion_publicidad",
            codename="view_trabajo",
        )
        response = self.client.post(
            reverse("personal_create"),
            {
                "username": "empleado-ui",
                "first_name": "Ana",
                "last_name": "Prueba",
                "email": "ana@example.com",
                "is_active": "on",
                "role": "Empleado",
                "permissions": [view_work.pk],
                "password1": "Strong-test-password-2030!",
                "password2": "Strong-test-password-2030!",
            },
        )
        self.assertEqual(response.status_code, 302)
        employee = get_user_model().objects.get(username="empleado-ui")
        self.assertTrue(employee.is_staff)
        self.assertTrue(employee.check_password("Strong-test-password-2030!"))
        self.assertTrue(employee.groups.filter(name="Empleado").exists())
        self.assertEqual(list(employee.user_permissions.all()), [view_work])

        response = self.client.get(reverse("personal_detail", args=(employee.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empleado")
        self.assertContains(response, "Permisos individuales")

        response = self.client.post(
            reverse("personal_edit", args=(employee.pk,)),
            {
                "username": "empleado-ui",
                "first_name": "Ana María",
                "last_name": "Prueba",
                "email": "ana@example.com",
                "is_active": "on",
                "role": "Empleado",
                "permissions": [view_work.pk],
                "password1": "",
                "password2": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertEqual(employee.first_name, "Ana María")

        response = self.client.post(reverse("personal_delete", args=(employee.pk,)))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=employee.pk).exists())

    def test_employee_cannot_open_personal_management(self):
        employee = get_user_model().objects.create_user(
            username="employee-no-personal",
            password="Secure-test-password-2026!",
            is_staff=True,
        )
        employee.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="gestion_publicidad",
                codename="view_trabajo",
            )
        )
        self.client.force_login(employee)

        self.assertEqual(self.client.get(reverse("personal_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("personal_create")).status_code, 403)

    def test_employee_permissions_allow_business_actions_but_limit_finance_access(self):
        employee = get_user_model().objects.create_user(
            username="employee-default-permissions",
            password="Secure-test-password-2026!",
        )
        employee.is_staff = True
        employee.save(update_fields=("is_staff",))
        employee.groups.add(Group.objects.get_or_create(name="Empleado")[0])
        employee.user_permissions.set(Permission.objects.filter(
            content_type__app_label="gestion_publicidad",
            codename__in=DEFAULT_EMPLOYEE_PERMISSION_CODENAMES,
        ))

        self.assertTrue(employee.is_staff)
        self.assertTrue(employee.groups.filter(name="Empleado").exists())
        for model in (
            "areainsumo",
            "insumo",
            "tipoinsumo",
            "trabajo",
            "trabajoinsumo",
            "trabajodia",
            "tareatrabajodia",
        ):
            for action in ("view", "add", "change"):
                with self.subTest(model=model, action=action):
                    self.assertTrue(
                        employee.has_perm(f"gestion_publicidad.{action}_{model}")
                    )

        self.assertTrue(employee.has_perm("gestion_publicidad.view_movimientofinanciero"))
        self.assertTrue(employee.has_perm("gestion_publicidad.add_movimientofinanciero"))
        self.assertFalse(employee.has_perm("gestion_publicidad.change_movimientofinanciero"))
        self.assertFalse(employee.has_perm("gestion_publicidad.delete_movimientofinanciero"))
        self.assertFalse(employee.has_perm("Gestion_Finanzas.view_categoriafinanciera"))
        self.assertFalse(employee.has_perm("auth.view_user"))
        self.client.force_login(employee)
        self.assertEqual(self.client.get(reverse("work_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("movement_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("movement_edit", args=(1,))).status_code, 403)
        self.assertEqual(self.client.get(reverse("personal_list")).status_code, 403)

    def test_administrator_role_has_full_business_access(self):
        response = self.client.post(
            reverse("personal_create"),
            {
                "username": "admin-role-ui",
                "first_name": "Admin",
                "last_name": "Rol",
                "email": "admin-role@example.com",
                "is_active": "on",
                "role": "Administrador",
                "password1": "Strong-test-password-2030!",
                "password2": "Strong-test-password-2030!",
            },
        )

        self.assertEqual(response.status_code, 302)
        administrator = get_user_model().objects.get(username="admin-role-ui")
        self.assertTrue(administrator.groups.filter(name="Administrador").exists())
        self.assertFalse(administrator.user_permissions.exists())
        self.client.force_login(administrator)
        self.assertEqual(self.client.get(reverse("work_create")).status_code, 200)

    def test_new_employee_account_form_defaults_to_employee_with_actions_selected(self):
        form = PersonalUserForm()

        self.assertEqual(form.initial["role"], "Empleado")
        self.assertEqual(
            set(form.initial["permissions"].values_list("codename", flat=True)),
            {
                f"{action}_{model}"
                for model in (
                    "areainsumo",
                    "insumo",
                    "tipoinsumo",
                    "trabajo",
                    "trabajoinsumo",
                    "trabajodia",
                    "tareatrabajodia",
                )
                for action in ("view", "add", "change")
            } | {"view_movimientofinanciero", "add_movimientofinanciero"},
        )
        self.assertNotIn(
            "change_movimientofinanciero",
            form.fields["permissions"].queryset.values_list("codename", flat=True),
        )

    def test_new_employee_form_saves_the_default_actions_when_selected(self):
        permissions = PersonalUserForm().fields["permissions"].queryset
        form = PersonalUserForm(data={
            "username": "employee-defaults-saved",
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "role": "Empleado",
            "permissions": list(permissions.values_list("pk", flat=True)),
            "password1": "Strong-test-password-2030!",
            "password2": "Strong-test-password-2030!",
        })

        self.assertTrue(form.is_valid(), form.errors)
        employee = form.save()
        self.assertEqual(
            set(employee.user_permissions.values_list("codename", flat=True)),
            set(DEFAULT_EMPLOYEE_PERMISSION_CODENAMES),
        )


class InventoryVisualTests(TestCase):
    def test_inventory_row_has_one_delete_action_and_icon_only_search_submit(self):
        administrator = get_user_model().objects.create_superuser(
            username="inventory-ui-admin",
            email="inventory-ui-admin@example.com",
            password="Secure-test-password-2026!",
        )
        Insumo.objects.create(nombre="Papel para impresión")
        self.client.force_login(administrator)

        response = self.client.get(reverse("inventory_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count(">Eliminar</a>"), 1)
        self.assertContains(response, "inventory-row-actions")
        self.assertNotContains(response, ">Buscar</button>")


class JourneyCalendarWorkflowTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="calendar-ui-admin",
            email="calendar-ui-admin@example.com",
            password="Secure-test-password-2026!",
        )
        self.client.force_login(self.admin)
        self.work = Trabajo.objects.create(
            cliente="Cliente de jornada",
            descripcion="Trabajo con jornada",
            monto_total=Decimal("25.00"),
        )

    def test_dashboard_keeps_calendar_and_date_filtered_journey_targets(self):
        journey = TrabajoDia.objects.create(
            trabajo=self.work,
            fecha=date(2026, 11, 12),
        )
        TareaTrabajoDia.objects.create(jornada=journey, descripcion="Preparar")

        response = self.client.get(
            reverse("dashboard"),
            {"calendar_month": "2026-11", "section": "jornadas"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-calendar-date="2026-11-12"')
        self.assertContains(response, 'hidden style="display: none;" data-journey-date="2026-11-12"')
        self.assertContains(response, "APARTADO 1 · CALENDARIO")
        self.assertContains(response, "APARTADO 2 · JORNADAS")
        self.assertContains(response, 'data-clear-calendar-filter>Mostrar todas</button>')
        dashboard_script = (
            Path(__file__).parent
            / "static"
            / "gestion_publicidad"
            / "js"
            / "dashboard.js"
        ).read_text(encoding="utf-8")
        self.assertIn('filterJourneysByDate("", true)', dashboard_script)
        self.assertIn('card.style.display = visible ? "" : "none"', dashboard_script)

    def test_journey_form_allows_multiple_tasks_and_calendar_sets_date(self):
        response = self.client.get(
            reverse("journey_create"),
            {"fecha": "2026-11-12"},
        )
        self.assertContains(response, 'value="2026-11-12"')
        self.assertContains(response, 'data-add-formset="tareas"')
        self.assertContains(response, "__prefix__")

        response = self.client.post(
            reverse("journey_create"),
            {
                "trabajo": self.work.pk,
                "fecha": "2026-11-12",
                "notas": "",
                "tareas-TOTAL_FORMS": "2",
                "tareas-INITIAL_FORMS": "0",
                "tareas-MIN_NUM_FORMS": "0",
                "tareas-MAX_NUM_FORMS": "1000",
                "tareas-0-descripcion": "Preparar",
                "tareas-1-descripcion": "Instalar",
                "materiales-TOTAL_FORMS": "0",
                "materiales-INITIAL_FORMS": "0",
                "materiales-MIN_NUM_FORMS": "0",
                "materiales-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 302)
        journey = TrabajoDia.objects.get(trabajo=self.work, fecha=date(2026, 11, 12))
        self.assertEqual(
            set(journey.tareas.values_list("descripcion", flat=True)),
            {"Preparar", "Instalar"},
        )
