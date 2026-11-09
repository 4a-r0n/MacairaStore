"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path

from gestion_publicidad import views as gestion_publicidad_views

urlpatterns = [
    path('', gestion_publicidad_views.dashboard, name='dashboard'),
    path('login/', gestion_publicidad_views.login_view, name='login'),
    path('logout/', gestion_publicidad_views.logout_view, name='logout'),
    path('trabajos/', gestion_publicidad_views.work_list, name='work_list'),
    path('trabajos/nuevo/', gestion_publicidad_views.work_create, name='work_create'),
    path('trabajos/<int:trabajo_id>/', gestion_publicidad_views.work_detail, name='work_detail'),
    path('trabajos/<int:trabajo_id>/editar/', gestion_publicidad_views.work_edit, name='work_edit'),
    path('trabajos/<int:trabajo_id>/eliminar/', gestion_publicidad_views.work_delete, name='work_delete'),
    path('jornadas/', gestion_publicidad_views.journey_list, name='journey_list'),
    path('jornadas/nueva/', gestion_publicidad_views.journey_create, name='journey_create'),
    path('jornadas/<int:jornada_id>/editar/', gestion_publicidad_views.journey_edit, name='journey_edit'),
    path('jornadas/<int:jornada_id>/eliminar/', gestion_publicidad_views.journey_delete, name='journey_delete'),
    path('por-cobrar/', gestion_publicidad_views.receivables_list, name='receivables_list'),
    path('inventario/', gestion_publicidad_views.inventory_list, name='inventory_list'),
    path('inventario/nuevo/', gestion_publicidad_views.inventory_create, name='inventory_create'),
    path('inventario/<int:insumo_id>/editar/', gestion_publicidad_views.inventory_edit, name='inventory_edit'),
    path('inventario/<int:insumo_id>/eliminar/', gestion_publicidad_views.inventory_delete, name='inventory_delete'),
    path('inventario/areas/nueva/', gestion_publicidad_views.area_create, name='area_create'),
    path('inventario/areas/<int:area_id>/editar/', gestion_publicidad_views.area_edit, name='area_edit'),
    path('inventario/reabastecer/', gestion_publicidad_views.inventory_restock, name='inventory_restock'),
    path('finanzas/', gestion_publicidad_views.finance_list, name='finance_list'),
    path('finanzas/movimientos/nuevo/', gestion_publicidad_views.movement_create, name='movement_create'),
    path('finanzas/movimientos/<int:movimiento_id>/editar/', gestion_publicidad_views.movement_edit, name='movement_edit'),
    path('finanzas/movimientos/<int:movimiento_id>/eliminar/', gestion_publicidad_views.movement_delete, name='movement_delete'),
    path('personal/', gestion_publicidad_views.personal_list, name='personal_list'),
    path('personal/nuevo/', gestion_publicidad_views.personal_create, name='personal_create'),
    path('personal/<int:usuario_id>/', gestion_publicidad_views.personal_detail, name='personal_detail'),
    path('personal/<int:usuario_id>/editar/', gestion_publicidad_views.personal_edit, name='personal_edit'),
    path('personal/<int:usuario_id>/eliminar/', gestion_publicidad_views.personal_delete, name='personal_delete'),
    path('finanzas/categorias/', gestion_publicidad_views.category_list, name='category_list'),
    path('finanzas/categorias/nueva/', gestion_publicidad_views.category_create, name='category_create'),
    path('finanzas/categorias/<int:categoria_id>/editar/', gestion_publicidad_views.category_edit, name='category_edit'),
    path('admin/', gestion_publicidad_views.legacy_admin_redirect, name='legacy_admin_redirect'),
    path('admin/<path:remaining_path>', gestion_publicidad_views.legacy_admin_redirect),
    path('api/insumos/', gestion_publicidad_views.insumos_por_area, name='insumos_por_area'),
    path(
        'jornadas/tareas/<int:tarea_id>/alternar/',
        gestion_publicidad_views.alternar_tarea,
        name='alternar_tarea',
    ),
]
