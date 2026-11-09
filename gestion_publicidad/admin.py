from datetime import date

from django import forms
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db import transaction
from django.forms import formset_factory
from django.http import HttpResponseForbidden
from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .admin_mixins import DashboardReturnMixin
from .calendar_utils import build_work_calendar
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


class GestionAdminSite(AdminSite):
    """Sitio de administración personalizado para Macaira Studio."""

    site_header = "Macaira Studio"
    site_title = "Macaira Studio"
    index_template = "admin/macaira_index.html"

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        orden_gestion = {
            "Trabajo": 0,
            "TrabajoPorCobrar": 1,
            "Insumo": 2,
            "TipoInsumo": 3,
            "AreaInsumo": 4,
        }
        finance_app = next(
            (app for app in app_list if app["app_label"] == "Gestion_Finanzas"),
            None,
        )
        finance_movement = None
        for app in app_list:
            if app["app_label"] == "gestion_publicidad":
                finance_movement = next(
                    (
                        model
                        for model in app["models"]
                        if model["object_name"] == "MovimientoFinanciero"
                    ),
                    None,
                )
                app["models"] = [
                    model for model in app["models"]
                    if model["object_name"] != "MovimientoFinanciero"
                ]
                app["models"].sort(
                    key=lambda model: orden_gestion.get(model["object_name"], len(orden_gestion))
                )
        if app_label == "Gestion_Finanzas":
            publicity_apps = super().get_app_list(request, "gestion_publicidad")
            finance_movement = next(
                (
                    model
                    for app in publicity_apps
                    for model in app["models"]
                    if model["object_name"] == "MovimientoFinanciero"
                ),
                None,
            )
        if finance_app is not None:
            if finance_movement is not None:
                finance_app["models"].append(finance_movement)
            finance_app["models"].sort(
                key=lambda model: (
                    0 if model["object_name"] == "MovimientoFinanciero" else 1
                )
            )
        return app_list


gestion_admin_site = GestionAdminSite(name="admin")


def mostrar_control_stock(estado):
    colores = {
        "Agotado": "#721c24",
        "Crítico": "#dc3545",
        "Poco stock": "#ffc107",
        "Óptimo": "#198754",
    }
    color_texto = "#212529" if estado == "Poco stock" else "#fff"
    return format_html(
        '<span style="background-color: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
        colores[estado],
        color_texto,
        estado,
    )


def mostrar_control_entrega(estado):
    colores = {
        "Entregado": "#198754",
        "Sin fecha": "#6c757d",
        "A tiempo": "#198754",
        "Poco tiempo": "#ffc107",
        "Fecha límite": "#dc3545",
        "Expirado": "#721c24",
    }
    color_texto = "#212529" if estado == "Poco tiempo" else "#fff"
    return format_html(
        '<span style="background-color: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
        colores[estado],
        color_texto,
        estado,
    )


class ControlNumericoAdminMixin:
    class Media:
        js = ('gestion_publicidad/js/gestion_pagos.js',)


class ReabastecerStockForm(forms.Form):
    area = forms.ModelChoiceField(
        queryset=AreaInsumo.objects.order_by('nombre'),
        label="Área",
    )
    insumo = forms.ModelChoiceField(
        queryset=Insumo.objects.none(),
        label="Insumo",
    )
    tipo_insumo = forms.ModelChoiceField(
        queryset=TipoInsumo.objects.none(),
        required=False,
        label="Tipo de insumo",
        help_text="Selecciona una variante si el insumo maneja tipos.",
    )
    cantidad = forms.DecimalField(
        min_value=0.01,
        max_digits=10,
        decimal_places=2,
        label="Cantidad a reabastecer",
        help_text="Esta cantidad se sumará al stock actual.",
    )

    class Media:
        js = ('gestion_publicidad/js/reabastecer_stock_v2.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        area_id = self.data.get(self.add_prefix('area')) if self.is_bound else None
        insumo_id = self.data.get(self.add_prefix('insumo')) if self.is_bound else None
        if area_id:
            self.fields['insumo'].queryset = Insumo.objects.filter(area_id=area_id).order_by('nombre')
        if insumo_id:
            self.fields['tipo_insumo'].queryset = TipoInsumo.objects.filter(
                insumo_id=insumo_id,
            ).order_by('nombre')

    def clean(self):
        cleaned_data = super().clean()
        area = cleaned_data.get('area')
        insumo = cleaned_data.get('insumo')
        tipo_insumo = cleaned_data.get('tipo_insumo')

        if area and insumo and insumo.area_id != area.pk:
            self.add_error('insumo', "Selecciona un insumo del área elegida.")

        if insumo:
            tiene_tipos = insumo.tiene_tipos or insumo.tipos.exists()
            if tiene_tipos and not tipo_insumo:
                mensaje = (
                    "Registra primero un tipo de insumo."
                    if not insumo.tipos.exists()
                    else "Selecciona el tipo de insumo que deseas reabastecer."
                )
                self.add_error('tipo_insumo', mensaje)
            elif tipo_insumo and tipo_insumo.insumo_id != insumo.pk:
                self.add_error('tipo_insumo', "El tipo seleccionado no pertenece al insumo.")

        return cleaned_data

    def reabastecer(self):
        insumo = self.cleaned_data['insumo']
        tipo_insumo = self.cleaned_data['tipo_insumo']
        objetivo = tipo_insumo or insumo
        modelo = TipoInsumo if tipo_insumo else Insumo

        with transaction.atomic():
            objetivo = modelo.objects.select_for_update().get(pk=objetivo.pk)
            objetivo.cantidad_disponible += self.cleaned_data['cantidad']
            objetivo.save(update_fields=('cantidad_disponible',))

        return objetivo


class ReabastecerStockFormSet(forms.BaseFormSet):
    def reabastecer(self):
        objetivos = []
        with transaction.atomic():
            for form in self.forms:
                if form.cleaned_data and form.has_changed():
                    objetivos.append(form.reabastecer())
        return objetivos


ReabastecerStockFormSetFactory = formset_factory(
    ReabastecerStockForm,
    formset=ReabastecerStockFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)


class TrabajoInsumoForm(forms.ModelForm):
    """
    Formulario para el inline de insumos de un Trabajo.

    Organización del flujo de consumo:
    1. Área (obligatoria) -> 2. Insumo (obligatorio, filtrado por área) -> 3. Tipo de Insumo (solo si el insumo tiene tipos) -> 4. Cantidad utilizada.
    """
    class Meta:
        model = TrabajoInsumo
        fields = ('area', 'insumo', 'tipo_insumo', 'cantidad_utilizada')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['area'].required = True
        self.fields['insumo'].required = True

        area_id = (
            self.data.get(self.add_prefix('area'))
            if self.is_bound
            else self.initial.get('area', self.instance.area_id)
        )
        insumo_id = (
            self.data.get(self.add_prefix('insumo'))
            if self.is_bound
            else self.initial.get('insumo', self.instance.insumo_id)
        )
        self.fields['insumo'].queryset = (
            Insumo.objects.filter(area_id=area_id) if area_id else Insumo.objects.none()
        )
        self.fields['tipo_insumo'].queryset = (
            TipoInsumo.objects.filter(insumo_id=insumo_id) if insumo_id else TipoInsumo.objects.none()
        )

    def clean(self):
        cleaned_data = super().clean()
        area = cleaned_data.get('area')
        insumo = cleaned_data.get('insumo')
        tipo_insumo = cleaned_data.get('tipo_insumo')

        if area and insumo and insumo.area_id != area.id:
            self.add_error('insumo', 'Selecciona un insumo que pertenezca al área elegida.')

        # El tipo de insumo debe pertenecer al insumo seleccionado
        if insumo and tipo_insumo and tipo_insumo.insumo_id != insumo.id:
            self.add_error(
                'tipo_insumo',
                'El tipo de insumo seleccionado no corresponde al insumo elegido.'
            )

        # Si el insumo elegido tiene tipos registrados, se debe seleccionar uno de ellos
        if insumo and not tipo_insumo and (insumo.tiene_tipos or insumo.tipos.exists()):
            self.add_error('tipo_insumo', 'Selecciona un tipo de insumo para el insumo elegido.')

        cantidad = cleaned_data.get('cantidad_utilizada')
        stock = tipo_insumo or insumo
        if stock and cantidad is not None:
            disponible = stock.cantidad_disponible
            if self.instance.pk:
                stock_anterior = self.instance.tipo_insumo or self.instance.insumo
                if (
                    stock_anterior
                    and type(stock_anterior) is type(stock)
                    and stock_anterior.pk == stock.pk
                ):
                    disponible += self.instance.cantidad_utilizada

            if cantidad > disponible:
                self.add_error(
                    'cantidad_utilizada',
                    f'Stock insuficiente de {stock}. Disponible: {disponible}.',
                )

        return cleaned_data


class TrabajoInsumoInline(ControlNumericoAdminMixin, admin.TabularInline):
    model = TrabajoInsumo
    form = TrabajoInsumoForm
    fields = ('area', 'insumo', 'tipo_insumo', 'cantidad_utilizada')
    extra = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'area':
            kwargs['queryset'] = AreaInsumo.objects.order_by('nombre')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_delete_permission(self, request, obj=None):
        # Solo administradores o superusuarios pueden desvocar insumos de un trabajo
        if request.user.is_superuser or request.user.groups.filter(name='Administrador').exists():
            return True
        return False


class AreaInsumoAdmin(DashboardReturnMixin, admin.ModelAdmin):
    change_list_template = "admin/gestion_publicidad/insumo/related_change_list.html"
    change_form_template = "admin/gestion_publicidad/insumo/related_change_form.html"
    search_fields = ('nombre',)
    verbose_name = "Área de Insumo"
    verbose_name_plural = "Áreas de Insumos"


class TipoInsumoInline(ControlNumericoAdminMixin, admin.TabularInline):
    model = TipoInsumo
    extra = 1
    fields = ('nombre', 'unidad_medida', 'cantidad_disponible', 'stock_minimo', 'control_stock')
    readonly_fields = ('control_stock',)

    def control_stock(self, obj):
        if obj is None:
            return "—"
        return mostrar_control_stock(obj.estado_stock)
    control_stock.short_description = 'Control de stock'


class InsumoAdmin(DashboardReturnMixin, ControlNumericoAdminMixin, admin.ModelAdmin):
    change_list_template = 'admin/gestion_publicidad/insumo/change_list.html'
    list_display = ('nombre', 'area', 'control_stock')
    list_filter = ('area',)
    search_fields = ('nombre', 'area__nombre')
    inlines = [TipoInsumoInline]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        no_area = AreaInsumo.objects.filter(nombre="Sin área").first()
        if no_area:
            initial.setdefault('area', no_area.pk)
        return initial

    def control_stock(self, obj):
        if obj.tiene_tipos or obj.tipos.exists():
            return "—"
        return mostrar_control_stock(obj.estado_stock)
    control_stock.short_description = 'Control de stock'

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if obj and (obj.tiene_tipos or obj.tipos.exists()):
            fields = [
                field for field in fields
                if field not in ('cantidad_disponible', 'stock_minimo', 'unidad_medida')
            ]
        return fields

    def get_inlines(self, request, obj=None):
        # El inline de tipos solo se muestra si el insumo tiene habilitados los tipos.
        if obj is not None:
            return [TipoInsumoInline] if (obj.tiene_tipos or obj.tipos.exists()) else []
        # En creación: solo si el usuario activó la opción "Tiene Tipos de Insumo"
        if request.method == "POST" and request.POST.get("tiene_tipos"):
            return [TipoInsumoInline]
        return []

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'reabastecer-stock/',
                self.admin_site.admin_view(self.reabastecer_stock_view),
                name='gestion_publicidad_insumo_reabastecer_stock',
            ),
        ]
        return custom_urls + urls

    def reabastecer_stock_view(self, request):
        if not self.has_change_permission(request):
            return HttpResponseForbidden()

        if request.method == "POST":
            form = ReabastecerStockFormSetFactory(request.POST)
            if form.is_valid():
                objetivos = form.reabastecer()
                resumen = "; ".join(
                    f"{objetivo}: {objetivo.cantidad_disponible}"
                    for objetivo in objetivos
                )
                messages.success(
                    request,
                    f"Stock actualizado para {len(objetivos)} insumo(s). Nuevos totales: {resumen}.",
                )
                dashboard_response = self._dashboard_redirect(request)
                if dashboard_response:
                    return dashboard_response
                return redirect(reverse('admin:gestion_publicidad_insumo_changelist'))
        else:
            form = ReabastecerStockFormSetFactory()

        context = {
            **self.admin_site.each_context(request),
            'title': "Reabastecer stock",
            'opts': self.model._meta,
            'form': form,
            'media': form.media,
        }
        return TemplateResponse(
            request,
            'admin/gestion_publicidad/reabastecer_stock.html',
            context,
        )


class TipoInsumoAdmin(DashboardReturnMixin, ControlNumericoAdminMixin, admin.ModelAdmin):
    change_list_template = "admin/gestion_publicidad/insumo/related_change_list.html"
    change_form_template = "admin/gestion_publicidad/insumo/related_change_form.html"
    list_display = ('nombre', 'insumo', 'cantidad_disponible', 'stock_minimo', 'unidad_medida', 'control_stock')
    search_fields = ('nombre', 'insumo__nombre', 'insumo__area__nombre')
    list_filter = ('unidad_medida', 'insumo__area', 'insumo')

    def control_stock(self, obj):
        return mostrar_control_stock(obj.estado_stock)
    control_stock.short_description = 'Control de stock'

    def get_readonly_fields(self, request, obj=None):
        # Si no es superusuario ni pertenece al grupo 'Administrador', protege ciertos campos
        if not (request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()):
            return ('nombre', 'insumo', 'unidad_medida', 'stock_minimo')
        return super().get_readonly_fields(request, obj=obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()


class TareaTrabajoDiaInline(admin.TabularInline):
    model = TareaTrabajoDia
    extra = 1
    fields = ("descripcion", "completada")
    can_delete = False


class TrabajoInsumoDiaInline(ControlNumericoAdminMixin, admin.TabularInline):
    model = TrabajoInsumo
    form = TrabajoInsumoForm
    extra = 1
    fields = ("area", "insumo", "tipo_insumo", "cantidad_utilizada")
    can_delete = False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "area":
            kwargs["queryset"] = AreaInsumo.objects.order_by("nombre")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TrabajoDiaAdmin(DashboardReturnMixin, admin.ModelAdmin):
    change_form_template = "admin/gestion_publicidad/trabajo/dia_change_form.html"
    list_display = ("fecha", "trabajo", "resumen_tareas")
    list_filter = ("fecha",)
    search_fields = ("trabajo__cliente", "trabajo__descripcion", "notas", "tareas__descripcion")
    inlines = (TareaTrabajoDiaInline, TrabajoInsumoDiaInline)
    fields = ("trabajo", "fecha", "notas")

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm("gestion_publicidad.view_trabajo")
            or request.user.has_perm("gestion_publicidad.change_trabajo")
        )

    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "gestion_publicidad.change_trabajo"
        )

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm(
            "gestion_publicidad.change_trabajo"
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        fecha = request.GET.get("fecha")
        trabajo = request.GET.get("trabajo")
        if fecha:
            initial["fecha"] = fecha
        if trabajo:
            initial["trabajo"] = trabajo
        return initial

    @admin.display(description="Tareas terminadas")
    def resumen_tareas(self, obj):
        total = obj.tareas.count()
        terminadas = obj.tareas.filter(completada=True).count()
        return f"{terminadas}/{total}"


class TrabajoAdmin(DashboardReturnMixin, admin.ModelAdmin):
    change_list_template = "admin/gestion_publicidad/trabajo/change_list.html"
    change_form_template = "admin/gestion_publicidad/trabajo/change_form.html"
    list_display = (
        'id',
        'cliente',
        'monto_total',
        'saldo_pendiente',
        'estado',
        'fecha_limite',
        'indicador_entrega',
        'fecha_creacion',
    )
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('cliente', 'descripcion')
    inlines = [TrabajoInsumoInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "calendario/",
                self.admin_site.admin_view(self.calendario_view),
                name="gestion_publicidad_trabajo_calendario",
            ),
        ]
        return custom_urls + urls

    def calendario_view(self, request):
        if not self.has_view_permission(request):
            return HttpResponseForbidden()

        hoy = timezone.localdate()
        try:
            year, month = map(int, request.GET.get("mes", "").split("-"))
            date(year, month, 1)
        except (ValueError, TypeError, OverflowError):
            year, month = hoy.year, hoy.month
        if year < 1900 or year > 9998:
            year, month = hoy.year, hoy.month

        calendar_data = build_work_calendar(year, month)
        context = {
            **self.admin_site.each_context(request),
            "title": "Calendario de trabajos",
            **calendar_data,
            "hoy": hoy,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/gestion_publicidad/trabajo/calendario.html",
            context,
        )

    @admin.display(description="Control de entrega")
    def indicador_entrega(self, obj):
        return mostrar_control_entrega(obj.estado_entrega)

    def get_readonly_fields(self, request, obj=None):
        # Si el usuario NO es superusuario ni administrador (es empleado)
        if not (request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()):
            if obj:
                # Si está EDITANDO un trabajo existente: solo puede cambiar el estado
                return ('cliente', 'descripcion', 'monto_total', 'saldo_pendiente')
            else:
                # Si está CREANDO un trabajo nuevo: el saldo_pendiente se oculta/bloquea porque el modelo lo llena solo
                return ('saldo_pendiente',)

        return super().get_readonly_fields(request, obj=obj)

    # Script para ocultar/mostrar el campo de monto de abono dinámicamente
    class Media:
        js = ('gestion_publicidad/js/gestion_pagos.js',)


class TrabajoPorCobrarAdmin(TrabajoAdmin):
    change_list_template = "admin/gestion_publicidad/trabajo/por_cobrar_change_list.html"
    list_display = (
        'id',
        'cliente',
        'monto_total',
        'saldo_pendiente',
        'fecha_limite',
        'indicador_entrega',
        'fecha_creacion',
    )
    list_filter = ('fecha_creacion',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            estado='FINALIZADO',
            saldo_pendiente__gt=0,
        )

    def has_module_permission(self, request):
        return (
            request.user.is_superuser
            or request.user.has_perm('gestion_publicidad.view_trabajo')
            or request.user.has_perm('gestion_publicidad.change_trabajo')
        )

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm('gestion_publicidad.view_trabajo')
            or request.user.has_perm('gestion_publicidad.change_trabajo')
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.has_perm('gestion_publicidad.change_trabajo')
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MovimientoFinancieroForm(forms.ModelForm):
    empleado = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        label="Empleado",
    )

    class Meta:
        model = MovimientoFinanciero
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        grupo_empleados = Group.objects.filter(name="Empleado").first()
        if grupo_empleados:
            self.fields["empleado"].queryset = get_user_model().objects.filter(
                groups=grupo_empleados,
                is_active=True,
                is_superuser=False,
            ).order_by("first_name", "last_name", "username")
        else:
            self.fields["empleado"].queryset = get_user_model().objects.none()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("tipo") == "EGRESO":
            if cleaned_data.get("categoria_egreso") != "REEMBOLSO_CLIENTE":
                cleaned_data["trabajo"] = None
            cleaned_data["tipo_ingreso"] = None
            if not cleaned_data.get("categoria_egreso"):
                self.add_error(
                    "categoria_egreso",
                    "Selecciona la categoría del egreso.",
                )
            elif cleaned_data.get("categoria_egreso") == "PAGO_EMPLEADOS":
                if not cleaned_data.get("empleado"):
                    self.add_error("empleado", "Selecciona el empleado al que se realizará el pago.")
            else:
                cleaned_data["empleado"] = None
        else:
            cleaned_data["categoria_egreso"] = ""
            cleaned_data["empleado"] = None
        return cleaned_data


class MovimientoFinancieroAdmin(DashboardReturnMixin, admin.ModelAdmin):
    form = MovimientoFinancieroForm
    list_display = (
        'id',
        'tipo',
        'categoria_egreso',
        'empleado',
        'monto',
        'metodo_pago',
        'descripcion',
        'trabajo',
        'fecha',
    )
    list_filter = ('tipo', 'metodo_pago', 'fecha')
    search_fields = ('descripcion', 'trabajo__cliente', 'empleado__username', 'empleado__first_name', 'empleado__last_name')

    class Media:
        js = ('gestion_publicidad/js/gestion_pagos.js',)


gestion_admin_site.register(Trabajo, TrabajoAdmin)
gestion_admin_site.register(TrabajoDia, TrabajoDiaAdmin)
gestion_admin_site.register(TrabajoPorCobrar, TrabajoPorCobrarAdmin)
gestion_admin_site.register(MovimientoFinanciero, MovimientoFinancieroAdmin)
gestion_admin_site.register(Insumo, InsumoAdmin)
gestion_admin_site.register(TipoInsumo, TipoInsumoAdmin)
gestion_admin_site.register(AreaInsumo, AreaInsumoAdmin)

from Gestion_Finanzas.admin import register_finance_models

register_finance_models(gestion_admin_site)
