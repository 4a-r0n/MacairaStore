import calendar
from datetime import date

from django.db.models import Prefetch

from .models import Trabajo, TrabajoDia, TrabajoInsumo


def build_work_calendar(year, month):
    month_date = date(year, month, 1)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    start_date = weeks[0][0]
    end_date = weeks[-1][-1]

    journeys_by_date = {}
    journeys = (
        TrabajoDia.objects.filter(fecha__range=(start_date, end_date))
        .select_related("trabajo")
        .prefetch_related(
            "tareas",
            Prefetch(
                "materiales_utilizados",
                queryset=TrabajoInsumo.objects.select_related("insumo", "tipo_insumo"),
            ),
        )
    )
    for journey in journeys:
        tasks = list(journey.tareas.all())
        journey.total_tareas = len(tasks)
        journey.tareas_terminadas = sum(task.completada for task in tasks)
        journey.tareas_lista = tasks
        materials = {}
        for material in journey.materiales_utilizados.all():
            stock_item = material.tipo_insumo or material.insumo
            name = material.tipo_insumo.nombre if material.tipo_insumo else material.insumo.nombre
            key = (stock_item._meta.label_lower, stock_item.pk)
            if key not in materials:
                materials[key] = {"nombre": name, "unidad": stock_item.unidad_medida, "cantidad": 0}
            materials[key]["cantidad"] += material.cantidad_utilizada
        journey.resumen_materiales = list(materials.values())
        journeys_by_date.setdefault(journey.fecha, []).append(journey)

    deliveries_by_date = {}
    deliveries = (
        Trabajo.objects.filter(fecha_limite__range=(start_date, end_date))
        .exclude(entregado=True)
        .order_by("cliente", "id")
    )
    for work in deliveries:
        deliveries_by_date.setdefault(work.fecha_limite, []).append(work)

    calendar_cells = [
        [
            {
                "fecha": day,
                "otro_mes": day.month != month,
                "jornadas": journeys_by_date.get(day, []),
                "entregas": deliveries_by_date.get(day, []),
            }
            for day in week
        ]
        for week in weeks
    ]

    previous_month = date(year - (month == 1), 12 if month == 1 else month - 1, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return {
        "celdas": calendar_cells,
        "mes_actual": month_date,
        "mes_anterior": previous_month.strftime("%Y-%m"),
        "mes_siguiente": next_month.strftime("%Y-%m"),
    }
