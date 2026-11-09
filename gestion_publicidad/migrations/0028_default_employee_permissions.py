from django.conf import settings
from django.db import migrations
from django.db.models import Q


BUSINESS_MODELS = (
    "areainsumo",
    "insumo",
    "tipoinsumo",
    "trabajo",
    "trabajoinsumo",
    "trabajodia",
    "tareatrabajodia",
)


def grant_default_employee_permissions(apps, schema_editor):
    using = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    employee_group, _ = Group.objects.using(using).get_or_create(name="Empleado")
    codenames = [
        f"{action}_{model}"
        for model in BUSINESS_MODELS
        for action in ("view", "add", "change")
    ] + ["view_movimientofinanciero", "add_movimientofinanciero"]
    disallowed_permissions = Permission.objects.using(using).filter(
        Q(content_type__app_label="Gestion_Finanzas")
        | Q(
            content_type__app_label="gestion_publicidad",
        )
        & ~Q(codename__in=codenames)
        | Q(content_type__app_label="auth", content_type__model="user")
    )
    employee_group.permissions.remove(*disallowed_permissions)
    permissions = []
    for app_label, model_names in (
        ("gestion_publicidad", (*BUSINESS_MODELS, "movimientofinanciero")),
    ):
        for model_name in model_names:
            content_type, _ = ContentType.objects.using(using).get_or_create(
                app_label=app_label,
                model=model_name,
            )
            for action in ("view", "add", "change"):
                codename = f"{action}_{model_name}"
                if codename not in codenames:
                    continue
                permission, _ = Permission.objects.using(using).get_or_create(
                    content_type=content_type,
                    codename=codename,
                    defaults={"name": f"Can {action} {model_name}"},
                )
                permissions.append(permission)

    for user in User.objects.using(using).filter(
        is_superuser=False,
        groups__name=employee_group.name,
    ).exclude(groups__name="Administrador").distinct():
        if not user.is_staff:
            User.objects.using(using).filter(pk=user.pk).update(is_staff=True)
        user.user_permissions.remove(*disallowed_permissions)
        user.user_permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("gestion_publicidad", "0027_alter_movimientofinanciero_metodo_pago_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            grant_default_employee_permissions,
            migrations.RunPython.noop,
        ),
    ]
