from django.db import migrations


def assign_no_area(apps, schema_editor):
    AreaInsumo = apps.get_model('gestion_publicidad', 'AreaInsumo')
    Insumo = apps.get_model('gestion_publicidad', 'Insumo')
    TrabajoInsumo = apps.get_model('gestion_publicidad', 'TrabajoInsumo')
    database = schema_editor.connection.alias

    no_area, _ = AreaInsumo.objects.using(database).get_or_create(nombre="Sin área")
    Insumo.objects.using(database).filter(area__isnull=True).update(area_id=no_area.pk)

    rows_without_area = (
        TrabajoInsumo.objects.using(database)
        .filter(area__isnull=True, insumo__isnull=False)
        .values_list('pk', 'insumo__area_id')
    )
    for row_id, area_id in rows_without_area.iterator():
        if area_id:
            TrabajoInsumo.objects.using(database).filter(pk=row_id).update(area_id=area_id)


class Migration(migrations.Migration):

    dependencies = [
        ('gestion_publicidad', '0011_insumo_cantidad_disponible_insumo_unidad_medida'),
    ]

    operations = [
        migrations.RunPython(assign_no_area, migrations.RunPython.noop),
    ]
