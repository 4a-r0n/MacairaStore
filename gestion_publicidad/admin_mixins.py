from datetime import datetime
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse


class DashboardReturnMixin:
    dashboard_sections = {
        "trabajos",
        "jornadas",
        "por-cobrar",
        "inventario",
        "finanzas",
    }

    def _dashboard_redirect(self, request):
        section = request.GET.get("dashboard_section")
        if request.user.is_staff and section in self.dashboard_sections:
            query = {}
            for parameter in ("finance_month", "calendar_month"):
                value = request.GET.get(parameter, "")
                try:
                    parsed = datetime.strptime(value, "%Y-%m")
                except ValueError:
                    continue
                if parsed.year < 1900 or parsed.year > 9998:
                    continue
                query[parameter] = value
            query_string = f"?{urlencode(query)}" if query else ""
            return redirect(f"{reverse('dashboard')}{query_string}#{section}")
        return None

    def response_add(self, request, obj, post_url_continue=None):
        response = super().response_add(request, obj, post_url_continue)
        return self._dashboard_redirect(request) or response

    def response_change(self, request, obj):
        response = super().response_change(request, obj)
        return self._dashboard_redirect(request) or response

    def response_delete(self, request, obj_display, obj_id):
        response = super().response_delete(request, obj_display, obj_id)
        return self._dashboard_redirect(request) or response
