from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from .forms import MovimientoForm, ReabastecerInsumoForm, TrabajoInsumoForm
from .models import (
    AreaInsumo,
    Insumo,
    MovimientoFinanciero,
    TipoInsumo,
    Trabajo,
    TrabajoDia,
    TrabajoInsumo,
    TrabajoPorCobrar,
    TareaTrabajoDia,
)


class CantidadesNoNegativasTests(TestCase):
    def test_campos_numericos_rechazan_valores_negativos(self):
        campos = (
            (Insumo, "cantidad_disponible"),
            (Insumo, "stock_minimo"),
            (TipoInsumo, "cantidad_disponible"),
            (TipoInsumo, "stock_minimo"),
            (Trabajo, "monto_total"),
            (Trabajo, "saldo_pendiente"),
            (Trabajo, "monto_abono"),
            (TrabajoInsumo, "cantidad_utilizada"),
            (MovimientoFinanciero, "monto"),
        )

        for modelo, nombre_campo in campos:
            with self.subTest(modelo=modelo.__name__, campo=nombre_campo):
                campo = modelo._meta.get_field(nombre_campo)
                with self.assertRaises(ValidationError):
                    campo.clean(Decimal("-1"), None)


class ControlStockTests(TestCase):
    def test_pantalla_propia_reabastece_stock_y_persiste_el_incremento(self):
        area = AreaInsumo.objects.create(nombre="Área de prueba")
        insumo = Insumo.objects.create(
            nombre="Papel",
            area=area,
            cantidad_disponible=Decimal("10"),
        )
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("inventory_restock"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="area"')
        self.assertContains(respuesta, 'name="insumo"')
        self.assertContains(respuesta, 'name="cantidad"')
        respuesta = self.client.post(
            reverse("inventory_restock"),
            {
                "area": area.pk,
                "insumo": insumo.pk,
                "tipo_insumo": "",
                "cantidad": "4",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        insumo.refresh_from_db()
        self.assertEqual(insumo.cantidad_disponible, Decimal("14"))

    def test_reabastecer_varios_insumos_en_un_envio(self):
        area = AreaInsumo.objects.create(nombre="Área de prueba")
        papel = Insumo.objects.create(
            nombre="Papel",
            area=area,
            cantidad_disponible=Decimal("10"),
        )
        vinil = Insumo.objects.create(
            nombre="Vinil",
            area=area,
            tiene_tipos=True,
            cantidad_disponible=Decimal("50"),
        )
        tipo_vinil = TipoInsumo.objects.create(
            insumo=vinil,
            nombre="Vinil opaco",
            unidad_medida="metros",
            cantidad_disponible=Decimal("8"),
        )
        usuario = get_user_model().objects.create_superuser(
            username="admin-multiple",
            email="admin-multiple@example.com",
            password="admin-multiple-password",
        )
        self.client.force_login(usuario)

        for supply, variant, quantity in (
            (papel, "", "4.5"),
            (vinil, tipo_vinil.pk, "2"),
        ):
            respuesta = self.client.post(
                reverse("inventory_restock"),
                {
                    "area": area.pk,
                    "insumo": supply.pk,
                    "tipo_insumo": variant,
                    "cantidad": quantity,
                },
            )
            self.assertEqual(respuesta.status_code, 302)
        papel.refresh_from_db()
        vinil.refresh_from_db()
        tipo_vinil.refresh_from_db()
        self.assertEqual(papel.cantidad_disponible, Decimal("14.5"))
        self.assertEqual(vinil.cantidad_disponible, Decimal("50"))
        self.assertEqual(tipo_vinil.cantidad_disponible, Decimal("10"))

    def test_estado_stock_usa_los_limites_definidos(self):
        casos = (
            ("0", "Agotado"),
            ("0.01", "Crítico"),
            ("20", "Crítico"),
            ("20.01", "Poco stock"),
            ("30", "Poco stock"),
            ("30.01", "Óptimo"),
        )

        insumo = Insumo(nombre="Papel bond")
        for cantidad, estado in casos:
            with self.subTest(cantidad=cantidad):
                insumo.cantidad_disponible = Decimal(cantidad)
                self.assertEqual(insumo.estado_stock, estado)

    def test_estado_stock_de_tipo_se_calcula_independientemente(self):
        insumo = Insumo.objects.create(nombre="Vinil", tiene_tipos=True)
        tipo = TipoInsumo.objects.create(
            insumo=insumo,
            nombre="Vinil opaco",
            unidad_medida="metros",
            cantidad_disponible=Decimal("25"),
        )

        self.assertEqual(tipo.estado_stock, "Poco stock")
        self.assertEqual(insumo.estado_stock, "Agotado")

    def test_minimo_configurable_ajusta_alerta_de_control_stock(self):
        insumo = Insumo(
            nombre="Papel",
            stock_minimo=Decimal("5"),
            cantidad_disponible=Decimal("5"),
        )
        self.assertEqual(insumo.estado_stock, "Crítico")

        insumo.cantidad_disponible = Decimal("15")
        self.assertEqual(insumo.estado_stock, "Poco stock")

        insumo.cantidad_disponible = Decimal("15.01")
        self.assertEqual(insumo.estado_stock, "Óptimo")

    def test_reabastecer_suma_stock_del_insumo_sin_reemplazarlo(self):
        area = AreaInsumo.objects.create(nombre="Área de prueba")
        insumo = Insumo.objects.create(
            nombre="Papel",
            area=area,
            cantidad_disponible=Decimal("12"),
        )
        form = ReabastecerInsumoForm({
            "area": area.pk,
            "insumo": insumo.pk,
            "tipo_insumo": "",
            "cantidad": "3.50",
        })

        self.assertTrue(form.is_valid(), form.errors)
        form.reabastecer()

        insumo.refresh_from_db()
        self.assertEqual(insumo.cantidad_disponible, Decimal("15.50"))

    def test_reabastecer_actualiza_solo_el_tipo_seleccionado(self):
        area = AreaInsumo.objects.create(nombre="Área de prueba")
        insumo = Insumo.objects.create(
            nombre="Vinil",
            area=area,
            tiene_tipos=True,
            cantidad_disponible=Decimal("80"),
        )
        tipo = TipoInsumo.objects.create(
            insumo=insumo,
            nombre="Vinil opaco",
            unidad_medida="metros",
            cantidad_disponible=Decimal("10"),
        )
        form = ReabastecerInsumoForm({
            "area": area.pk,
            "insumo": insumo.pk,
            "tipo_insumo": tipo.pk,
            "cantidad": "5",
        })

        self.assertTrue(form.is_valid(), form.errors)
        form.reabastecer()

        insumo.refresh_from_db()
        tipo.refresh_from_db()
        self.assertEqual(tipo.cantidad_disponible, Decimal("15"))
        self.assertEqual(insumo.cantidad_disponible, Decimal("80"))

    def test_reabastecer_requiere_tipo_cuando_insumo_tiene_variantes(self):
        area = AreaInsumo.objects.create(nombre="Área de prueba")
        insumo = Insumo.objects.create(nombre="Vinil", area=area, tiene_tipos=True)
        TipoInsumo.objects.create(
            insumo=insumo,
            nombre="Vinil opaco",
            unidad_medida="metros",
        )
        form = ReabastecerInsumoForm({
            "area": area.pk,
            "insumo": insumo.pk,
            "tipo_insumo": "",
            "cantidad": "5",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("tipo_insumo", form.errors)

    def test_consumir_insumo_sin_tipos_descuenta_su_stock(self):
        insumo = Insumo.objects.create(
            nombre="Papel bond",
            cantidad_disponible=Decimal("40"),
            unidad_medida="unidades",
        )
        trabajo = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
        )

        TrabajoInsumo.objects.create(
            trabajo=trabajo,
            area=insumo.area,
            insumo=insumo,
            cantidad_utilizada=Decimal("5"),
        )

        insumo.refresh_from_db()
        self.assertEqual(insumo.cantidad_disponible, Decimal("35"))


class AreaInsumoTrabajoTests(TestCase):
    def test_api_devuelve_solo_el_nombre_del_insumo(self):
        area = AreaInsumo.objects.create(nombre="Ahumar")
        Insumo.objects.create(nombre="Vinil", area=area)
        usuario = get_user_model().objects.create_superuser(
            username="admin-api-insumos",
            email="api-insumos@example.com",
            password="secure-test-password",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get("/api/insumos/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["insumos"][0]["nombre"], "Vinil")

    def test_api_de_insumos_requiere_autenticacion_y_permiso(self):
        area = AreaInsumo.objects.create(nombre="Área privada")
        Insumo.objects.create(nombre="Material privado", area=area)

        respuesta = self.client.get("/api/insumos/")

        self.assertEqual(respuesta.status_code, 302)
        usuario = get_user_model().objects.create_user(
            username="lector-sin-permiso",
            password="secure-test-password",
        )
        self.client.force_login(usuario)
        respuesta = self.client.get("/api/insumos/")
        self.assertEqual(respuesta.status_code, 403)

    def test_insumo_sin_area_se_asigna_a_sin_area(self):
        insumo = Insumo.objects.create(nombre="Cartulina")

        self.assertEqual(insumo.area.nombre, "Sin área")

    def test_formulario_de_trabajo_inicia_en_sin_area_y_filtra_insumos(self):
        no_area = AreaInsumo.objects.get(nombre="Sin área")
        otro_area = AreaInsumo.objects.create(nombre="Ahumar")
        insumo_sin_area = Insumo.objects.create(nombre="Cartulina", area=no_area)
        insumo_ahumar = Insumo.objects.create(nombre="Vinil", area=otro_area)

        form = TrabajoInsumoForm(prefix="insumos_utilizados-0")

        self.assertIsNone(form["area"].value())
        self.assertFalse(form.fields["insumo"].queryset.exists())

        edit_form = TrabajoInsumoForm(
            prefix="insumos_utilizados-0",
            instance=TrabajoInsumo(area=no_area, insumo=insumo_sin_area),
        )
        self.assertEqual(edit_form["area"].value(), no_area.pk)
        self.assertEqual(list(edit_form.fields["insumo"].queryset), [insumo_sin_area])
        self.assertNotIn(insumo_ahumar, form.fields["insumo"].queryset)

    def test_trabajo_no_acepta_insumo_de_otra_area(self):
        area_a = AreaInsumo.objects.create(nombre="Área A")
        area_b = AreaInsumo.objects.create(nombre="Área B")
        insumo = Insumo.objects.create(nombre="Vinil", area=area_b)
        trabajo = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
        )

        with self.assertRaisesMessage(ValueError, "no pertenece al área elegida"):
            TrabajoInsumo.objects.create(
                trabajo=trabajo,
                area=area_a,
                insumo=insumo,
                cantidad_utilizada=Decimal("1"),
            )


class TrabajoInsumoStockTests(TestCase):
    def setUp(self):
        area = AreaInsumo.objects.create(nombre="Ahumar")
        self.insumo = Insumo.objects.create(
            nombre="Vinil",
            area=area,
            tiene_tipos=True,
        )
        self.tipo = TipoInsumo.objects.create(
            insumo=self.insumo,
            nombre="Vinil opaco",
            unidad_medida="metros",
            cantidad_disponible=Decimal("100"),
        )
        self.trabajo = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
        )

    def crear_consumo(self, cantidad):
        return TrabajoInsumo.objects.create(
            trabajo=self.trabajo,
            area=self.insumo.area,
            insumo=self.insumo,
            tipo_insumo=self.tipo,
            cantidad_utilizada=Decimal(cantidad),
        )

    def test_editar_consumo_no_rechaza_stock_ya_descontado(self):
        consumo = self.crear_consumo("70")
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.cantidad_disponible, Decimal("30"))

        consumo = TrabajoInsumo.objects.get(pk=consumo.pk)
        consumo.save()

        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.cantidad_disponible, Decimal("30"))

    def test_editar_consumo_aplica_diferencia_y_eliminar_restituye_stock(self):
        consumo = self.crear_consumo("70")

        consumo.cantidad_utilizada = Decimal("80")
        consumo.save()
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.cantidad_disponible, Decimal("20"))

        consumo.cantidad_utilizada = Decimal("60")
        consumo.save()
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.cantidad_disponible, Decimal("40"))

        consumo.delete()
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.cantidad_disponible, Decimal("100"))

    def test_cambiar_tipo_restituye_el_stock_anterior(self):
        consumo = self.crear_consumo("70")
        otro_tipo = TipoInsumo.objects.create(
            insumo=self.insumo,
            nombre="Vinil translúcido",
            unidad_medida="metros",
            cantidad_disponible=Decimal("50"),
        )

        consumo.tipo_insumo = otro_tipo
        consumo.cantidad_utilizada = Decimal("10")
        consumo.save()

        self.tipo.refresh_from_db()
        otro_tipo.refresh_from_db()
        self.assertEqual(self.tipo.cantidad_disponible, Decimal("100"))
        self.assertEqual(otro_tipo.cantidad_disponible, Decimal("40"))

    def test_formulario_muestra_error_si_aumenta_consumo_sin_stock(self):
        consumo = self.crear_consumo("70")
        for cantidad, valido in (("70", True), ("101", False)):
            with self.subTest(cantidad=cantidad):
                datos = {
                    "insumos_utilizados-0-area": str(self.insumo.area_id),
                    "insumos_utilizados-0-insumo": str(self.insumo.pk),
                    "insumos_utilizados-0-tipo_insumo": str(self.tipo.pk),
                    "insumos_utilizados-0-cantidad_utilizada": cantidad,
                }
                formulario = TrabajoInsumoForm(
                    data=datos,
                    instance=consumo,
                    prefix="insumos_utilizados-0",
                )

                self.assertEqual(formulario.is_valid(), valido)
                if not valido:
                    self.assertIn("Stock insuficiente", str(formulario.errors["cantidad_utilizada"]))


class FechaLimiteTrabajoTests(TestCase):
    @patch("gestion_publicidad.models.timezone.localdate", return_value=date(2026, 10, 29))
    def test_indicador_de_entrega_se_calcula_segun_dias_restantes(self, _):
        casos = (
            (None, "Sin fecha"),
            (date(2026, 11, 3), "A tiempo"),
            (date(2026, 11, 2), "Poco tiempo"),
            (date(2026, 11, 1), "Poco tiempo"),
            (date(2026, 10, 31), "Fecha límite"),
            (date(2026, 10, 30), "Fecha límite"),
            (date(2026, 10, 29), "Fecha límite"),
            (date(2026, 10, 28), "Expirado"),
        )

        for fecha_limite, estado in casos:
            with self.subTest(fecha_limite=fecha_limite):
                trabajo = Trabajo(fecha_limite=fecha_limite)
                self.assertEqual(trabajo.estado_entrega, estado)

    @patch("gestion_publicidad.models.timezone.localdate")
    def test_trabajo_pasa_a_expirado_automaticamente_al_pasar_fecha(self, localdate):
        trabajo = Trabajo(fecha_limite=date(2026, 10, 29))

        localdate.return_value = date(2026, 10, 29)
        self.assertEqual(trabajo.estado_entrega, "Fecha límite")

        localdate.return_value = date(2026, 10, 30)
        self.assertEqual(trabajo.estado_entrega, "Expirado")

    def test_finalizar_trabajo_lo_marca_entregado_y_limpia_fecha_limite(self):
        trabajo = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
            fecha_limite=date(2026, 11, 3),
        )

        trabajo.estado = "FINALIZADO"
        trabajo.save()
        trabajo.refresh_from_db()

        self.assertTrue(trabajo.entregado)
        self.assertIsNone(trabajo.fecha_limite)
        self.assertEqual(trabajo.estado_entrega, "Entregado")

    def test_finalizacion_con_update_fields_guarda_entregado_y_limpia_fecha(self):
        trabajo = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
            fecha_limite=date(2026, 11, 3),
        )
        trabajo.estado = "FINALIZADO"
        trabajo.save(update_fields=("estado",))
        trabajo.refresh_from_db()

        self.assertTrue(trabajo.entregado)
        self.assertIsNone(trabajo.fecha_limite)


class TrabajosPorCobrarTests(TestCase):
    def crear_trabajo(self, cliente, estado, saldo):
        trabajo = Trabajo.objects.create(
            cliente=cliente,
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
        )
        trabajo.estado = estado
        trabajo.saldo_pendiente = Decimal(saldo)
        trabajo.save()
        return trabajo

    def test_lista_solo_trabajos_finalizados_con_saldo_pendiente(self):
        por_cobrar = self.crear_trabajo("Pendiente de cobro", "FINALIZADO", "25")
        self.crear_trabajo("Pagado", "FINALIZADO", "0")
        self.crear_trabajo("Aún en proceso", "EN_PROCESO", "25")

        self.assertEqual(
            list(TrabajoPorCobrar.objects.values_list("pk", flat=True)),
            [por_cobrar.pk],
        )

    def test_trabajo_sale_del_apartado_al_pagar_o_cambiar_estado(self):
        trabajo = self.crear_trabajo("Pendiente de cobro", "FINALIZADO", "25")
        self.assertTrue(TrabajoPorCobrar.objects.filter(pk=trabajo.pk).exists())

        trabajo.saldo_pendiente = Decimal("0")
        trabajo.save()
        self.assertFalse(TrabajoPorCobrar.objects.filter(pk=trabajo.pk).exists())

        trabajo.saldo_pendiente = Decimal("25")
        trabajo.estado = "EN_PROCESO"
        trabajo.save()
        self.assertFalse(TrabajoPorCobrar.objects.filter(pk=trabajo.pk).exists())

    def test_cuentas_por_cobrar_y_trabajos_usan_las_pantallas_propias(self):
        self.crear_trabajo("Pendiente de cobro", "FINALIZADO", "25")
        self.crear_trabajo("Pagado", "FINALIZADO", "0")
        usuario = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("receivables_list"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pendiente de cobro")
        self.assertNotContains(respuesta, "Pagado")
        self.assertEqual(
            self.client.get(reverse("work_list")).status_code,
            200,
        )
        self.assertRedirects(
            self.client.get("/admin/"),
            reverse("dashboard"),
            fetch_redirect_response=False,
        )


class CategoriasEgresoTests(TestCase):
    def setUp(self):
        self.trabajo = Trabajo.objects.create(
            cliente="Cliente de prueba",
            descripcion="Trabajo de prueba",
            monto_total=Decimal("100"),
        )

    def test_egreso_pide_categoria_y_no_asocia_trabajo(self):
        datos = {
            "tipo": "EGRESO",
            "monto": "25",
            "metodo_pago": "EFECTIVO_USD",
            "plataforma": "",
            "tipo_cuenta": "USD",
            "descripcion": "Compra de tinta",
            "trabajo": str(self.trabajo.pk),
            "categoria_egreso": "COMPRA_MATERIAL",
            "fecha_transaccion": "2026-11-09",
            "tipo_ingreso": "",
            "categoria_financiera": "",
            "empleado": "",
        }
        formulario = MovimientoForm(data=datos)

        self.assertTrue(formulario.is_valid(), formulario.errors)
        movimiento = formulario.save()
        self.assertIsNone(movimiento.trabajo)
        self.assertEqual(movimiento.categoria_egreso, "COMPRA_MATERIAL")
        self.assertIsNone(movimiento.empleado)

    def test_pago_a_empleado_exige_seleccion_y_guarda_el_empleado(self):
        empleado = get_user_model().objects.create_user(
            username="empleado-pago",
            password="test-password",
            first_name="Ana",
            last_name="Pérez",
        )
        empleado_group, _ = Group.objects.get_or_create(name="Empleado")
        empleado.groups.add(empleado_group)
        datos = {
            "tipo": "EGRESO",
            "monto": "75",
            "metodo_pago": "EFECTIVO_USD",
            "plataforma": "",
            "tipo_cuenta": "USD",
            "descripcion": "Pago semanal",
            "trabajo": "",
            "categoria_egreso": "PAGO_EMPLEADOS",
            "empleado": "",
            "fecha_transaccion": "2026-11-09",
            "tipo_ingreso": "",
            "categoria_financiera": "",
        }
        formulario_sin_empleado = MovimientoForm(data=datos)
        self.assertFalse(formulario_sin_empleado.is_valid())
        self.assertIn("empleado", formulario_sin_empleado.errors)

        datos["empleado"] = str(empleado.pk)
        formulario = MovimientoForm(data=datos)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        movimiento = formulario.save()
        self.assertEqual(movimiento.empleado, empleado)
        self.assertIsNone(movimiento.trabajo)

    def test_formulario_solo_ofrece_usuarios_del_grupo_empleado(self):
        empleado = get_user_model().objects.create_user(
            username="empleado-elegible",
            password="test-password",
        )
        administrador = get_user_model().objects.create_superuser(
            username="admin-no-elegible",
            email="admin@example.com",
            password="test-password",
        )
        grupo_empleados, _ = Group.objects.get_or_create(name="Empleado")
        empleado.groups.add(grupo_empleados)
        administrador.groups.add(grupo_empleados)
        empleado_inactivo = get_user_model().objects.create_user(
            username="empleado-inactivo",
            password="test-password",
            is_active=False,
        )
        empleado_inactivo.groups.add(grupo_empleados)
        formulario = MovimientoForm()

        self.assertIn(empleado, formulario.fields["empleado"].queryset)
        self.assertNotIn(empleado_inactivo, formulario.fields["empleado"].queryset)
        self.assertNotIn(administrador, formulario.fields["empleado"].queryset)

    def test_pago_empleado_rechaza_usuario_fuera_del_grupo_empleado(self):
        usuario = get_user_model().objects.create_user(
            username="usuario-sin-grupo-empleado",
            password="test-password",
        )
        usuario.groups.clear()
        movimiento = MovimientoFinanciero(
            tipo="EGRESO",
            monto=Decimal("75"),
            metodo_pago="EFECTIVO_USD",
            categoria_egreso="PAGO_EMPLEADOS",
            empleado=usuario,
        )

        with self.assertRaises(ValidationError) as error:
            movimiento.full_clean()

        self.assertIn("empleado", error.exception.message_dict)

    def test_pantalla_financiera_propia_incluye_selector_de_empleado(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-movimientos",
            email="movimientos@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("movement_create"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="empleado"')

    def test_egreso_sin_categoria_no_es_valido(self):
        formulario = MovimientoForm(data={
            "tipo": "EGRESO",
            "monto": "25",
            "metodo_pago": "EFECTIVO_USD",
            "plataforma": "",
            "tipo_cuenta": "USD",
            "descripcion": "Compra de tinta",
            "categoria_egreso": "",
            "fecha_transaccion": "2026-11-09",
            "tipo_ingreso": "",
            "categoria_financiera": "",
            "empleado": "",
            "trabajo": "",
        })

        self.assertFalse(formulario.is_valid())
        self.assertIn("categoria_egreso", formulario.errors)

    def test_ingreso_no_guarda_categoria_egreso(self):
        formulario = MovimientoForm(data={
            "tipo": "INGRESO",
            "monto": "25",
            "metodo_pago": "EFECTIVO_USD",
            "plataforma": "",
            "tipo_cuenta": "USD",
            "descripcion": "Pago de trabajo",
            "trabajo": str(self.trabajo.pk),
            "categoria_egreso": "COMPRA_MATERIAL",
            "tipo_ingreso": "ABONO_CLIENTES",
            "fecha_transaccion": "2026-11-09",
            "categoria_financiera": "",
            "empleado": "",
        })

        self.assertTrue(formulario.is_valid(), formulario.errors)
        movimiento = formulario.save()
        self.assertEqual(movimiento.trabajo, self.trabajo)
        self.assertEqual(movimiento.categoria_egreso, "")


class CalendarioTrabajoTests(TestCase):
    def setUp(self):
        self.trabajo = Trabajo.objects.create(
            cliente="Cliente calendario",
            descripcion="Proyecto de varios días",
            monto_total=Decimal("100"),
        )
        self.area = AreaInsumo.objects.create(nombre="Área calendario")
        self.insumo = Insumo.objects.create(
            nombre="Material calendario",
            area=self.area,
            cantidad_disponible=Decimal("50"),
            unidad_medida="metros",
        )
        self.fecha = date(2026, 11, 5)

    def test_jornadas_permiten_repetir_trabajo_en_dias_distintos(self):
        primera = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)
        segunda = TrabajoDia.objects.create(
            trabajo=self.trabajo,
            fecha=date(2026, 11, 6),
        )

        self.assertNotEqual(primera.pk, segunda.pk)
        self.assertEqual(self.trabajo.jornadas.count(), 2)

    @patch("gestion_publicidad.models.timezone.now")
    def test_tarea_registra_y_conserva_fecha_de_finalizacion(self, ahora):
        ahora.return_value = timezone.make_aware(datetime(2026, 11, 5, 16, 30))
        jornada = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)
        tarea = TareaTrabajoDia.objects.create(
            jornada=jornada,
            descripcion="Preparar materiales",
            completada=True,
        )
        fecha_registro = tarea.completada_en

        ahora.return_value = timezone.make_aware(datetime(2026, 11, 6, 10, 0))
        tarea.descripcion = "Preparar materiales y equipo"
        tarea.save()
        tarea.refresh_from_db()
        self.assertEqual(tarea.completada_en, fecha_registro)

        tarea.completada = False
        tarea.save()
        self.assertIsNone(tarea.completada_en)

    def test_consumo_de_material_diario_actualiza_y_restituye_stock(self):
        jornada = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)
        material = TrabajoInsumo.objects.create(
            jornada=jornada,
            area=self.area,
            insumo=self.insumo,
            cantidad_utilizada=Decimal("8"),
        )
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.cantidad_disponible, Decimal("42"))

        material.cantidad_utilizada = Decimal("10")
        material.save()
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.cantidad_disponible, Decimal("40"))

        material.delete()
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.cantidad_disponible, Decimal("50"))

    def test_consumo_de_variante_actualiza_solo_su_stock(self):
        self.insumo.tiene_tipos = True
        self.insumo.save()
        tipo = TipoInsumo.objects.create(
            insumo=self.insumo,
            nombre="Material variante",
            unidad_medida="metros",
            cantidad_disponible=Decimal("12"),
        )
        jornada = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)

        TrabajoInsumo.objects.create(
            jornada=jornada,
            area=self.area,
            insumo=self.insumo,
            tipo_insumo=tipo,
            cantidad_utilizada=Decimal("3"),
        )

        tipo.refresh_from_db()
        self.insumo.refresh_from_db()
        self.assertEqual(tipo.cantidad_disponible, Decimal("9"))
        self.assertEqual(self.insumo.cantidad_disponible, Decimal("50"))

    def test_formulario_valida_area_tipo_y_stock(self):
        jornada = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)
        otro_area = AreaInsumo.objects.create(nombre="Otra área")
        datos = {
            "materiales_utilizados-0-area": str(otro_area.pk),
            "materiales_utilizados-0-insumo": str(self.insumo.pk),
            "materiales_utilizados-0-tipo_insumo": "",
            "materiales_utilizados-0-cantidad_utilizada": "5",
        }
        form = TrabajoInsumoForm(
            data=datos,
            instance=TrabajoInsumo(jornada=jornada),
            prefix="materiales_utilizados-0",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("insumo", form.errors)

    def test_dashboard_muestra_jornadas_y_fechas_limite(self):
        self.trabajo.fecha_limite = self.fecha
        self.trabajo.save()
        jornada = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)
        TareaTrabajoDia.objects.create(
            jornada=jornada,
            descripcion="Cortar material",
        )
        TrabajoInsumo.objects.create(
            jornada=jornada,
            area=self.area,
            insumo=self.insumo,
            cantidad_utilizada=Decimal("4"),
        )
        otro_trabajo = Trabajo.objects.create(
            cliente="Otro cliente del día",
            descripcion="Otro trabajo",
            monto_total=Decimal("50"),
        )
        TrabajoDia.objects.create(trabajo=otro_trabajo, fecha=self.fecha)

        usuario = get_user_model().objects.create_superuser(
            username="calendar-admin",
            email="calendar@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)
        respuesta = self.client.get(
            reverse("dashboard"),
            {"calendar_month": "2026-11", "section": "jornadas"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cliente calendario")
        self.assertContains(respuesta, "Otro cliente del día")
        self.assertContains(respuesta, "Entrega")
        self.assertContains(respuesta, "Cortar material")
        self.assertContains(respuesta, "4.00 metros")

    def test_formulario_propio_prefija_fecha_al_agendar_jornada(self):
        usuario = get_user_model().objects.create_superuser(
            username="calendar-admin",
            email="calendar@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)
        respuesta = self.client.get(
            reverse("journey_create"),
            {"fecha": "2026-11-05"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'value="2026-11-05"')

    def test_formulario_propio_de_jornada_oculta_campos_internos(self):
        jornada = TrabajoDia.objects.create(trabajo=self.trabajo, fecha=self.fecha)
        TareaTrabajoDia.objects.create(
            jornada=jornada,
            descripcion="Preparar materiales",
        )
        usuario = get_user_model().objects.create_superuser(
            username="calendar-admin",
            email="calendar@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("journey_edit", args=[jornada.pk])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Terminada el")
        self.assertNotContains(respuesta, "completada_en")
        self.assertContains(respuesta, "tareas-0-DELETE")
        self.assertContains(respuesta, "Eliminar jornada")
        self.assertNotContains(respuesta, "materiales-0-DELETE")

    def test_pantalla_propia_guarda_jornada_tarea_y_material(self):
        usuario = get_user_model().objects.create_superuser(
            username="calendar-admin",
            email="calendar@example.com",
            password="test-password",
        )
        self.client.force_login(usuario)
        respuesta = self.client.post(
            reverse("journey_create"),
            {
                "trabajo": self.trabajo.pk,
                "fecha": self.fecha.isoformat(),
                "notas": "Jornada de preparación",
                "tareas-TOTAL_FORMS": "1",
                "tareas-INITIAL_FORMS": "0",
                "tareas-MIN_NUM_FORMS": "0",
                "tareas-MAX_NUM_FORMS": "1000",
                "tareas-0-descripcion": "Preparar el área",
                "tareas-0-completada": "on",
                "materiales-TOTAL_FORMS": "1",
                "materiales-INITIAL_FORMS": "0",
                "materiales-MIN_NUM_FORMS": "0",
                "materiales-MAX_NUM_FORMS": "1000",
                "materiales-0-area": self.area.pk,
                "materiales-0-insumo": self.insumo.pk,
                "materiales-0-tipo_insumo": "",
                "materiales-0-cantidad_utilizada": "6",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        jornada = TrabajoDia.objects.get(trabajo=self.trabajo, fecha=self.fecha)
        self.assertEqual(jornada.tareas.count(), 1)
        self.assertIsNotNone(jornada.tareas.get().completada_en)
        self.assertEqual(jornada.materiales_utilizados.count(), 1)
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.cantidad_disponible, Decimal("44"))
