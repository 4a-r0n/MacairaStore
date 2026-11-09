from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import F, Q
from django.conf import settings
from django.utils import timezone
# Create your models here.

DEFAULT_EMPLOYEE_PERMISSION_CODENAMES = tuple(
    f"{action}_{model}"
    for model in (
        "areainsumo",
        "insumo",
        "tipoinsumo",
        "trabajo",
        "trabajoinsumo",
        "trabajodia",
        "tareatrabajodia",
    )
    for action in ("view", "add", "change")
) + ("view_movimientofinanciero", "add_movimientofinanciero")


class AreaInsumo(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Área")

    class Meta:
        verbose_name = "Área de Insumo"
        verbose_name_plural = "Áreas de Insumos"

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    area = models.ForeignKey(AreaInsumo, on_delete=models.CASCADE, related_name="insumos", verbose_name="Área", null=True, blank=True)
    nombre = models.CharField(max_length=150, unique=True, verbose_name="Insumo")
    tiene_tipos = models.BooleanField(default=False, verbose_name="Tiene Tipos de Insumo", help_text="Si se activa, se pueden registrar tipos/variantes para este insumo.")
    cantidad_disponible = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)], verbose_name="Cantidad disponible")
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=20.00, validators=[MinValueValidator(0)], verbose_name="Stock mínimo")
    unidad_medida = models.CharField(max_length=50, default="unidades", verbose_name="Unidad de medida", help_text="Ej: Metros, Unidades, Litros")

    class Meta:
        verbose_name = "Insumo"
        verbose_name_plural = "Insumos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad_disponible__gte=0),
                name="insumo_cantidad_no_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(stock_minimo__gte=0),
                name="insumo_minimo_no_negativo",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.area_id is None:
            self.area, _ = AreaInsumo.objects.get_or_create(nombre="Sin área")
        super().save(*args, **kwargs)

    def __str__(self):
        if self.area:
            return f"{self.area.nombre} > {self.nombre}"
        return f"[Sin Área] > {self.nombre}"

    @property
    def estado_stock(self):
        return obtener_estado_stock(self.cantidad_disponible, self.stock_minimo)


class TipoInsumo(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE, related_name="tipos", verbose_name="Insumo")
    nombre = models.CharField(max_length=150, verbose_name="Tipo / Variante")
    unidad_medida = models.CharField(max_length=50, help_text="Ej: Metros, Unidades, Litros", verbose_name="Unidad de medida")
    cantidad_disponible = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)], verbose_name="Cantidad disponible")
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=20.00, validators=[MinValueValidator(0)], verbose_name="Stock mínimo")

    class Meta:
        verbose_name = "Tipo de Insumo"
        verbose_name_plural = "Tipos de Insumos"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad_disponible__gte=0),
                name="tipo_insumo_cantidad_no_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(stock_minimo__gte=0),
                name="tipo_insumo_minimo_no_negativo",
            ),
        ]

    @property
    def estado_stock(self):
        return obtener_estado_stock(self.cantidad_disponible, self.stock_minimo)

    def __str__(self):
        return f"{self.insumo.nombre} - {self.nombre} ({self.cantidad_disponible} {self.unidad_medida})"


def obtener_estado_stock(cantidad, stock_minimo=20):
    if cantidad <= 0:
        return "Agotado"
    if cantidad <= stock_minimo:
        return "Crítico"
    if cantidad <= stock_minimo + 10:
        return "Poco stock"
    return "Óptimo"


def actualizar_stock_consumido(stock, cantidad, stock_anterior=None, cantidad_anterior=0):
    referencias = {
        (stock._meta.label_lower, stock.pk): stock,
    }
    if stock_anterior:
        referencias[(stock_anterior._meta.label_lower, stock_anterior.pk)] = stock_anterior

    bloqueados = {}
    for referencia in sorted(referencias):
        objeto = referencias[referencia]
        bloqueados[referencia] = type(objeto).objects.select_for_update().get(pk=objeto.pk)

    referencia_actual = (stock._meta.label_lower, stock.pk)
    referencia_anterior = (
        (stock_anterior._meta.label_lower, stock_anterior.pk)
        if stock_anterior else None
    )
    stock_actual = bloqueados[referencia_actual]
    misma_existencia = referencia_actual == referencia_anterior
    disponible = stock_actual.cantidad_disponible
    if misma_existencia:
        disponible += cantidad_anterior

    if disponible < cantidad:
        raise ValueError(
            f"Stock insuficiente de {stock_actual}. Disponible: {disponible}"
        )

    stock_actual.cantidad_disponible = disponible - cantidad
    stock_actual.save(update_fields=('cantidad_disponible',))

    if referencia_anterior and not misma_existencia:
        stock_anterior_bloqueado = bloqueados[referencia_anterior]
        stock_anterior_bloqueado.cantidad_disponible += cantidad_anterior
        stock_anterior_bloqueado.save(update_fields=('cantidad_disponible',))


def restaurar_stock_consumido(stock, cantidad):
    with transaction.atomic():
        stock_bloqueado = type(stock).objects.select_for_update().get(pk=stock.pk)
        stock_bloqueado.cantidad_disponible += cantidad
        stock_bloqueado.save(update_fields=('cantidad_disponible',))


class Trabajo(models.Model):
    cliente = models.CharField(max_length=150)
    descripcion = models.TextField()
    monto_total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2, editable=False, validators=[MinValueValidator(0)])
    
    TIPO_PAGO_CHOICES = [
        ('NADA', 'No registrar pago por ahora'),
        ('TOTAL', 'Pagar el Total del Trabajo'),
        ('ABONO', 'Dar Abono Inicial'),
    ]
    tipo_pago = models.CharField(max_length=10, choices=TIPO_PAGO_CHOICES, default='NADA', verbose_name='Tipo de Pago', blank=True, null=True)
    monto_abono = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)], verbose_name='Monto del Abono', blank=True, null=True)
    
    METODO_PAGO_CHOICES = [
        ('EFECTIVO_USD', 'Efectivo USD'),
        ('PAGO_MOVIL', 'Pago Móvil'),
        ('TRANSFERENCIA', 'Transferencia USD/USDT'),
        ('TARJETA', 'Tarjeta'),
    ]
    metodo_pago = models.CharField(max_length=30, choices=METODO_PAGO_CHOICES, verbose_name='Método de pago', blank=True, null=True)

    PLATAFORMA_CHOICES = [
        ('NINGUNA', 'N/A'),
        ('BANCO_NACIONAL', 'Banco nacional'),
        ('BANCO_INTERNACIONAL', 'Banco internacional'),
        ('PAYPAL', 'PayPal'),
        ('ZELLE', 'Zelle'),
        ('BINANCE', 'Binance'),
        ('OTRO', 'Otro'),
    ]
    plataforma = models.CharField(max_length=30, choices=PLATAFORMA_CHOICES, verbose_name='Plataforma', default='NINGUNA', blank=True, null=True)

    TIPO_CUENTA_CHOICES = [
        ('USD', 'USD'),
        ('EUR', 'EUR'),
        ('USDT', 'USDT'),
        ('VES', 'Bolívares (VES)'),
    ]
    tipo_cuenta = models.CharField(max_length=20, choices=TIPO_CUENTA_CHOICES, verbose_name='Tipo de cuenta', default='USD', blank=True, null=True)

    estado = models.CharField(
        max_length=20,
        choices=[
            ('PENDIENTE', 'Pendiente'), 
            ('EN_PROCESO', 'En Proceso'), 
            ('FINALIZADO', 'Finalizado'), 
            ('CANCELADO', 'Cancelado')
        ],
        default='PENDIENTE'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_limite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha límite de entrega",
    )
    entregado = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="Entregado",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(monto_total__gte=0),
                name="trabajo_monto_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(saldo_pendiente__gte=0),
                name="trabajo_saldo_no_negativo",
            ),
            models.CheckConstraint(
                condition=Q(monto_abono__isnull=True) | Q(monto_abono__gte=0),
                name="trabajo_abono_no_negativo",
            ),
            models.CheckConstraint(
                condition=~Q(tipo_pago='ABONO') | Q(monto_abono__lte=F('monto_total')),
                name="trabajo_abono_no_supera_total",
            ),
        ]

    @property
    def estado_entrega(self):
        if self.entregado:
            return "Entregado"
        if not self.fecha_limite:
            return "Sin fecha"

        dias_restantes = (self.fecha_limite - timezone.localdate()).days
        if dias_restantes < 0:
            return "Expirado"
        if dias_restantes <= 2:
            return "Fecha límite"
        if dias_restantes <= 4:
            return "Poco tiempo"
        return "A tiempo"

    def save(self, *args, **kwargs):
        es_nuevo = not self.pk
        
        if es_nuevo:
            if self.tipo_pago == 'TOTAL':
                self.saldo_pendiente = 0.00
                monto_a_registrar = self.monto_total
            elif self.tipo_pago == 'ABONO':
                abono = self.monto_abono if self.monto_abono else 0.00
                self.saldo_pendiente = self.monto_total - abono
                monto_a_registrar = abono
            else:
                self.saldo_pendiente = self.monto_total
                monto_a_registrar = 0.00

        if self.estado == "FINALIZADO":
            self.entregado = True
            self.fecha_limite = None
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "entregado",
                    "fecha_limite",
                }

        super().save(*args, **kwargs)

        if es_nuevo and self.tipo_pago != 'NADA' and monto_a_registrar > 0:
            movimiento = MovimientoFinanciero.objects.create(
                tipo='INGRESO',
                monto=monto_a_registrar,
                metodo_pago=self.metodo_pago,
                plataforma=self.plataforma,
                tipo_cuenta=self.tipo_cuenta,
                descripcion=f"Pago inicial por Trabajo #{self.id} - {self.cliente}",
                trabajo=self
            )
            from Gestion_Finanzas.models import CategoriaFinanciera

            categoria, _ = CategoriaFinanciera.objects.get_or_create(
                nombre="Abonos de clientes",
                defaults={"tipo": "INCOME", "activa": True},
            )
            metadata = movimiento.detalle_financiero
            metadata.categoria = categoria
            metadata.save(update_fields=("categoria",))

    def __str__(self):
        return f"Trabajo #{self.id} - {self.cliente}"


class TrabajoPorCobrarManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            estado='FINALIZADO',
            saldo_pendiente__gt=0,
        )


class TrabajoPorCobrar(Trabajo):
    objects = TrabajoPorCobrarManager()

    class Meta:
        proxy = True
        default_permissions = ()
        verbose_name = "Trabajo por cobrar"
        verbose_name_plural = "Trabajos por cobrar"


class TrabajoInsumo(models.Model):
    trabajo = models.ForeignKey(Trabajo, on_delete=models.CASCADE, related_name='insumos_utilizados')
    jornada = models.ForeignKey(
        "TrabajoDia",
        on_delete=models.PROTECT,
        related_name="materiales_utilizados",
        null=True,
        blank=True,
        verbose_name="Jornada",
    )
    area = models.ForeignKey(AreaInsumo, on_delete=models.PROTECT, verbose_name="Área", null=True, blank=True)
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, verbose_name="Insumo", null=True, blank=True)
    tipo_insumo = models.ForeignKey(TipoInsumo, on_delete=models.PROTECT, verbose_name="Tipo de Insumo", null=True, blank=True)
    cantidad_utilizada = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    fecha_consumo = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.jornada_id:
            if self.trabajo_id and self.trabajo_id != self.jornada.trabajo_id:
                raise ValueError("La jornada seleccionada pertenece a otro trabajo.")
            self.trabajo_id = self.jornada.trabajo_id

        if not self.insumo_id:
            raise ValueError("Debes seleccionar un insumo válido.")
        if not self.area_id:
            raise ValueError("Debes seleccionar un área para el insumo.")
        if self.insumo.area_id != self.area_id:
            raise ValueError("El insumo seleccionado no pertenece al área elegida.")

        if self.tipo_insumo_id:
            if self.tipo_insumo.insumo_id != self.insumo_id:
                raise ValueError("El tipo de insumo seleccionado no corresponde al insumo elegido.")
            stock = self.tipo_insumo
        elif self.insumo.tiene_tipos or self.insumo.tipos.exists():
            raise ValueError("Debes seleccionar un tipo de insumo para el insumo elegido.")
        else:
            stock = self.insumo

        if stock is None:
            raise ValueError("Debes seleccionar un insumo válido.")

        with transaction.atomic():
            trabajo_existente = None
            stock_anterior = None
            if self.pk:
                trabajo_existente = (
                    type(self).objects.select_related('insumo', 'tipo_insumo').get(pk=self.pk)
                )
                stock_anterior = trabajo_existente.tipo_insumo or trabajo_existente.insumo

            cantidad_anterior = trabajo_existente.cantidad_utilizada if trabajo_existente else 0
            actualizar_stock_consumido(
                stock,
                self.cantidad_utilizada,
                stock_anterior,
                cantidad_anterior,
            )

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            trabajo_existente = (
                type(self).objects.select_related('insumo', 'tipo_insumo').get(pk=self.pk)
            )
            stock = trabajo_existente.tipo_insumo or trabajo_existente.insumo
            if stock:
                restaurar_stock_consumido(stock, trabajo_existente.cantidad_utilizada)
            return super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Insumo del Trabajo"
        verbose_name_plural = "Insumos del Trabajo"
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad_utilizada__gte=0),
                name="trabajo_insumo_cantidad_no_negativa",
            ),
        ]

    def __str__(self):
        nombre = self.tipo_insumo.nombre if self.tipo_insumo else (self.insumo.nombre if self.insumo else "Insumo sin definir")
        return f"{self.cantidad_utilizada} de {nombre} para Trabajo #{self.trabajo.id}"


class TrabajoDia(models.Model):
    trabajo = models.ForeignKey(
        Trabajo,
        on_delete=models.PROTECT,
        related_name="jornadas",
        verbose_name="Trabajo",
    )
    fecha = models.DateField(verbose_name="Fecha de trabajo")
    notas = models.TextField(blank=True, verbose_name="Notas del día")

    class Meta:
        ordering = ("fecha", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("trabajo", "fecha"),
                name="jornada_unica_por_trabajo_fecha",
            ),
        ]
        verbose_name = "Jornada de trabajo"
        verbose_name_plural = "Jornadas de trabajo"

    def __str__(self):
        return f"{self.trabajo} - {self.fecha}"


class TareaTrabajoDia(models.Model):
    jornada = models.ForeignKey(
        TrabajoDia,
        on_delete=models.CASCADE,
        related_name="tareas",
        verbose_name="Jornada",
    )
    descripcion = models.CharField(max_length=250, verbose_name="Tarea")
    completada = models.BooleanField(default=False, verbose_name="Terminada")
    completada_en = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Terminada el",
    )

    class Meta:
        ordering = ("id",)
        verbose_name = "Tarea del día"
        verbose_name_plural = "Tareas del día"

    def save(self, *args, **kwargs):
        if self.completada:
            if self.pk:
                estado_anterior = type(self).objects.filter(pk=self.pk).values(
                    "completada", "completada_en"
                ).first()
            else:
                estado_anterior = None
            if not estado_anterior or not estado_anterior["completada"]:
                self.completada_en = timezone.now()
            elif estado_anterior["completada_en"]:
                self.completada_en = estado_anterior["completada_en"]
        else:
            self.completada_en = None

        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"completada_en"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.descripcion


class MovimientoFinanciero(models.Model):
    TIPO_CHOICES = [
        ('INGRESO', 'Ingreso'),
        ('EGRESO', 'Egreso'),
    ]
    
    METODO_PAGO_CHOICES = [
        ('EFECTIVO_USD', 'Efectivo USD'),
        ('PAGO_MOVIL', 'Pago Móvil'),
        ('TRANSFERENCIA', 'Transferencia USD/USDT'),
        ('TARJETA', 'Tarjeta'),
    ]

    PLATAFORMA_CHOICES = [
        ('NINGUNA', 'N/A'),
        ('BANCO_NACIONAL', 'Banco nacional'),
        ('BANCO_INTERNACIONAL', 'Banco internacional'),
        ('PAYPAL', 'PayPal'),
        ('ZELLE', 'Zelle'),
        ('BINANCE', 'Binance'),
        ('OTRO', 'Otro'),
    ]

    TIPO_CUENTA_CHOICES = [
        ('USD', 'USD'),
        ('EUR', 'EUR'),
        ('USDT', 'USDT'),
        ('VES', 'Bolívares (VES)'),
    ]

    CATEGORIA_EGRESO_CHOICES = [
        ('COMPRA_MATERIAL', 'Compra de material'),
        ('PAGO_EMPLEADOS', 'Pago a empleados'),
        ('REEMBOLSO_CLIENTE', 'Reembolso a cliente'),
    ]

    TIPO_INGRESO_CHOICES = [
        ('ABONO_CLIENTES', 'Abono de clientes'),
        ('OTROS_INGRESOS', 'Otros ingresos'),
    ]

    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='INGRESO')
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tipo_ingreso = models.CharField(
        max_length=30,
        choices=TIPO_INGRESO_CHOICES,
        blank=True,
        null=True,
        verbose_name="Tipo de ingreso",
    )
    categoria_egreso = models.CharField(max_length=30, choices=CATEGORIA_EGRESO_CHOICES, blank=True, verbose_name="Tipo de egreso")
    metodo_pago = models.CharField(
        max_length=30,
        choices=METODO_PAGO_CHOICES,
        verbose_name="Método de pago",
    )
    plataforma = models.CharField(max_length=30, choices=PLATAFORMA_CHOICES, blank=True, null=True)
    tipo_cuenta = models.CharField(max_length=20, choices=TIPO_CUENTA_CHOICES, verbose_name="Tipo de cuenta", blank=True, null=True)
    descripcion = models.TextField(default="Sin descripción")
    trabajo = models.ForeignKey('Trabajo', on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos')
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pagos_empleado", verbose_name="Empleado")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(monto__gte=0),
                name="movimiento_monto_no_negativo",
            ),
        ]

    def clean(self):
        super().clean()
        if self.metodo_pago == "EFECTIVO_USD":
            self.tipo_cuenta = None
            self.plataforma = None
        elif self.metodo_pago == "PAGO_MOVIL":
            self.tipo_cuenta = "VES"
            self.plataforma = "BANCO_NACIONAL"
        if self.tipo == 'EGRESO':
            if self.metodo_pago == "TARJETA":
                raise ValidationError({
                    "metodo_pago": "Tarjeta no está disponible para egresos.",
                })
            if not self.categoria_egreso:
                raise ValidationError({
                    'categoria_egreso': "Selecciona la categoría del egreso.",
                })
            if self.categoria_egreso == "PAGO_EMPLEADOS" and not self.empleado_id:
                raise ValidationError({
                    'empleado': "Selecciona el empleado al que se realizará el pago.",
                })
            if self.categoria_egreso == "PAGO_EMPLEADOS" and (
                not self.empleado.is_active
                or self.empleado.is_superuser
                or not self.empleado.groups.filter(name="Empleado").exists()
            ):
                raise ValidationError({
                    'empleado': "Solo se pueden registrar pagos a usuarios activos del grupo Empleado.",
                })
            if self.categoria_egreso != "PAGO_EMPLEADOS":
                self.empleado = None
            if self.categoria_egreso != "REEMBOLSO_CLIENTE":
                self.trabajo = None
            self.tipo_ingreso = None
        else:
            self.categoria_egreso = ""
            self.empleado = None

    def __str__(self):
        return f"{self.tipo} - ${self.monto} ({self.get_metodo_pago_display()} - {self.tipo_cuenta})"