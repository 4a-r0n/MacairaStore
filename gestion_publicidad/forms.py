from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory

from Gestion_Finanzas.models import CategoriaFinanciera, DetalleMovimientoFinanciero
from .models import (
    AreaInsumo,
    DEFAULT_EMPLOYEE_PERMISSION_CODENAMES,
    Insumo,
    MovimientoFinanciero,
    TareaTrabajoDia,
    TipoInsumo,
    Trabajo,
    TrabajoDia,
    TrabajoInsumo,
)


def _style_fields(form):
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")


class TrabajoForm(forms.ModelForm):
    class Meta:
        model = Trabajo
        fields = (
            "cliente",
            "descripcion",
            "monto_total",
            "tipo_pago",
            "monto_abono",
            "metodo_pago",
            "plataforma",
            "tipo_cuenta",
            "estado",
            "fecha_limite",
        )
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "fecha_limite": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        payment_type = (
            self.data.get(self.add_prefix("tipo_pago"))
            if self.is_bound
            else self.initial.get("tipo_pago", self.instance.tipo_pago or "NADA")
        )
        self.initially_hidden_fields = set()
        if payment_type in ("NADA", ""):
            self.initially_hidden_fields.update(
                ("monto_abono", "metodo_pago", "plataforma", "tipo_cuenta")
            )
        elif payment_type == "TOTAL":
            self.initially_hidden_fields.add("monto_abono")
        self.fields["tipo_pago"].widget.attrs["data-job-payment-type"] = ""
        for name in ("monto_abono", "metodo_pago", "plataforma", "tipo_cuenta"):
            self.fields[name].widget.attrs["data-job-payment-field"] = name
        self.fields["monto_abono"].label = "Monto Abono"
        _style_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get("tipo_pago")
        if payment_type in ("TOTAL", "ABONO") and not cleaned_data.get("metodo_pago"):
            self.add_error("metodo_pago", "Selecciona un método para registrar el pago.")
        if payment_type == "NADA":
            cleaned_data["monto_abono"] = None
            cleaned_data["metodo_pago"] = None
            cleaned_data["plataforma"] = "NINGUNA"
            cleaned_data["tipo_cuenta"] = "USD"
        elif payment_type == "TOTAL":
            cleaned_data["monto_abono"] = None
        if cleaned_data.get("metodo_pago") == "EFECTIVO_USD":
            cleaned_data["plataforma"] = "NINGUNA"
            cleaned_data["tipo_cuenta"] = "USD"
        elif cleaned_data.get("metodo_pago") == "PAGO_MOVIL":
            cleaned_data["plataforma"] = "BANCO_NACIONAL"
            cleaned_data["tipo_cuenta"] = "VES"
        return cleaned_data


class TrabajoUpdateForm(forms.ModelForm):
    class Meta:
        model = Trabajo
        fields = ("cliente", "descripcion", "estado", "fecha_limite")
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "fecha_limite": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = (
            "area",
            "nombre",
            "tiene_tipos",
            "cantidad_disponible",
            "stock_minimo",
            "unidad_medida",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].queryset = AreaInsumo.objects.order_by("nombre")
        if self.instance.pk and (
            self.instance.tiene_tipos or self.instance.tipos.exists()
        ):
            for name in ("cantidad_disponible", "stock_minimo", "unidad_medida"):
                self.fields.pop(name)
        _style_fields(self)


class TipoInsumoForm(forms.ModelForm):
    class Meta:
        model = TipoInsumo
        fields = ("nombre", "unidad_medida", "cantidad_disponible", "stock_minimo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def has_changed(self):
        if self.is_bound and not self.instance.pk:
            has_text_input = any(
                self.data.get(self.add_prefix(field), "").strip()
                for field in ("nombre", "unidad_medida")
            )
            has_non_default_stock = (
                self.data.get(self.add_prefix("cantidad_disponible"), "0") not in ("", "0", "0.00")
                or self.data.get(self.add_prefix("stock_minimo"), "20") not in ("", "20", "20.00")
            )
            if not has_text_input and not has_non_default_stock:
                return False
        return super().has_changed()


TipoInsumoFormSet = inlineformset_factory(
    Insumo, TipoInsumo, form=TipoInsumoForm, extra=1, can_delete=True
)


class AreaInsumoForm(forms.ModelForm):
    class Meta:
        model = AreaInsumo
        fields = ("nombre",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class ReabastecerInsumoForm(forms.Form):
    area = forms.ModelChoiceField(queryset=AreaInsumo.objects.order_by("nombre"), label="Área")
    insumo = forms.ModelChoiceField(queryset=Insumo.objects.none(), label="Insumo")
    tipo_insumo = forms.ModelChoiceField(
        queryset=TipoInsumo.objects.none(), required=False, label="Tipo de insumo"
    )
    cantidad = forms.DecimalField(
        min_value=0.01, max_digits=10, decimal_places=2, label="Cantidad a reabastecer"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        area_id = self.data.get("area") if self.is_bound else None
        insumo_id = self.data.get("insumo") if self.is_bound else None
        if area_id:
            self.fields["insumo"].queryset = Insumo.objects.filter(
                area_id=area_id
            ).order_by("nombre")
        if insumo_id:
            self.fields["tipo_insumo"].queryset = TipoInsumo.objects.filter(
                insumo_id=insumo_id
            ).order_by("nombre")
        _style_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        area = cleaned_data.get("area")
        insumo = cleaned_data.get("insumo")
        tipo = cleaned_data.get("tipo_insumo")
        if area and insumo and insumo.area_id != area.pk:
            self.add_error("insumo", "Selecciona un insumo del área elegida.")
        if insumo:
            has_types = insumo.tiene_tipos or insumo.tipos.exists()
            if has_types and not tipo:
                self.add_error("tipo_insumo", "Selecciona una variante del insumo.")
            elif tipo and tipo.insumo_id != insumo.pk:
                self.add_error("tipo_insumo", "La variante no pertenece al insumo elegido.")
        return cleaned_data

    def reabastecer(self):
        from django.db import transaction

        obj = self.cleaned_data["tipo_insumo"] or self.cleaned_data["insumo"]
        with transaction.atomic():
            obj = type(obj).objects.select_for_update().get(pk=obj.pk)
            obj.cantidad_disponible += self.cleaned_data["cantidad"]
            obj.save(update_fields=("cantidad_disponible",))
        return obj


class TrabajoDiaForm(forms.ModelForm):
    class Meta:
        model = TrabajoDia
        fields = ("trabajo", "fecha", "notas")
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "notas": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["trabajo"].queryset = Trabajo.objects.order_by("-fecha_creacion")
        _style_fields(self)


class TareaTrabajoDiaForm(forms.ModelForm):
    class Meta:
        model = TareaTrabajoDia
        fields = ("descripcion", "completada")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class TrabajoInsumoForm(forms.ModelForm):
    class Meta:
        model = TrabajoInsumo
        fields = ("area", "insumo", "tipo_insumo", "cantidad_utilizada")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        area_id = (
            self.data.get(self.add_prefix("area"))
            if self.is_bound
            else self.instance.area_id
        )
        insumo_id = (
            self.data.get(self.add_prefix("insumo"))
            if self.is_bound
            else self.instance.insumo_id
        )
        self.fields["area"].queryset = AreaInsumo.objects.order_by("nombre")
        self.fields["insumo"].queryset = (
            Insumo.objects.filter(area_id=area_id).order_by("nombre")
            if area_id
            else Insumo.objects.none()
        )
        self.fields["tipo_insumo"].queryset = (
            TipoInsumo.objects.filter(insumo_id=insumo_id).order_by("nombre")
            if insumo_id
            else TipoInsumo.objects.none()
        )
        self.fields["area"].required = True
        self.fields["insumo"].required = True
        _style_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        area = cleaned_data.get("area")
        insumo = cleaned_data.get("insumo")
        tipo = cleaned_data.get("tipo_insumo")
        amount = cleaned_data.get("cantidad_utilizada")
        if area and insumo and insumo.area_id != area.pk:
            self.add_error("insumo", "El insumo no pertenece al área elegida.")
        if insumo and tipo and tipo.insumo_id != insumo.pk:
            self.add_error("tipo_insumo", "La variante no pertenece al insumo elegido.")
        if insumo and not tipo and (insumo.tiene_tipos or insumo.tipos.exists()):
            self.add_error("tipo_insumo", "Selecciona una variante del insumo.")
        stock = tipo or insumo
        if stock and amount is not None:
            available = stock.cantidad_disponible
            previous = self.instance.tipo_insumo or self.instance.insumo
            if self.instance.pk and previous and previous.pk == stock.pk and type(previous) is type(stock):
                available += self.instance.cantidad_utilizada
            if amount > available:
                self.add_error(
                    "cantidad_utilizada",
                    f"Stock insuficiente. Disponible: {available}.",
                )
        return cleaned_data


TareaFormSet = inlineformset_factory(
    TrabajoDia, TareaTrabajoDia, form=TareaTrabajoDiaForm, extra=1, can_delete=False
)
MaterialFormSet = inlineformset_factory(
    TrabajoDia, TrabajoInsumo, form=TrabajoInsumoForm, extra=1, can_delete=False
)


class FinanceCategorySelect(forms.Select):
    def __init__(self, *args, category_metadata=None, **kwargs):
        self.category_metadata = category_metadata or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        category_id = str(getattr(value, "value", value))
        category = self.category_metadata.get(category_id)
        if category:
            option["attrs"]["data-category-kind"] = category["tipo"]
            if category["nombre"] in ("Abonos de clientes", "Otros ingresos"):
                option["attrs"]["data-income-category"] = category["nombre"]
            if category["nombre"] in ("Materiales e insumos", "Pago a empleados", "Reembolsos"):
                option["attrs"]["data-expense-category"] = category["nombre"]
        return option


class MovimientoForm(forms.ModelForm):
    fecha_transaccion = forms.DateField(
        label="Fecha de la transacción",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    categoria_financiera = forms.ModelChoiceField(
        queryset=CategoriaFinanciera.objects.none(),
        required=False,
        label="Categoría financiera",
    )
    empleado = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False, label="Empleado"
    )

    class Meta:
        model = MovimientoFinanciero
        fields = (
            "tipo",
            "monto",
            "tipo_ingreso",
            "categoria_egreso",
            "fecha_transaccion",
            "categoria_financiera",
            "metodo_pago",
            "plataforma",
            "tipo_cuenta",
            "descripcion",
            "trabajo",
            "empleado",
        )
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = CategoriaFinanciera.objects.filter(activa=True)
        current_category_id = None
        if self.instance.pk:
            current_category_id = (
                DetalleMovimientoFinanciero.objects.filter(movimiento_id=self.instance.pk)
                .values_list("categoria_id", flat=True)
                .first()
            )
            if current_category_id:
                categories = CategoriaFinanciera.objects.filter(
                    Q(activa=True) | Q(pk=current_category_id)
                )
        self.fields["categoria_financiera"].queryset = categories.order_by("nombre")
        self.fields["categoria_financiera"].widget = FinanceCategorySelect(
            category_metadata={
                str(category.pk): {"tipo": category.tipo, "nombre": category.nombre}
                for category in categories
            }
        )
        self.fields["categoria_financiera"].widget.choices = (
            self.fields["categoria_financiera"].choices
        )
        group = Group.objects.filter(name="Empleado").first()
        if group:
            self.fields["empleado"].queryset = get_user_model().objects.filter(
                groups=group, is_active=True, is_superuser=False
            ).order_by("first_name", "last_name", "username")
        movement_type = (
            self.data.get("tipo")
            if self.is_bound
            else self.initial.get("tipo", self.instance.tipo or "INGRESO")
        )
        self.fields["tipo_ingreso"].required = movement_type == "INGRESO"
        self.fields["categoria_egreso"].required = movement_type == "EGRESO"
        expense_type = (
            self.data.get("categoria_egreso")
            if self.is_bound
            else self.initial.get("categoria_egreso", self.instance.categoria_egreso)
        )
        self.fields["empleado"].required = (
            movement_type == "EGRESO" and expense_type == "PAGO_EMPLEADOS"
        )
        self.fields["tipo"].widget.attrs["data-movement-type"] = ""
        for field_name in (
            "tipo_ingreso",
            "categoria_egreso",
            "metodo_pago",
            "plataforma",
            "tipo_cuenta",
            "trabajo",
            "empleado",
            "categoria_financiera",
        ):
            self.fields[field_name].widget.attrs["data-movement-field"] = field_name
        self.fields["metodo_pago"].widget.attrs["data-payment-method"] = ""
        if movement_type == "EGRESO":
            self.fields["metodo_pago"].choices = [
                choice for choice in self.fields["metodo_pago"].choices
                if choice[0] != "TARJETA"
            ]
        if self.instance.pk:
            detail = DetalleMovimientoFinanciero.objects.filter(
                movimiento_id=self.instance.pk
            ).first()
            self.initial["fecha_transaccion"] = (
                detail.fecha_transaccion if detail else self.instance.fecha.date()
            )
            if detail:
                self.initial["categoria_financiera"] = detail.categoria_id
        else:
            from django.utils import timezone

            self.initial.setdefault("fecha_transaccion", timezone.localdate())
        _style_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo")
        payment_type = cleaned_data.get("tipo_ingreso")
        expense_type = cleaned_data.get("categoria_egreso")
        method = cleaned_data.get("metodo_pago")
        category_names = {
            ("INGRESO", "ABONO_CLIENTES"): ("Abonos de clientes", ("INCOME", "BOTH")),
            ("INGRESO", "OTROS_INGRESOS"): ("Otros ingresos", ("INCOME", "BOTH")),
            ("EGRESO", "COMPRA_MATERIAL"): ("Materiales e insumos", ("EXPENSE", "BOTH")),
            ("EGRESO", "PAGO_EMPLEADOS"): ("Pago a empleados", ("EXPENSE", "BOTH")),
            ("EGRESO", "REEMBOLSO_CLIENTE"): ("Reembolsos", ("EXPENSE", "BOTH")),
        }

        if tipo == "INGRESO":
            cleaned_data["categoria_egreso"] = ""
            cleaned_data["empleado"] = None
            if payment_type == "OTROS_INGRESOS":
                cleaned_data["trabajo"] = None
        elif tipo == "EGRESO":
            cleaned_data["tipo_ingreso"] = None
            if expense_type != "REEMBOLSO_CLIENTE":
                cleaned_data["trabajo"] = None
            if expense_type != "PAGO_EMPLEADOS":
                cleaned_data["empleado"] = None

        category_definition = category_names.get(
            (tipo, payment_type if tipo == "INGRESO" else expense_type)
        )
        if category_definition:
            category_name, allowed_kinds = category_definition
            category = CategoriaFinanciera.objects.filter(
                activa=True,
                nombre=category_name,
                tipo__in=allowed_kinds,
            ).first()
            if category is None:
                self.add_error(
                    "categoria_financiera",
                    f"Activa la categoría financiera “{category_name}” para continuar.",
                )
            else:
                cleaned_data["categoria_financiera"] = category
        else:
            category = cleaned_data.get("categoria_financiera")
            expected_kind = "INCOME" if tipo == "INGRESO" else "EXPENSE"
            if category and category.tipo not in (expected_kind, "BOTH"):
                self.add_error(
                    "categoria_financiera",
                    "Selecciona una categoría correspondiente al tipo de movimiento.",
                )

        if tipo == "EGRESO":
            if not expense_type and "categoria_egreso" not in self.errors:
                self.add_error("categoria_egreso", "Selecciona la categoría del egreso.")
            elif (
                expense_type == "PAGO_EMPLEADOS"
                and not cleaned_data.get("empleado")
                and "empleado" not in self.errors
            ):
                self.add_error("empleado", "Selecciona el empleado al que se realizará el pago.")
            if method == "TARJETA":
                self.add_error("metodo_pago", "Tarjeta no está disponible para egresos.")
        elif tipo == "INGRESO" and not payment_type and "tipo_ingreso" not in self.errors:
            self.add_error("tipo_ingreso", "Selecciona el tipo de ingreso.")

        if method == "EFECTIVO_USD":
            cleaned_data["plataforma"] = None
            cleaned_data["tipo_cuenta"] = None
        elif method == "PAGO_MOVIL":
            cleaned_data["plataforma"] = "BANCO_NACIONAL"
            cleaned_data["tipo_cuenta"] = "VES"
        return cleaned_data


class PersonalUserForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=(("Administrador", "Administrador"), ("Empleado", "Empleado")),
        label="Rol",
        help_text="Administrador tiene acceso total; Empleado usa permisos individuales.",
    )
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(
            content_type__app_label="gestion_publicidad",
            codename__in=DEFAULT_EMPLOYEE_PERMISSION_CODENAMES,
        ).order_by("content_type__model", "codename"),
        required=False,
        label="Permisos del empleado",
        help_text="Selecciona las acciones que este empleado puede realizar.",
        widget=forms.CheckboxSelectMultiple,
    )
    password1 = forms.CharField(
        label="Contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput,
    )

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_active")
        labels = {
            "username": "Nombre de usuario",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
            "is_active": "Cuenta activa",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        if self.instance.pk:
            self.initial["role"] = (
                "Administrador"
                if self.instance.groups.filter(name="Administrador").exists()
                else "Empleado"
            )
            self.initial["permissions"] = self.instance.user_permissions.filter(
                content_type__app_label="gestion_publicidad",
                codename__in=DEFAULT_EMPLOYEE_PERMISSION_CODENAMES,
            )
            self.fields["password1"].label = "Nueva contraseña (opcional)"
            self.fields["password2"].label = "Confirmar nueva contraseña"
        else:
            self.initial.setdefault("role", "Empleado")
            self.initial.setdefault(
                "permissions",
                self.fields["permissions"].queryset,
            )
        _style_fields(self)

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if not self.instance.pk and not password1:
            self.add_error("password1", "La contraseña es obligatoria para crear la cuenta.")
        elif password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            elif password1:
                try:
                    validate_password(password1, self.instance)
                except ValidationError as error:
                    self.add_error("password1", error)

        if (
            self.instance.pk
            and self.instance.groups.filter(name="Administrador").exists()
            and (
                cleaned_data.get("role") != "Administrador"
                or not cleaned_data.get("is_active")
            )
            and not get_user_model().objects.filter(
                is_active=True, is_superuser=True
            ).exists()
            and not get_user_model().objects.filter(
                is_active=True, groups__name="Administrador"
            ).exclude(pk=self.instance.pk).exists()
        ):
            self.add_error(
                "role",
                "Debe permanecer al menos un administrador activo en el sistema.",
            )
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            administrator_group, _ = Group.objects.get_or_create(name="Administrador")
            employee_group, _ = Group.objects.get_or_create(name="Empleado")
            user.groups.set(
                [administrator_group]
                if self.cleaned_data["role"] == "Administrador"
                else [employee_group]
            )
            user.user_permissions.set(
                self.cleaned_data["permissions"]
                if self.cleaned_data["role"] == "Empleado"
                else []
            )
        return user


class CategoriaFinancieraForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanciera
        fields = ("nombre", "tipo", "activa")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class MacairaLoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Usuario/correo o contraseña incorrectos.",
        "inactive": "Usuario/correo o contraseña incorrectos.",
    }

    username = forms.CharField(
        label="Usuario o correo electrónico",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "Usuario o correo electrónico",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Contraseña"}
        ),
    )

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and "@" in username:
            matches = get_user_model().objects.filter(email__iexact=username)
            if matches.count() == 1:
                self.cleaned_data["username"] = matches.get().get_username()
        return super().clean()
