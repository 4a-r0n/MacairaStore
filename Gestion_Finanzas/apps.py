from django.apps import AppConfig


class GestionFinanzasConfig(AppConfig):
    name = 'Gestion_Finanzas'
    verbose_name = "Gestión de Finanzas"

    def ready(self):
        from . import signals
