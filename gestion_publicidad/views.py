from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from itertools import groupby
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import DateField, F, ProtectedError, Q
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from Gestion_Finanzas.models import (
    CategoriaFinanciera,
    DetalleMovimientoFinanciero,
)
from .calendar_utils import build_work_calendar
from .forms import (
    AreaInsumoForm,
    CategoriaFinancieraForm,
    InsumoForm,
    MacairaLoginForm,
    MaterialFormSet,
    MovimientoForm,
    PersonalUserForm,
    ReabastecerInsumoForm,
    TareaFormSet,
    TipoInsumoFormSet,
    TrabajoDiaForm,
    TrabajoForm,
    TrabajoUpdateForm,
)
from .models import (
    AreaInsumo,
    Insumo,
    MovimientoFinanciero,
    TareaTrabajoDia,
    Trabajo,
    TrabajoDia,
    TrabajoPorCobrar,
)

MONTH_NAMES_ES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def _can_access(user, *permissions):
    return user.is_superuser or (
        user.is_authenticated
        and (
            user.groups.filter(name="Administrador").exists()
            or user.is_staff
            and any(user.has_perm(permission) for permission in permissions)
        )
    )


def _can_manage_personal(user):
    return user.is_superuser or (
        user.is_authenticated and user.groups.filter(name="Administrador").exists()
    )


def _managed_user(user_id):
    return get_object_or_404(get_user_model(), pk=user_id, is_superuser=False)


def _has_another_active_administrator(excluded_user_id=None):
    users = get_user_model().objects.filter(is_active=True)
    if excluded_user_id is not None:
        users = users.exclude(pk=excluded_user_id)
    return users.filter(is_superuser=True).exists() or users.filter(
        groups__name="Administrador"
    ).exists()


def _safe_next_url(request):
    destination = request.POST.get("next") or request.GET.get("next", "")
    destination_path = urlsplit(destination).path.rstrip("/") if destination else ""
    if destination and url_has_allowed_host_and_scheme(
        destination,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ) and destination_path != "/admin" and not destination_path.startswith("/admin/"):
        return destination
    return reverse("dashboard")


def _parse_month(value, fallback):
    if not value:
        return fallback.replace(day=1), False
    try:
        parsed = datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError):
        return fallback.replace(day=1), True
    if parsed.year < 1900 or parsed.year > 9998:
        return fallback.replace(day=1), True
    return parsed, False


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request))

    form = MacairaLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        auth_login(request, form.get_user())
        remember_me = request.POST.get("remember_me") == "on"
        request.session.set_expiry(
            settings.SESSION_COOKIE_AGE if remember_me else 0
        )
        return redirect(_safe_next_url(request))

    return render(
        request,
        "gestion_publicidad/login.html",
        {"form": form, "next": request.POST.get("next") or request.GET.get("next", "")},
    )


@require_POST
@never_cache
def logout_view(request):
    auth_logout(request)
    return redirect("login")


def legacy_admin_redirect(request, remaining_path=""):
    return redirect("dashboard")


def _movement_currency(movement):
    if movement.tipo_cuenta:
        return movement.tipo_cuenta
    if movement.metodo_pago == "EFECTIVO_USD":
        return "USD"
    if movement.metodo_pago == "PAGO_MOVIL":
        return "VES"
    return "Moneda no especificada"


def _monthly_finance_data(month_start):
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)

    monthly_movements = list(
        MovimientoFinanciero.objects.select_related(
            "trabajo", "empleado", "detalle_financiero__categoria"
        )
        .annotate(
            fecha_panel=Coalesce(
                F("detalle_financiero__fecha_transaccion"),
                TruncDate("fecha"),
                output_field=DateField(),
            )
        )
        .filter(fecha_panel__gte=month_start, fecha_panel__lt=next_month)
        .order_by("-fecha_panel", "-fecha", "-id")
    )

    totals = defaultdict(lambda: {"ingresos": Decimal("0"), "egresos": Decimal("0")})
    groups_by_date = defaultdict(list)
    counts = {"INGRESO": 0, "EGRESO": 0}
    movement_kinds = {
        "INGRESO": ("INGRESO", "ingresos"),
        "ENTRADA": ("INGRESO", "ingresos"),
        "EGRESO": ("EGRESO", "egresos"),
        "SALIDA": ("EGRESO", "egresos"),
    }
    for movement in monthly_movements:
        currency = _movement_currency(movement)
        movement.moneda_panel = currency
        count_key, kind = movement_kinds[movement.tipo]
        totals[currency][kind] += movement.monto
        counts[count_key] += 1
        groups_by_date[movement.fecha_panel].append(movement)

    currency_totals = [
        {
            "currency": currency,
            "ingresos": values["ingresos"],
            "egresos": values["egresos"],
            "saldo": values["ingresos"] - values["egresos"],
        }
        for currency, values in sorted(totals.items())
    ]
    movements_by_date = [
        {"fecha": transaction_date, "movimientos": day_movements}
        for transaction_date, day_movements in groups_by_date.items()
    ]
    return monthly_movements, movements_by_date, currency_totals, counts


@never_cache
def dashboard(request):
    if not request.user.is_authenticated:
        return render(
            request,
            "gestion_publicidad/login.html",
            {"form": MacairaLoginForm(), "next": request.GET.get("next", "")},
        )

    today = timezone.localdate()
    finance_month, invalid_finance_month = _parse_month(
        request.GET.get("finance_month"), today
    )
    calendar_month, invalid_calendar_month = _parse_month(
        request.GET.get("calendar_month"), today
    )
    if invalid_finance_month or invalid_calendar_month:
        messages.warning(
            request,
            "El mes indicado no es válido. Se muestra el mes actual.",
        )

    can_view_work = _can_access(
        request.user,
        "gestion_publicidad.view_trabajo",
        "gestion_publicidad.change_trabajo",
    )
    can_view_inventory = _can_access(
        request.user,
        "gestion_publicidad.view_insumo",
        "gestion_publicidad.change_insumo",
    )
    can_view_finance = _can_access(
        request.user,
        "gestion_publicidad.view_movimientofinanciero",
        "gestion_publicidad.change_movimientofinanciero",
    )

    trabajos = Trabajo.objects.none()
    jornadas = TrabajoDia.objects.none()
    trabajos_por_cobrar = TrabajoPorCobrar.objects.none()
    insumos = Insumo.objects.none()
    movimientos = MovimientoFinanciero.objects.none()
    monthly_movements = []
    movements_by_date = []
    currency_totals = []
    monthly_movement_counts = {"INGRESO": 0, "EGRESO": 0}
    categorias_financieras = CategoriaFinanciera.objects.none()
    calendar = {}

    if can_view_work:
        trabajos = Trabajo.objects.order_by("-fecha_creacion")
        jornadas = (
            TrabajoDia.objects.select_related("trabajo")
            .prefetch_related("tareas", "materiales_utilizados__insumo", "materiales_utilizados__tipo_insumo")
            .order_by("-fecha", "-id")
        )
        trabajos_por_cobrar = TrabajoPorCobrar.objects.order_by("-fecha_creacion")
        calendar = build_work_calendar(calendar_month.year, calendar_month.month)

    if can_view_inventory:
        insumos = list(
            Insumo.objects.select_related("area")
            .prefetch_related("tipos")
            .order_by("area__nombre", "nombre")
        )

    area_groups = []
    for area_id, grouped_insumos in groupby(
        insumos,
        key=lambda item: (item.area_id, item.area.nombre if item.area_id else "Sin área"),
    ):
        group_area_id, area_name = area_id
        area_groups.append(
            {
                "id": group_area_id if group_area_id is not None else "sin-area",
                "nombre": area_name,
                "insumos": list(grouped_insumos),
            }
        )

    if can_view_finance:
        movimientos = (
            MovimientoFinanciero.objects.select_related(
                "trabajo", "empleado", "detalle_financiero__categoria"
            )
            .order_by("-fecha")
        )
        categorias_financieras = CategoriaFinanciera.objects.filter(activa=True).order_by(
            "nombre"
        )
        (
            monthly_movements,
            movements_by_date,
            currency_totals,
            monthly_movement_counts,
        ) = _monthly_finance_data(finance_month)

    if finance_month.month == 12:
        previous_finance_month = date(finance_month.year, 11, 1)
        next_finance_month = date(finance_month.year + 1, 1, 1)
    else:
        previous_finance_month = date(
            finance_month.year - 1 if finance_month.month == 1 else finance_month.year,
            12 if finance_month.month == 1 else finance_month.month - 1,
            1,
        )
        next_finance_month = date(finance_month.year, finance_month.month + 1, 1)

    insumos_criticos_count = 0
    for insumo in insumos:
        tipos = list(insumo.tipos.all())
        existencias = tipos if (insumo.tiene_tipos or tipos) else [insumo]
        insumos_criticos_count += sum(
            existencia.estado_stock in ("Agotado", "Crítico")
            for existencia in existencias
        )

    context = {
        "can_view_work": can_view_work,
        "can_view_inventory": can_view_inventory,
        "can_view_finance": can_view_finance,
        "can_manage_personal": _can_manage_personal(request.user),
        "can_add_work": _can_access(request.user, "gestion_publicidad.add_trabajo"),
        "can_change_work": _can_access(request.user, "gestion_publicidad.change_trabajo"),
        "can_add_inventory": _can_access(request.user, "gestion_publicidad.add_insumo"),
        "can_change_inventory": _can_access(request.user, "gestion_publicidad.change_insumo"),
        "can_add_movement": _can_access(
            request.user, "gestion_publicidad.add_movimientofinanciero"
        ),
        "can_change_movement": _can_access(
            request.user, "gestion_publicidad.change_movimientofinanciero"
        ),
        "can_manage_finance_categories": _can_access(
            request.user,
            "Gestion_Finanzas.view_categoriafinanciera",
            "Gestion_Finanzas.change_categoriafinanciera",
            "Gestion_Finanzas.add_categoriafinanciera",
        ),
        "can_add_finance_category": _can_access(
            request.user, "Gestion_Finanzas.add_categoriafinanciera"
        ),
        "can_change_finance_category": _can_access(
            request.user, "Gestion_Finanzas.change_categoriafinanciera"
        ),
        "trabajos": trabajos,
        "trabajos_recientes": trabajos[:10],
        "trabajos_count": trabajos.count(),
        "trabajos_pendientes_count": trabajos.filter(estado="PENDIENTE").count(),
        "jornadas": jornadas,
        "jornadas_count": jornadas.count(),
        "trabajos_por_cobrar": trabajos_por_cobrar,
        "trabajos_por_cobrar_count": trabajos_por_cobrar.count(),
        "insumos": insumos,
        "grupos_insumos": area_groups,
        "insumos_count": len(insumos),
        "insumos_criticos_count": insumos_criticos_count,
        "movimientos": movimientos,
        "movimientos_count": movimientos.count(),
        "ingresos_count": movimientos.filter(tipo="INGRESO").count(),
        "egresos_count": movimientos.filter(tipo="EGRESO").count(),
        "movimientos_mes": monthly_movements,
        "movimientos_por_fecha": movements_by_date,
        "totales_por_moneda": currency_totals,
        "conteo_movimientos_mes": monthly_movement_counts,
        "mes_financiero": finance_month,
        "mes_financiero_label": f"{MONTH_NAMES_ES[finance_month.month - 1]} {finance_month.year}",
        "mes_financiero_input": finance_month.strftime("%Y-%m"),
        "mes_financiero_anterior": previous_finance_month.strftime("%Y-%m"),
        "mes_financiero_siguiente": next_finance_month.strftime("%Y-%m"),
        "calendario": calendar,
        "hoy": today,
        "mes_calendario_label": (
            f"{MONTH_NAMES_ES[calendar_month.month - 1]} {calendar_month.year}"
        ),
        "mes_calendario_input": calendar_month.strftime("%Y-%m"),
        "categorias_financieras": categorias_financieras,
    }
    return render(request, "gestion_publicidad/dashboard.html", context)


@login_required(login_url="/login/")
@require_POST
def alternar_tarea(request, tarea_id):
    if not _can_access(
        request.user,
        "gestion_publicidad.change_trabajo",
    ):
        return HttpResponseForbidden()

    tarea = get_object_or_404(
        TareaTrabajoDia.objects.select_related("jornada"),
        pk=tarea_id,
    )
    tarea.completada = not tarea.completada
    tarea.save(update_fields=("completada",))
    messages.success(
        request,
        "Tarea marcada como completada."
        if tarea.completada
        else "Tarea marcada como pendiente.",
    )
    destination = request.POST.get("next")
    if destination and url_has_allowed_host_and_scheme(
        destination,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destination)
    return redirect(f"{reverse('dashboard')}#jornadas")


@never_cache
@login_required(login_url="/login/")
@require_GET
def insumos_por_area(request):
    """
    Endpoint JSON para poblar los selects dependientes del área -> insumo -> tipo
    de los formularios propios de inventario y jornadas.

    Query params:
        area (opcional): id del área. Si se envía, se devuelven solo los insumos de esa área.

    Devuelve:
        {
            "insumos": [
                {
                    "id": 2,
                    "nombre": "Vinil",
                    "area": 2,
                    "tipos": [
                        {
                            "id": 1,
                            "nombre": "Vinilo opaco",
                            "unidad_medida": "Metros",
                        }
                    ],
                }
            ]
        }
    """
    if not _has_inventory_access(request.user, "view") and not _has_inventory_access(
        request.user, "change"
    ):
        return HttpResponseForbidden()

    area_id = request.GET.get('area')
    insumos = Insumo.objects.select_related('area').prefetch_related('tipos').order_by('nombre')

    if area_id:
        insumos = insumos.filter(area_id=area_id)

    data = []
    for insumo in insumos:
        tipos = list(insumo.tipos.all())
        data.append({
            'id': insumo.id,
            'nombre': insumo.nombre,
            'area': insumo.area_id,
            'tiene_tipos': insumo.tiene_tipos or bool(tipos),
            'tipos': [
                {
                    'id': tipo.id,
                    'nombre': tipo.nombre,
                    'unidad_medida': tipo.unidad_medida,
                }
                for tipo in tipos
            ],
        })

    return JsonResponse({'insumos': data})


def _app_context(request, active_module, **extra):
    user = request.user
    context = {
        "active_module": active_module,
        "can_view_work": _can_access(
            user, "gestion_publicidad.view_trabajo", "gestion_publicidad.change_trabajo"
        ),
        "can_view_inventory": _can_access(
            user, "gestion_publicidad.view_insumo", "gestion_publicidad.change_insumo"
        ),
        "can_view_finance": _can_access(
            user,
            "gestion_publicidad.view_movimientofinanciero",
            "gestion_publicidad.change_movimientofinanciero",
        ),
        "can_manage_personal": _can_manage_personal(user),
        "can_add_work": _can_access(user, "gestion_publicidad.add_trabajo"),
        "can_change_work": _can_access(user, "gestion_publicidad.change_trabajo"),
        "can_delete_work": _can_access(user, "gestion_publicidad.delete_trabajo"),
        "can_add_inventory": _can_access(user, "gestion_publicidad.add_insumo"),
        "can_change_inventory": _can_access(user, "gestion_publicidad.change_insumo"),
        "can_delete_inventory": _can_access(user, "gestion_publicidad.delete_insumo"),
        "can_add_movement": _can_access(
            user, "gestion_publicidad.add_movimientofinanciero"
        ),
        "can_change_movement": _can_access(
            user, "gestion_publicidad.change_movimientofinanciero"
        ),
        "can_delete_movement": _can_access(
            user, "gestion_publicidad.delete_movimientofinanciero"
        ),
    }
    context.update(extra)
    return context


def _has_work_access(user, permission):
    return _can_access(user, f"gestion_publicidad.{permission}_trabajo")


def _has_inventory_access(user, permission):
    return _can_access(user, f"gestion_publicidad.{permission}_insumo")


def _has_movement_access(user, permission):
    return _can_access(user, f"gestion_publicidad.{permission}_movimientofinanciero")


def _has_category_access(user, permission):
    return _can_access(user, f"Gestion_Finanzas.{permission}_categoriafinanciera")


def _forbidden():
    return HttpResponseForbidden("No tienes permiso para realizar esta acción.")


@login_required(login_url="/login/")
def work_list(request):
    if not _has_work_access(request.user, "view") and not _has_work_access(request.user, "change"):
        return _forbidden()
    works = Trabajo.objects.order_by("-fecha_creacion")
    query = request.GET.get("q", "").strip()
    state = request.GET.get("estado", "").strip()
    if query:
        search_filter = Q(cliente__icontains=query) | Q(descripcion__icontains=query)
        if query.isdecimal():
            search_filter |= Q(pk=int(query))
        works = works.filter(search_filter)
    if state in dict(Trabajo._meta.get_field("estado").choices):
        works = works.filter(estado=state)
    context = _app_context(
        request,
        "trabajos",
        page_title="Trabajos",
        page_description="Consulta y administra los trabajos y sus fechas de entrega.",
        trabajos=works,
        query=query,
        selected_state=state,
        state_choices=Trabajo._meta.get_field("estado").choices,
    )
    return render(request, "gestion_publicidad/work_list.html", context)


@login_required(login_url="/login/")
def work_detail(request, trabajo_id):
    if not _has_work_access(request.user, "view") and not _has_work_access(request.user, "change"):
        return _forbidden()
    work = get_object_or_404(
        Trabajo.objects.prefetch_related(
            "jornadas__tareas",
            "jornadas__materiales_utilizados__insumo",
            "jornadas__materiales_utilizados__tipo_insumo",
        ),
        pk=trabajo_id,
    )
    return render(
        request,
        "gestion_publicidad/work_detail.html",
        _app_context(request, "trabajos", trabajo=work, page_title=f"Trabajo #{work.pk}"),
    )


@login_required(login_url="/login/")
def work_create(request):
    if not _has_work_access(request.user, "add"):
        return _forbidden()
    form = TrabajoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            work = form.save()
        messages.success(request, f"El trabajo #{work.pk} se creó correctamente.")
        return redirect("work_detail", trabajo_id=work.pk)
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "trabajos",
            page_title="Nuevo trabajo",
            page_description="Registra un trabajo y, si corresponde, su pago inicial.",
            form=form,
            cancel_url=reverse("work_list"),
            submit_label="Crear trabajo",
        ),
    )


@login_required(login_url="/login/")
def work_edit(request, trabajo_id):
    if not _has_work_access(request.user, "change"):
        return _forbidden()
    work = get_object_or_404(Trabajo, pk=trabajo_id)
    is_admin = request.user.is_superuser or request.user.groups.filter(
        name="Administrador"
    ).exists()
    form_class = TrabajoForm if is_admin else TrabajoUpdateForm
    form = form_class(request.POST or None, instance=work)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"El trabajo #{work.pk} se actualizó correctamente.")
        return redirect("work_detail", trabajo_id=work.pk)
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "trabajos",
            page_title=f"Editar trabajo #{work.pk}",
            page_description="Actualiza los datos operativos y el estado del trabajo.",
            form=form,
            cancel_url=reverse("work_detail", args=(work.pk,)),
            submit_label="Guardar cambios",
        ),
    )


@login_required(login_url="/login/")
def work_delete(request, trabajo_id):
    if not _can_access(request.user, "gestion_publicidad.delete_trabajo"):
        return _forbidden()
    work = get_object_or_404(Trabajo, pk=trabajo_id)
    if request.method == "POST":
        try:
            work.delete()
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar este trabajo porque tiene jornadas o insumos asociados.",
            )
            return redirect("work_detail", trabajo_id=work.pk)
        messages.success(request, "El trabajo se eliminó correctamente.")
        return redirect("work_list")
    return render(
        request,
        "gestion_publicidad/confirm_delete.html",
        _app_context(
            request,
            "trabajos",
            page_title=f"Eliminar trabajo #{work.pk}",
            object_label=str(work),
            cancel_url=reverse("work_detail", args=(work.pk,)),
            warning="La eliminación no se puede deshacer.",
        ),
    )


@login_required(login_url="/login/")
def journey_list(request):
    if not _has_work_access(request.user, "view") and not _has_work_access(request.user, "change"):
        return _forbidden()
    journeys = (
        TrabajoDia.objects.select_related("trabajo")
        .prefetch_related("tareas", "materiales_utilizados__insumo", "materiales_utilizados__tipo_insumo")
        .order_by("-fecha", "-id")
    )
    query = request.GET.get("q", "").strip()
    if query:
        journeys = journeys.filter(
            Q(trabajo__cliente__icontains=query)
            | Q(trabajo__descripcion__icontains=query)
            | Q(notas__icontains=query)
            | Q(tareas__descripcion__icontains=query)
        ).distinct()
    return render(
        request,
        "gestion_publicidad/journey_list.html",
        _app_context(
            request,
            "jornadas",
            page_title="Jornadas y tareas",
            page_description="Planifica jornadas, tareas e insumos utilizados.",
            jornadas=journeys,
            query=query,
        ),
    )


@login_required(login_url="/login/")
def journey_create(request):
    if not _has_work_access(request.user, "change"):
        return _forbidden()
    initial = {}
    if request.GET.get("fecha"):
        initial["fecha"] = request.GET["fecha"]
    if request.GET.get("trabajo"):
        initial["trabajo"] = request.GET["trabajo"]
    form = TrabajoDiaForm(request.POST or None, initial=initial if request.method != "POST" else None)
    task_formset = TareaFormSet(request.POST or None, prefix="tareas")
    material_formset = MaterialFormSet(request.POST or None, prefix="materiales")
    if (
        request.method == "POST"
        and form.is_valid()
        and task_formset.is_valid()
        and material_formset.is_valid()
    ):
        try:
            with transaction.atomic():
                journey = form.save()
                task_formset.instance = journey
                material_formset.instance = journey
                task_formset.save()
                material_formset.save()
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "La jornada se creó correctamente.")
            return redirect("journey_list")
    return _journey_form_response(
        request, form, task_formset, material_formset, "Nueva jornada"
    )


@login_required(login_url="/login/")
def journey_edit(request, jornada_id):
    if not _has_work_access(request.user, "change"):
        return _forbidden()
    journey = get_object_or_404(TrabajoDia, pk=jornada_id)
    form = TrabajoDiaForm(request.POST or None, instance=journey)
    task_formset = TareaFormSet(request.POST or None, instance=journey, prefix="tareas")
    material_formset = MaterialFormSet(
        request.POST or None, instance=journey, prefix="materiales"
    )
    if (
        request.method == "POST"
        and form.is_valid()
        and task_formset.is_valid()
        and material_formset.is_valid()
    ):
        try:
            with transaction.atomic():
                form.save()
                task_formset.save()
                material_formset.save()
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "La jornada se actualizó correctamente.")
            return redirect("journey_list")
    return _journey_form_response(
        request,
        form,
        task_formset,
        material_formset,
        f"Editar jornada · {journey.fecha:%d/%m/%Y}",
        journey=journey,
    )


@login_required(login_url="/login/")
def journey_delete(request, jornada_id):
    if not _can_access(request.user, "gestion_publicidad.delete_trabajo"):
        return _forbidden()
    journey = get_object_or_404(TrabajoDia, pk=jornada_id)
    has_materials = journey.materiales_utilizados.exists()
    if request.method == "POST":
        restore_stock = request.POST.get("restore_stock") == "on"
        try:
            with transaction.atomic():
                if has_materials:
                    if restore_stock:
                        for material in journey.materiales_utilizados.select_related(
                            "insumo", "tipo_insumo"
                        ):
                            material.delete()
                    else:
                        journey.materiales_utilizados.update(jornada=None)
                journey.delete()
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar esta jornada porque tiene registros asociados.",
            )
            return redirect("journey_edit", jornada_id=journey.pk)
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("journey_edit", jornada_id=journey.pk)
        messages.success(request, "La jornada se eliminó correctamente.")
        return redirect("journey_list")
    warning = "La eliminación no se puede deshacer. Las tareas de esta jornada también se eliminarán."
    if has_materials:
        warning = (
            "La eliminación no se puede deshacer. Las tareas de esta jornada también se eliminarán. "
            "Elige cómo tratar los insumos utilizados."
        )
    return render(
        request,
        "gestion_publicidad/confirm_delete.html",
        _app_context(
            request,
            "jornadas",
            page_title=f"Eliminar jornada · {journey.fecha:%d/%m/%Y}",
            object_label=f"Jornada de {journey.trabajo} ({journey.fecha:%d/%m/%Y})",
            cancel_url=reverse("journey_edit", args=(journey.pk,)),
            warning=warning,
            show_restore_stock=has_materials,
        ),
    )


def _journey_form_response(request, form, task_formset, material_formset, title, journey=None):
    journey_delete_url = ""
    if journey and journey.pk and _can_access(request.user, "gestion_publicidad.delete_trabajo"):
        journey_delete_url = reverse("journey_delete", args=(journey.pk,))
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "jornadas",
            page_title=title,
            page_description="Las existencias se actualizan automáticamente al guardar los materiales.",
            form=form,
            task_formset=task_formset,
            material_formset=material_formset,
            cancel_url=reverse("journey_list"),
            submit_label="Guardar jornada",
            journey_delete_url=journey_delete_url,
        ),
    )


@login_required(login_url="/login/")
def receivables_list(request):
    if not _has_work_access(request.user, "view") and not _has_work_access(request.user, "change"):
        return _forbidden()
    works = TrabajoPorCobrar.objects.order_by("-fecha_creacion")
    query = request.GET.get("q", "").strip()
    if query:
        works = works.filter(Q(cliente__icontains=query) | Q(descripcion__icontains=query))
    return render(
        request,
        "gestion_publicidad/receivables_list.html",
        _app_context(
            request,
            "por-cobrar",
            page_title="Trabajos por cobrar",
            page_description="Trabajos finalizados que conservan un saldo pendiente.",
            trabajos_por_cobrar=works,
            query=query,
        ),
    )


@login_required(login_url="/login/")
def inventory_list(request):
    if not _has_inventory_access(request.user, "view") and not _has_inventory_access(request.user, "change"):
        return _forbidden()
    supplies = Insumo.objects.select_related("area").prefetch_related("tipos").order_by(
        "area__nombre", "nombre"
    )
    query = request.GET.get("q", "").strip()
    if query:
        supplies = supplies.filter(
            Q(nombre__icontains=query)
            | Q(area__nombre__icontains=query)
            | Q(tipos__nombre__icontains=query)
        ).distinct()
    areas = AreaInsumo.objects.order_by("nombre")
    return render(
        request,
        "gestion_publicidad/inventory_list.html",
        _app_context(
            request,
            "inventario",
            page_title="Insumos e inventario",
            page_description="Administra las existencias, áreas y variantes de insumos.",
            insumos=supplies,
            areas=areas,
            query=query,
        ),
    )


@login_required(login_url="/login/")
def inventory_create(request):
    if not _has_inventory_access(request.user, "add"):
        return _forbidden()
    form = InsumoForm(request.POST or None)
    types = TipoInsumoFormSet(request.POST or None, prefix="tipos")
    if request.method == "POST" and form.is_valid() and types.is_valid():
        with transaction.atomic():
            supply = form.save()
            types.instance = supply
            types.save()
        messages.success(request, f"El insumo “{supply.nombre}” se creó correctamente.")
        return redirect("inventory_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "inventario",
            page_title="Nuevo insumo",
            page_description="Registra existencias iniciales y, si aplica, variantes.",
            form=form,
            type_formset=types,
            cancel_url=reverse("inventory_list"),
            submit_label="Crear insumo",
        ),
    )


@login_required(login_url="/login/")
def inventory_edit(request, insumo_id):
    if not _has_inventory_access(request.user, "change"):
        return _forbidden()
    supply = get_object_or_404(Insumo, pk=insumo_id)
    form = InsumoForm(request.POST or None, instance=supply)
    types = TipoInsumoFormSet(request.POST or None, instance=supply, prefix="tipos")
    if request.method == "POST" and form.is_valid() and types.is_valid():
        try:
            with transaction.atomic():
                supply = form.save()
                types.instance = supply
                types.save()
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar una variante que ya está asociada a un trabajo.",
            )
        else:
            messages.success(request, "El insumo se actualizó correctamente.")
            return redirect("inventory_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "inventario",
            page_title=f"Editar insumo · {supply.nombre}",
            page_description="Los tipos asociados a trabajos no se pueden eliminar.",
            form=form,
            type_formset=types,
            cancel_url=reverse("inventory_list"),
            submit_label="Guardar insumo",
        ),
    )


@login_required(login_url="/login/")
def inventory_delete(request, insumo_id):
    if not _can_access(request.user, "gestion_publicidad.delete_insumo"):
        return _forbidden()
    supply = get_object_or_404(Insumo, pk=insumo_id)
    if request.method == "POST":
        try:
            supply.delete()
        except ProtectedError:
            messages.error(request, "No se puede eliminar un insumo utilizado en trabajos.")
            return redirect("inventory_list")
        messages.success(request, "El insumo se eliminó correctamente.")
        return redirect("inventory_list")
    return render(
        request,
        "gestion_publicidad/confirm_delete.html",
        _app_context(
            request,
            "inventario",
            page_title="Eliminar insumo",
            object_label=supply.nombre,
            cancel_url=reverse("inventory_list"),
            warning="La eliminación no se puede deshacer.",
        ),
    )


@login_required(login_url="/login/")
def area_create(request):
    if not _has_inventory_access(request.user, "add"):
        return _forbidden()
    form = AreaInsumoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "El área se creó correctamente.")
        return redirect("inventory_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "inventario",
            page_title="Nueva área de insumos",
            form=form,
            cancel_url=reverse("inventory_list"),
            submit_label="Crear área",
        ),
    )


@login_required(login_url="/login/")
def area_edit(request, area_id):
    if not _has_inventory_access(request.user, "change"):
        return _forbidden()
    area = get_object_or_404(AreaInsumo, pk=area_id)
    form = AreaInsumoForm(request.POST or None, instance=area)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "El área se actualizó correctamente.")
        return redirect("inventory_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "inventario",
            page_title=f"Editar área · {area.nombre}",
            form=form,
            cancel_url=reverse("inventory_list"),
            submit_label="Guardar área",
        ),
    )


@login_required(login_url="/login/")
def inventory_restock(request):
    if not _has_inventory_access(request.user, "change"):
        return _forbidden()
    form = ReabastecerInsumoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stock = form.reabastecer()
        messages.success(
            request,
            f"Existencia actualizada: {stock} ({stock.cantidad_disponible} {stock.unidad_medida}).",
        )
        return redirect("inventory_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "inventario",
            page_title="Reabastecer existencias",
            page_description="La cantidad se suma al stock actual de forma segura.",
            form=form,
            cancel_url=reverse("inventory_list"),
            submit_label="Reabastecer",
            include_form_scripts=True,
        ),
    )


@login_required(login_url="/login/")
def finance_list(request):
    if not _has_movement_access(request.user, "view") and not _has_movement_access(request.user, "change"):
        return _forbidden()
    movements = MovimientoFinanciero.objects.select_related(
        "trabajo", "empleado", "detalle_financiero__categoria"
    ).order_by("-fecha")
    query = request.GET.get("q", "").strip()
    kind = request.GET.get("tipo", "").strip()
    if query:
        movements = movements.filter(
            Q(descripcion__icontains=query)
            | Q(trabajo__cliente__icontains=query)
            | Q(empleado__username__icontains=query)
            | Q(empleado__first_name__icontains=query)
            | Q(empleado__last_name__icontains=query)
        )
    if kind in dict(MovimientoFinanciero.TIPO_CHOICES):
        movements = movements.filter(tipo=kind)
    for movement in movements:
        movement.moneda_panel = _movement_currency(movement)
    return render(
        request,
        "gestion_publicidad/finance_list.html",
        _app_context(
            request,
            "finanzas",
            page_title="Finanzas y movimientos",
            page_description="Consulta ingresos, egresos y sus categorías.",
            movimientos=movements,
            query=query,
            selected_kind=kind,
            type_choices=MovimientoFinanciero.TIPO_CHOICES,
            can_manage_categories=(
                _has_category_access(request.user, "view")
                or _has_category_access(request.user, "add")
                or _has_category_access(request.user, "change")
            ),
        ),
    )


@login_required(login_url="/login/")
def personal_list(request):
    if not _can_manage_personal(request.user):
        return _forbidden()
    users = get_user_model().objects.filter(is_superuser=False).prefetch_related(
        "groups", "user_permissions"
    )
    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    users = list(users.order_by("first_name", "last_name", "username"))
    for user in users:
        user.role_label = (
            "Administrador"
            if any(group.name == "Administrador" for group in user.groups.all())
            else "Empleado"
        )
    return render(
        request,
        "gestion_publicidad/personal_list.html",
        _app_context(
            request,
            "personal",
            page_title="Personal",
            page_description="Administra las cuentas, roles y permisos de acceso.",
            usuarios=users,
            query=query,
        ),
    )


@login_required(login_url="/login/")
def personal_detail(request, usuario_id):
    if not _can_manage_personal(request.user):
        return _forbidden()
    user = _managed_user(usuario_id)
    role_label = (
        "Administrador"
        if user.groups.filter(name="Administrador").exists()
        else "Empleado"
    )
    permissions = user.user_permissions.filter(
        content_type__app_label__in=("gestion_publicidad", "Gestion_Finanzas")
    ).order_by("content_type__app_label", "content_type__model", "codename")
    return render(
        request,
        "gestion_publicidad/personal_detail.html",
        _app_context(
            request,
            "personal",
            page_title=f"Personal · {user.get_full_name() or user.username}",
            usuario=user,
            role_label=role_label,
            permisos=permissions,
        ),
    )


@login_required(login_url="/login/")
def personal_create(request):
    if not _can_manage_personal(request.user):
        return _forbidden()
    form = PersonalUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"La cuenta de {user.get_username()} se creó correctamente.")
        return redirect("personal_detail", usuario_id=user.pk)
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "personal",
            page_title="Agregar integrante",
            page_description="Crea una cuenta y asigna su rol y permisos.",
            form=form,
            cancel_url=reverse("personal_list"),
            submit_label="Crear cuenta",
        ),
    )


@login_required(login_url="/login/")
def personal_edit(request, usuario_id):
    if not _can_manage_personal(request.user):
        return _forbidden()
    user = _managed_user(usuario_id)
    form = PersonalUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"La cuenta de {user.get_username()} se actualizó.")
        return redirect("personal_detail", usuario_id=user.pk)
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "personal",
            page_title=f"Editar integrante · {user.get_username()}",
            page_description="Actualiza el rol, acceso y permisos individuales.",
            form=form,
            cancel_url=reverse("personal_detail", args=(user.pk,)),
            submit_label="Guardar cambios",
        ),
    )


@login_required(login_url="/login/")
def personal_delete(request, usuario_id):
    if not _can_manage_personal(request.user):
        return _forbidden()
    user = _managed_user(usuario_id)
    if request.user.pk == user.pk:
        messages.error(request, "No puedes eliminar la cuenta con la que has iniciado sesión.")
        return redirect("personal_detail", usuario_id=user.pk)
    is_active_administrator = (
        user.is_active and user.groups.filter(name="Administrador").exists()
    )
    if is_active_administrator and not _has_another_active_administrator(user.pk):
        messages.error(request, "Debe permanecer al menos un administrador activo.")
        return redirect("personal_detail", usuario_id=user.pk)
    if request.method == "POST":
        username = user.get_username()
        user.delete()
        messages.success(request, f"La cuenta de {username} se eliminó.")
        return redirect("personal_list")
    return render(
        request,
        "gestion_publicidad/confirm_delete.html",
        _app_context(
            request,
            "personal",
            page_title="Eliminar integrante",
            object_label=user.get_full_name() or user.get_username(),
            cancel_url=reverse("personal_detail", args=(user.pk,)),
            warning="La cuenta y sus permisos se eliminarán permanentemente.",
        ),
    )


@login_required(login_url="/login/")
def movement_create(request):
    if not _has_movement_access(request.user, "add"):
        return _forbidden()
    form = MovimientoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            movement = form.save()
            detail, _ = DetalleMovimientoFinanciero.objects.get_or_create(
                movimiento=movement
            )
            detail.fecha_transaccion = form.cleaned_data["fecha_transaccion"]
            detail.categoria = form.cleaned_data["categoria_financiera"]
            detail.save(update_fields=("fecha_transaccion", "categoria"))
        messages.success(request, "El movimiento se registró correctamente.")
        return redirect("finance_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "finanzas",
            page_title="Registrar movimiento",
            page_description="Registra un ingreso o egreso en el ledger financiero.",
            form=form,
            cancel_url=reverse("finance_list"),
            submit_label="Registrar movimiento",
        ),
    )


@login_required(login_url="/login/")
def movement_edit(request, movimiento_id):
    if not _has_movement_access(request.user, "change"):
        return _forbidden()
    movement = get_object_or_404(MovimientoFinanciero, pk=movimiento_id)
    form = MovimientoForm(request.POST or None, instance=movement)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            movement = form.save()
            detail, _ = DetalleMovimientoFinanciero.objects.get_or_create(
                movimiento=movement
            )
            detail.fecha_transaccion = form.cleaned_data["fecha_transaccion"]
            detail.categoria = form.cleaned_data["categoria_financiera"]
            detail.save(update_fields=("fecha_transaccion", "categoria"))
        messages.success(request, "El movimiento se actualizó correctamente.")
        return redirect("finance_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "finanzas",
            page_title=f"Editar movimiento #{movement.pk}",
            form=form,
            cancel_url=reverse("finance_list"),
            submit_label="Guardar cambios",
        ),
    )


@login_required(login_url="/login/")
def movement_delete(request, movimiento_id):
    if not _can_access(request.user, "gestion_publicidad.delete_movimientofinanciero"):
        return _forbidden()
    movement = get_object_or_404(MovimientoFinanciero, pk=movimiento_id)
    if request.method == "POST":
        movement.delete()
        messages.success(request, "El movimiento se eliminó correctamente.")
        return redirect("finance_list")
    return render(
        request,
        "gestion_publicidad/confirm_delete.html",
        _app_context(
            request,
            "finanzas",
            page_title="Eliminar movimiento",
            object_label=str(movement),
            cancel_url=reverse("finance_list"),
            warning="El registro financiero se eliminará permanentemente.",
        ),
    )


@login_required(login_url="/login/")
def category_list(request):
    if not any(
        _has_category_access(request.user, permission)
        for permission in ("view", "add", "change")
    ):
        return _forbidden()
    categories = CategoriaFinanciera.objects.order_by("nombre")
    return render(
        request,
        "gestion_publicidad/category_list.html",
        _app_context(
            request,
            "finanzas",
            page_title="Categorías financieras",
            categorias=categories,
            can_add_category=_has_category_access(request.user, "add"),
            can_change_category=_has_category_access(request.user, "change"),
        ),
    )


@login_required(login_url="/login/")
def category_create(request):
    if not _has_category_access(request.user, "add"):
        return _forbidden()
    form = CategoriaFinancieraForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La categoría se creó correctamente.")
        return redirect("category_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "finanzas",
            page_title="Nueva categoría financiera",
            form=form,
            cancel_url=reverse("category_list"),
            submit_label="Crear categoría",
        ),
    )


@login_required(login_url="/login/")
def category_edit(request, categoria_id):
    if not _has_category_access(request.user, "change"):
        return _forbidden()
    category = get_object_or_404(CategoriaFinanciera, pk=categoria_id)
    form = CategoriaFinancieraForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La categoría se actualizó correctamente.")
        return redirect("category_list")
    return render(
        request,
        "gestion_publicidad/form_page.html",
        _app_context(
            request,
            "finanzas",
            page_title=f"Editar categoría · {category.nombre}",
            form=form,
            cancel_url=reverse("category_list"),
            submit_label="Guardar categoría",
        ),
    )
