from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from Gestion_Finanzas.models import CategoriaFinanciera, DetalleMovimientoFinanciero
from .models import (
    AreaInsumo,
    Insumo,
    MovimientoFinanciero,
    TareaTrabajoDia,
    TipoInsumo,
    Trabajo,
    TrabajoDia,
)


class DashboardTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="dashboard-admin",
            email="dashboard@example.com",
            password="test-password",
        )
        self.client.force_login(self.admin)

    def test_dashboard_uses_real_work_inventory_and_finance_records(self):
        work = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Producción de piezas gráficas",
            monto_total=Decimal("125.00"),
            tipo_pago="NADA",
        )
        area = AreaInsumo.objects.create(nombre="Impresión")
        Insumo.objects.create(
            nombre="Papel",
            area=area,
            cantidad_disponible=Decimal("5"),
            stock_minimo=Decimal("10"),
        )
        vinil = Insumo.objects.create(
            nombre="Vinil",
            area=area,
            tiene_tipos=True,
        )
        TipoInsumo.objects.create(
            insumo=vinil,
            nombre="Mate",
            unidad_medida="metros",
            cantidad_disponible=Decimal("0"),
        )
        jornada = TrabajoDia.objects.create(trabajo=work, fecha=date.today())
        TareaTrabajoDia.objects.create(jornada=jornada, descripcion="Preparar arte")
        MovimientoFinanciero.objects.create(
            tipo="INGRESO",
            monto=Decimal("25"),
            metodo_pago="EFECTIVO_USD",
            descripcion="Pago de prueba",
            trabajo=work,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumen del negocio")
        self.assertContains(response, "Cliente de prueba")
        self.assertContains(response, "Papel")
        self.assertContains(response, "Mate")
        self.assertContains(response, 'data-dashboard-search="inventory"')
        self.assertContains(response, "data-toggle-variants")
        self.assertContains(response, "Preparar arte")
        self.assertContains(response, "Pago de prueba")
        self.assertEqual(response.context["insumos_criticos_count"], 2)

    def test_dashboard_shows_own_login_page_to_anonymous_user(self):
        self.client.logout()

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gestion_publicidad/login.html")
        self.assertContains(response, "Usuario o correo electrónico")
        self.assertContains(response, "Recordarme siempre")
        self.assertContains(response, "/static/gestion_publicidad/css/dashboard.css")

    def test_login_accepts_email_and_session_expires_when_browser_closes(self):
        self.client.logout()
        user = get_user_model().objects.create_user(
            username="dashboard-login",
            email="login@example.com",
            password="secure-test-password",
        )

        response = self.client.post(
            reverse("login"),
            {"username": user.email, "password": "secure-test-password"},
        )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertIn("_auth_user_id", self.client.session)

    def test_remember_me_uses_configured_session_age_and_logout_invalidates_session(self):
        self.client.logout()
        user = get_user_model().objects.create_user(
            username="dashboard-remember",
            email="remember@example.com",
            password="secure-test-password",
        )

        self.client.post(
            reverse("login"),
            {
                "username": user.username,
                "password": "secure-test-password",
                "remember_me": "on",
            },
        )

        session = self.client.session
        self.assertFalse(session.get_expire_at_browser_close())
        self.assertEqual(session.get_expiry_age(), settings.SESSION_COOKIE_AGE)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTemplateUsed(self.client.get(reverse("dashboard")), "gestion_publicidad/login.html")

    def test_login_rejects_external_next_redirect(self):
        self.client.logout()
        user = get_user_model().objects.create_user(
            username="dashboard-next",
            password="secure-test-password",
        )

        response = self.client.post(
            f"{reverse('login')}?next=https://example.invalid/",
            {
                "username": user.username,
                "password": "secure-test-password",
                "next": "https://example.invalid/",
            },
        )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_monthly_finance_totals_filter_by_month_and_keep_currencies_separate(self):
        movements = [
            ("INGRESO", "100.00", "USD", date(2026, 11, 3)),
            ("EGRESO", "30.00", "USD", date(2026, 11, 8)),
            ("INGRESO", "400.00", "VES", date(2026, 11, 10)),
            ("EGRESO", "100.00", "VES", date(2026, 11, 14)),
            ("INGRESO", "25.00", "USDT", date(2026, 12, 1)),
        ]
        for kind, amount, currency, transaction_date in movements:
            movement = MovimientoFinanciero.objects.create(
                tipo=kind,
                monto=Decimal(amount),
                metodo_pago="TRANSFERENCIA",
                tipo_cuenta=currency,
                descripcion=f"Movimiento {currency} {transaction_date}",
            )
            detail = DetalleMovimientoFinanciero.objects.get(movimiento=movement)
            detail.fecha_transaccion = transaction_date
            detail.save(update_fields=("fecha_transaccion",))

        response = self.client.get(
            reverse("dashboard"),
            {
                "finance_month": "2026-11",
                "calendar_month": "2026-11",
                "section": "finanzas",
            },
        )

        self.assertEqual(response.status_code, 200)
        totals = {row["currency"]: row for row in response.context["totales_por_moneda"]}
        self.assertEqual(totals["USD"]["ingresos"], Decimal("100.00"))
        self.assertEqual(totals["USD"]["egresos"], Decimal("30.00"))
        self.assertEqual(totals["USD"]["saldo"], Decimal("70.00"))
        self.assertEqual(totals["VES"]["saldo"], Decimal("300.00"))
        self.assertNotIn("USDT", totals)
        self.assertEqual(len(response.context["movimientos_mes"]), 4)
        self.assertContains(response, "Detalle de movimientos · Noviembre 2026")

    def test_monthly_finance_handles_legacy_movement_types(self):
        legacy_movements = (
            ("ENTRADA", "INGRESO", "45.00"),
            ("SALIDA", "EGRESO", "12.00"),
        )
        for stored_kind, _, amount in legacy_movements:
            movement = MovimientoFinanciero.objects.create(
                tipo=stored_kind,
                monto=Decimal(amount),
                metodo_pago="TRANSFERENCIA",
                tipo_cuenta="USD",
                descripcion=f"Movimiento histórico {stored_kind}",
            )
            detail = DetalleMovimientoFinanciero.objects.get(movimiento=movement)
            detail.fecha_transaccion = date(2026, 10, 5)
            detail.save(update_fields=("fecha_transaccion",))

        response = self.client.get(
            reverse("dashboard"),
            {"finance_month": "2026-10", "calendar_month": "2026-11"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["conteo_movimientos_mes"],
            {"INGRESO": 1, "EGRESO": 1},
        )
        totals = response.context["totales_por_moneda"][0]
        self.assertEqual(totals["ingresos"], Decimal("45.00"))
        self.assertEqual(totals["egresos"], Decimal("12.00"))

    def test_invalid_calendar_and_finance_months_fall_back_to_current_month(self):
        response = self.client.get(
            reverse("dashboard"),
            {"finance_month": "2026-99", "calendar_month": "9999-12"},
        )

        current_month = timezone.localdate().replace(day=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mes_financiero"], current_month)
        self.assertEqual(
            response.context["calendario"]["mes_actual"],
            current_month,
        )
        self.assertContains(response, "El mes indicado no es válido")

    def test_calendar_is_rendered_in_the_panel_with_real_journeys_and_tasks(self):
        work = Trabajo.objects.create(
            cliente="Cliente del panel calendario",
            descripcion="Trabajo calendario",
            monto_total=Decimal("80"),
            tipo_pago="NADA",
        )
        journey = TrabajoDia.objects.create(
            trabajo=work,
            fecha=date(2026, 11, 5),
        )
        TareaTrabajoDia.objects.create(
            jornada=journey,
            descripcion="Tarea visible en calendario",
        )

        response = self.client.get(
            reverse("dashboard"),
            {"calendar_month": "2026-11", "section": "jornadas"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Noviembre 2026")
        self.assertContains(response, "Cliente del panel calendario")
        self.assertContains(response, "Tarea visible en calendario")
        self.assertContains(response, "calendar_month=2026-11")

    def test_legacy_admin_urls_redirect_to_the_custom_dashboard(self):
        for path in ("/admin/", "/admin/login/?next=/admin/", "/admin/auth/user/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(
                    response,
                    reverse("dashboard"),
                    fetch_redirect_response=False,
                )
        self.assertEqual(self.client.get("/admin/login/?next=/admin/").status_code, 302)

    def test_task_completion_post_returns_to_journeys_and_persists(self):
        work = Trabajo.objects.create(
            cliente="Cliente",
            descripcion="Trabajo",
            monto_total=Decimal("50"),
            tipo_pago="NADA",
        )
        jornada = TrabajoDia.objects.create(trabajo=work, fecha=date.today())
        tarea = TareaTrabajoDia.objects.create(
            jornada=jornada,
            descripcion="Revisar diseño",
        )

        response = self.client.post(
            reverse("alternar_tarea", args=[tarea.pk]),
        )

        self.assertRedirects(
            response,
            f"{reverse('dashboard')}#jornadas",
            fetch_redirect_response=False,
        )
        tarea.refresh_from_db()
        self.assertTrue(tarea.completada)
        self.assertIsNotNone(tarea.completada_en)

    def test_task_completion_requires_work_change_permission(self):
        user = get_user_model().objects.create_user(
            username="dashboard-viewer",
            password="test-password",
        )
        work = Trabajo.objects.create(
            cliente="Cliente",
            descripcion="Trabajo",
            monto_total=Decimal("50"),
            tipo_pago="NADA",
        )
        jornada = TrabajoDia.objects.create(trabajo=work, fecha=date.today())
        tarea = TareaTrabajoDia.objects.create(
            jornada=jornada,
            descripcion="Revisar diseño",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("alternar_tarea", args=[tarea.pk]))

        self.assertEqual(response.status_code, 403)
        tarea.refresh_from_db()
        self.assertFalse(tarea.completada)

    def test_non_staff_user_does_not_get_dashboard_data_from_model_permissions(self):
        user = get_user_model().objects.create_user(
            username="dashboard-non-staff",
            password="test-password",
        )
        permission = Permission.objects.get(
            content_type__app_label="gestion_publicidad",
            codename="view_trabajo",
        )
        user.user_permissions.add(permission)
        Trabajo.objects.create(
            cliente="Cliente privado",
            descripcion="Trabajo privado",
            monto_total=Decimal("50"),
            tipo_pago="NADA",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tu cuenta no tiene permisos")
        self.assertNotContains(response, "Cliente privado")

    def test_native_management_pages_render_without_admin_links(self):
        routes = (
            "work_list",
            "journey_list",
            "receivables_list",
            "inventory_list",
            "finance_list",
            "category_list",
            "work_create",
            "journey_create",
            "inventory_create",
            "inventory_restock",
            "movement_create",
            "category_create",
        )
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "/admin/")

    def test_native_work_and_inventory_forms_persist_records(self):
        work_response = self.client.post(
            reverse("work_create"),
            {
                "cliente": "Cliente interfaz",
                "descripcion": "Diseño para evento",
                "monto_total": "120.00",
                "tipo_pago": "NADA",
                "monto_abono": "0",
                "metodo_pago": "",
                "plataforma": "NINGUNA",
                "tipo_cuenta": "USD",
                "estado": "PENDIENTE",
                "fecha_limite": "",
            },
        )
        self.assertEqual(work_response.status_code, 302)
        work = Trabajo.objects.get(cliente="Cliente interfaz")
        self.assertEqual(work.saldo_pendiente, Decimal("120.00"))

        area = AreaInsumo.objects.create(nombre="Impresión interfaz")
        inventory_response = self.client.post(
            reverse("inventory_create"),
            {
                "area": area.pk,
                "nombre": "Cartulina interfaz",
                "tiene_tipos": "",
                "cantidad_disponible": "15.00",
                "stock_minimo": "4.00",
                "unidad_medida": "pliegos",
                "tipos-TOTAL_FORMS": "1",
                "tipos-INITIAL_FORMS": "0",
                "tipos-MIN_NUM_FORMS": "0",
                "tipos-MAX_NUM_FORMS": "1000",
                "tipos-0-nombre": "",
                "tipos-0-unidad_medida": "",
                "tipos-0-cantidad_disponible": "0.00",
                "tipos-0-stock_minimo": "20.00",
            },
        )
        self.assertEqual(inventory_response.status_code, 302)
        supply = Insumo.objects.get(nombre="Cartulina interfaz")
        self.assertEqual(supply.cantidad_disponible, Decimal("15.00"))

    def test_native_journey_form_updates_tasks_and_consumes_stock(self):
        work = Trabajo.objects.create(
            cliente="Cliente jornada interfaz",
            descripcion="Impresión",
            monto_total=Decimal("70"),
            tipo_pago="NADA",
        )
        area = AreaInsumo.objects.create(nombre="Materiales interfaz")
        supply = Insumo.objects.create(
            nombre="Papel interfaz",
            area=area,
            cantidad_disponible=Decimal("8"),
            stock_minimo=Decimal("1"),
        )

        response = self.client.post(
            reverse("journey_create"),
            {
                "trabajo": work.pk,
                "fecha": "2026-11-05",
                "notas": "Turno de impresión",
                "tareas-TOTAL_FORMS": "1",
                "tareas-INITIAL_FORMS": "0",
                "tareas-MIN_NUM_FORMS": "0",
                "tareas-MAX_NUM_FORMS": "1000",
                "tareas-0-descripcion": "Preparar archivo",
                "tareas-0-completada": "",
                "materiales-TOTAL_FORMS": "1",
                "materiales-INITIAL_FORMS": "0",
                "materiales-MIN_NUM_FORMS": "0",
                "materiales-MAX_NUM_FORMS": "1000",
                "materiales-0-area": area.pk,
                "materiales-0-insumo": supply.pk,
                "materiales-0-tipo_insumo": "",
                "materiales-0-cantidad_utilizada": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        journey = TrabajoDia.objects.get(trabajo=work)
        self.assertEqual(journey.tareas.get().descripcion, "Preparar archivo")
        self.assertEqual(journey.materiales_utilizados.get().cantidad_utilizada, Decimal("2"))
        supply.refresh_from_db()
        self.assertEqual(supply.cantidad_disponible, Decimal("6"))

    def test_native_movement_form_saves_finance_date_and_category(self):
        category = CategoriaFinanciera.objects.create(
            nombre="Venta interfaz", tipo="INCOME", activa=True
        )
        response = self.client.post(
            reverse("movement_create"),
            {
                "tipo": "INGRESO",
                "monto": "42.50",
                "tipo_ingreso": "OTROS_INGRESOS",
                "categoria_egreso": "",
                "metodo_pago": "EFECTIVO_USD",
                "plataforma": "",
                "tipo_cuenta": "",
                "descripcion": "Venta de prueba desde interfaz",
                "trabajo": "",
                "empleado": "",
                "fecha_transaccion": "2026-11-04",
                "categoria_financiera": category.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        movement = MovimientoFinanciero.objects.get(
            descripcion="Venta de prueba desde interfaz"
        )
        detail = DetalleMovimientoFinanciero.objects.get(movimiento=movement)
        self.assertEqual(detail.fecha_transaccion, date(2026, 11, 4))
        self.assertEqual(
            detail.categoria,
            CategoriaFinanciera.objects.get(nombre="Otros ingresos"),
        )

    def test_native_inventory_variant_and_restock_forms_update_variant_stock(self):
        area = AreaInsumo.objects.create(nombre="Área variantes interfaz")
        response = self.client.post(
            reverse("inventory_create"),
            {
                "area": area.pk,
                "nombre": "Vinil interfaz",
                "tiene_tipos": "on",
                "cantidad_disponible": "0",
                "stock_minimo": "0",
                "unidad_medida": "metros",
                "tipos-TOTAL_FORMS": "1",
                "tipos-INITIAL_FORMS": "0",
                "tipos-MIN_NUM_FORMS": "0",
                "tipos-MAX_NUM_FORMS": "1000",
                "tipos-0-nombre": "Mate",
                "tipos-0-unidad_medida": "metros",
                "tipos-0-cantidad_disponible": "4",
                "tipos-0-stock_minimo": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        supply = Insumo.objects.get(nombre="Vinil interfaz")
        variant = supply.tipos.get(nombre="Mate")

        response = self.client.post(
            reverse("inventory_restock"),
            {
                "area": area.pk,
                "insumo": supply.pk,
                "tipo_insumo": variant.pk,
                "cantidad": "3.5",
            },
        )
        self.assertEqual(response.status_code, 302)
        variant.refresh_from_db()
        self.assertEqual(variant.cantidad_disponible, Decimal("7.50"))

    def test_native_edit_and_delete_flows_update_records(self):
        work = Trabajo.objects.create(
            cliente="Cliente editable",
            descripcion="Descripción anterior",
            monto_total=Decimal("65"),
            tipo_pago="NADA",
        )
        response = self.client.post(
            reverse("work_edit", args=(work.pk,)),
            {
                "cliente": "Cliente actualizado",
                "descripcion": "Descripción actualizada",
                "monto_total": "65",
                "tipo_pago": "NADA",
                "monto_abono": "0",
                "metodo_pago": "",
                "plataforma": "NINGUNA",
                "tipo_cuenta": "USD",
                "estado": "EN_PROCESO",
                "fecha_limite": "2026-11-15",
            },
        )
        self.assertEqual(response.status_code, 302)
        work.refresh_from_db()
        self.assertEqual(work.cliente, "Cliente actualizado")
        self.assertEqual(work.estado, "EN_PROCESO")

        area = AreaInsumo.objects.create(nombre="Área editable")
        supply = Insumo.objects.create(
            nombre="Material editable",
            area=area,
            cantidad_disponible=Decimal("5"),
            stock_minimo=Decimal("2"),
            unidad_medida="unidades",
        )
        response = self.client.post(
            reverse("inventory_edit", args=(supply.pk,)),
            {
                "area": area.pk,
                "nombre": "Material actualizado",
                "tiene_tipos": "",
                "cantidad_disponible": "9",
                "stock_minimo": "3",
                "unidad_medida": "metros",
                "tipos-TOTAL_FORMS": "1",
                "tipos-INITIAL_FORMS": "0",
                "tipos-MIN_NUM_FORMS": "0",
                "tipos-MAX_NUM_FORMS": "1000",
                "tipos-0-nombre": "",
                "tipos-0-unidad_medida": "",
                "tipos-0-cantidad_disponible": "0.00",
                "tipos-0-stock_minimo": "20.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        supply.refresh_from_db()
        self.assertEqual(supply.nombre, "Material actualizado")
        self.assertEqual(supply.cantidad_disponible, Decimal("9"))

        category = CategoriaFinanciera.objects.create(
            nombre="Categoría editable", tipo="BOTH", activa=True
        )
        response = self.client.post(
            reverse("category_edit", args=(category.pk,)),
            {"nombre": "Categoría actualizada", "tipo": "EXPENSE", "activa": "on"},
        )
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertEqual(category.nombre, "Categoría actualizada")

        response = self.client.post(reverse("work_delete", args=(work.pk,)))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Trabajo.objects.filter(pk=work.pk).exists())
        response = self.client.post(reverse("inventory_delete", args=(supply.pk,)))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Insumo.objects.filter(pk=supply.pk).exists())

    def test_native_management_routes_enforce_permissions(self):
        user = get_user_model().objects.create_user(
            username="native-viewer",
            password="secure-test-password",
            is_staff=True,
        )
        view_permission = Permission.objects.get(
            content_type__app_label="gestion_publicidad",
            codename="view_trabajo",
        )
        user.user_permissions.add(view_permission)
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("work_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("work_create")).status_code, 403)

    def test_login_does_not_redirect_back_to_legacy_admin_after_logout(self):
        self.client.logout()
        user = get_user_model().objects.create_user(
            username="no-admin-redirect",
            password="secure-test-password",
        )

        response = self.client.post(
            f"{reverse('login')}?next=/admin/",
            {
                "username": user.username,
                "password": "secure-test-password",
                "next": "/admin/",
            },
        )
        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "gestion_publicidad/dashboard.html")

    def test_administrator_can_edit_all_work_fields(self):
        work = Trabajo.objects.create(
            cliente="Cliente administrador",
            descripcion="Diseño anterior",
            monto_total=Decimal("80"),
            tipo_pago="NADA",
        )
        administrator = get_user_model().objects.create_user(
            username="staff-administrator",
            password="secure-test-password",
            is_staff=True,
        )
        administrator.groups.add(Group.objects.get_or_create(name="Administrador")[0])
        change_permission = Permission.objects.get(
            content_type__app_label="gestion_publicidad",
            codename="change_trabajo",
        )
        administrator.user_permissions.add(change_permission)
        self.client.force_login(administrator)

        response = self.client.get(reverse("work_edit", args=(work.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="monto_total"')
        self.assertContains(response, 'name="tipo_pago"')
        self.assertContains(response, 'name="metodo_pago"')
        self.assertContains(response, 'name="plataforma"')
        self.assertContains(response, 'name="tipo_cuenta"')

        response = self.client.post(
            reverse("work_edit", args=(work.pk,)),
            {
                "cliente": "Cliente actualizado por admin",
                "descripcion": "Diseño actualizado",
                "monto_total": "95.00",
                "tipo_pago": "NADA",
                "monto_abono": "0",
                "metodo_pago": "",
                "plataforma": "NINGUNA",
                "tipo_cuenta": "USD",
                "estado": "EN_PROCESO",
                "fecha_limite": "2026-12-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        work.refresh_from_db()
        self.assertEqual(work.monto_total, Decimal("95.00"))
        self.assertEqual(work.descripcion, "Diseño actualizado")

    def test_employee_work_edit_keeps_the_limited_field_set(self):
        work = Trabajo.objects.create(
            cliente="Cliente empleado",
            descripcion="Diseño del empleado",
            monto_total=Decimal("80"),
            tipo_pago="NADA",
        )
        employee = get_user_model().objects.create_user(
            username="staff-employee",
            password="secure-test-password",
            is_staff=True,
        )
        employee.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="gestion_publicidad",
                codename="change_trabajo",
            )
        )
        self.client.force_login(employee)

        response = self.client.get(reverse("work_edit", args=(work.pk,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="cliente"')
        self.assertContains(response, 'name="estado"')
        self.assertNotContains(response, 'name="monto_total"')
