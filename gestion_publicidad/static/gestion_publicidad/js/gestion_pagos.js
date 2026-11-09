
document.addEventListener("DOMContentLoaded", function() {
    console.log("--> SCRIPT GESTIÓN DE PAGOS CARGADO <--");

    const tipoPagoSelect = document.querySelector("#id_tipo_pago");
    
    // Contenedores visuales
    const campoAbono = document.querySelector(".field-monto_abono");
    const campoMetodo = document.querySelector(".field-metodo_pago");
    const campoPlataforma = document.querySelector(".field-plataforma");
    const campoTipoCuenta = document.querySelector(".field-tipo_cuenta");
    
    // Elementos selectores e inputs numéricos
    const metodoPagoSelect = document.querySelector("#id_metodo_pago");
    const plataformaSelect = document.querySelector("#id_plataforma");
    const tipoCuentaSelect = document.querySelector("#id_tipo_cuenta");
    
    const inputAbono = document.querySelector("#id_monto_abono");
    const inputTotal = document.querySelector("#id_monto_total");

    function limitarCampoNumerico(input) {
        if (input.type !== "number") return;
        input.min = "0";
        if (input.value !== "" && Number(input.value) < 0) {
            input.value = "0";
        }
    }

    document.querySelectorAll('input[type="number"]').forEach(limitarCampoNumerico);
    document.addEventListener("input", function(evento) {
        if (evento.target instanceof HTMLInputElement) {
            limitarCampoNumerico(evento.target);
        }
    });

    const tipoMovimientoSelect = document.querySelector("#id_tipo");
    const categoriaEgresoField = document.querySelector(".field-categoria_egreso");
    const categoriaEgresoSelect = document.querySelector("#id_categoria_egreso");
    const empleadoEgresoField = document.querySelector(".field-empleado");
    const empleadoEgresoSelect = document.querySelector("#id_empleado");
    const trabajoMovimientoField = document.querySelector(".field-trabajo");
    const trabajoMovimientoSelect = document.querySelector("#id_trabajo");

    function actualizarFormularioMovimiento() {
        if (!tipoMovimientoSelect) return;
        const esEgreso = tipoMovimientoSelect.value === "EGRESO";
        const esPagoEmpleado = esEgreso
            && categoriaEgresoSelect
            && categoriaEgresoSelect.value === "PAGO_EMPLEADOS";

        if (categoriaEgresoField) categoriaEgresoField.style.display = esEgreso ? "" : "none";
        if (empleadoEgresoField) empleadoEgresoField.style.display = esPagoEmpleado ? "" : "none";
        if (trabajoMovimientoField) trabajoMovimientoField.style.display = esEgreso ? "none" : "";

        if (esEgreso) {
            if (trabajoMovimientoSelect) trabajoMovimientoSelect.value = "";
        } else if (categoriaEgresoSelect) {
            categoriaEgresoSelect.value = "";
        }

        if (!esPagoEmpleado && empleadoEgresoSelect) {
            empleadoEgresoSelect.value = "";
        }
    }

    if (tipoMovimientoSelect) {
        tipoMovimientoSelect.addEventListener("change", actualizarFormularioMovimiento);
        if (categoriaEgresoSelect) {
            categoriaEgresoSelect.addEventListener("change", actualizarFormularioMovimiento);
        }
        actualizarFormularioMovimiento();
    }

    function actualizarFormulario() {
        if (!tipoPagoSelect) return;
        const tipoPago = tipoPagoSelect.value;
        const metodo = metodoPagoSelect ? metodoPagoSelect.value : "";

        // 1. Si no hay pago inicial seleccionado ("" o "NADA")
        if (tipoPago === "" || tipoPago === "NADA") {
            if (campoAbono) campoAbono.style.display = "none";
            if (campoMetodo) campoMetodo.style.display = "none";
            if (campoPlataforma) campoPlataforma.style.display = "none";
            if (campoTipoCuenta) campoTipoCuenta.style.display = "none";
            return;
        }

        // 2. Si se registra Pago Total o Abono
        if (campoMetodo) campoMetodo.style.display = "block";
        if (campoAbono) {
            campoAbono.style.display = (tipoPago === "ABONO") ? "block" : "none";
        }

        // 3. Reglas específicas según el Método de Pago seleccionado
        if (metodo === "EFECTIVO_USD") {
            if (campoPlataforma) campoPlataforma.style.display = "none";
            if (campoTipoCuenta) campoTipoCuenta.style.display = "none";
            
            if (plataformaSelect) {
                plataformaSelect.value = "";
                plataformaSelect.disabled = false;
            }
            if (tipoCuentaSelect) {
                tipoCuentaSelect.value = "";
                tipoCuentaSelect.disabled = false;
            }
        } 
        else if (metodo === "PAGO_MOVIL" || metodo === "TARJETA") {
            if (campoPlataforma) campoPlataforma.style.display = "block";
            if (campoTipoCuenta) campoTipoCuenta.style.display = "none";
            
            if (plataformaSelect) plataformaSelect.disabled = false;
            if (tipoCuentaSelect) {
                tipoCuentaSelect.value = "VES";
                tipoCuentaSelect.disabled = false;
            }
        } 
        else {
            if (campoPlataforma) campoPlataforma.style.display = "block";
            if (campoTipoCuenta) campoTipoCuenta.style.display = "block";
            
            if (plataformaSelect) plataformaSelect.disabled = false;
            if (tipoCuentaSelect) tipoCuentaSelect.disabled = false;
        }
    }

    if (tipoPagoSelect) {
        tipoPagoSelect.addEventListener("change", actualizarFormulario);
    }

    if (metodoPagoSelect) {
        metodoPagoSelect.addEventListener("change", actualizarFormulario);
    }

    // ============================================================
    // Lógica de selects dependientes: Área -> Insumo -> Tipo (inline de Trabajo)
    // ============================================================
    const CAMPOS_INSUMO = {
        area: 'select[name$="-area"]',
        insumo: 'select[name$="-insumo"]',
        tipo: 'select[name$="-tipo_insumo"]'
    };

    async function cargarCatalogoInsumos() {
        try {
            const respuesta = await fetch("/api/insumos/");
            if (!respuesta.ok) {
                throw new Error("No se pudo cargar el catálogo de insumos: " + respuesta.status);
            }
            const data = await respuesta.json();
            window.catalogoInsumos = data.insumos || [];
        } catch (error) {
            console.error(error);
            window.catalogoInsumos = [];
        }
    }

    function poblarInsumosDeArea(fila) {
        const insumoSelect = fila.querySelector(CAMPOS_INSUMO.insumo);
        const areaSelect = fila.querySelector(CAMPOS_INSUMO.area);
        if (!insumoSelect) return;

        const areaId = areaSelect ? areaSelect.value : "";
        const selectedInsumoId = insumoSelect.value;
        const insumos = (window.catalogoInsumos || []).filter((insumo) =>
            areaId && String(insumo.area) === String(areaId)
        );

        insumoSelect.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "- Select an option -";
        insumoSelect.appendChild(placeholder);

        insumos.forEach((insumo) => {
            const option = document.createElement("option");
            option.value = String(insumo.id);
            option.textContent = insumo.nombre;
            insumoSelect.appendChild(option);
        });

        insumoSelect.disabled = !areaId;
        if (insumos.some((insumo) => String(insumo.id) === String(selectedInsumoId))) {
            insumoSelect.value = selectedInsumoId;
        } else {
            insumoSelect.value = "";
        }
    }

    function actualizarColumnaInline(contenedor, campo, visible) {
        const tabla = contenedor.closest("table") || contenedor;
        const filas = Array.from(tabla.querySelectorAll("tr.form-row"));
        const primeraFila = filas.find((fila) => !fila.classList.contains("empty-form")) || filas[0];
        const celda = primeraFila && primeraFila.querySelector(`td.field-${campo}`);
        if (!celda) return;

        const indice = Array.from(celda.parentElement.children).indexOf(celda);
        const encabezado = tabla.querySelector("thead tr")?.children[indice];
        if (encabezado) encabezado.style.display = visible ? "" : "none";

        filas.forEach((fila) => {
            const celdaFila = fila.querySelector(`td.field-${campo}`);
            if (celdaFila) celdaFila.style.display = visible ? "" : "none";
        });
    }

    function actualizarColumnaArea(contenedor) {
        const tabla = contenedor.closest("table") || contenedor;
        const fila = tabla.querySelector("tr.form-row:not(.empty-form)") || tabla.querySelector("tr.form-row");
        const areaSelect = fila && fila.querySelector(CAMPOS_INSUMO.area);
        const opcionesArea = areaSelect
            ? Array.from(areaSelect.options).filter((opcion) => opcion.value)
            : [];
        actualizarColumnaInline(contenedor, "area", opcionesArea.length > 1);
    }

    function actualizarColumnaTipo(contenedor) {
        const tabla = contenedor.closest("table") || contenedor;
        const filas = Array.from(tabla.querySelectorAll("tr.form-row:not(.empty-form)"));
        const tieneTiposVisible = filas.some((fila) => {
            const eliminado = fila.querySelector('input[name$="-DELETE"]');
            return fila.dataset.tieneTipos === "true" && !(eliminado && eliminado.checked);
        });
        actualizarColumnaInline(contenedor, "tipo_insumo", tieneTiposVisible);
    }

    function poblarTipoDeInsumo(fila) {
        const tipoSelect = fila.querySelector(CAMPOS_INSUMO.tipo);
        const insumoSelect = fila.querySelector(CAMPOS_INSUMO.insumo);
        if (!tipoSelect) return;

        const insumoId = insumoSelect ? insumoSelect.value : "";
        const insumo = (window.catalogoInsumos || []).find((i) => String(i.id) === String(insumoId));
        const valorAnterior = tipoSelect.value;
        const controlTipo = tipoSelect.closest(".related-widget-wrapper") || tipoSelect;

        tipoSelect.innerHTML = "";

        if (!insumo || !insumo.tipos || insumo.tipos.length === 0) {
            tipoSelect.disabled = true;
            tipoSelect.required = false;
            fila.dataset.tieneTipos = "false";
            const celdaTipo = tipoSelect.closest("td");
            if (celdaTipo) celdaTipo.style.display = "none";
            else controlTipo.style.display = "none";
            actualizarColumnaTipo(fila.closest("table"));
            return;
        }

        fila.dataset.tieneTipos = "true";
        const celdaTipo = tipoSelect.closest("td");
        if (celdaTipo) celdaTipo.style.display = "";
        else controlTipo.style.display = "";
        tipoSelect.disabled = false;
        tipoSelect.required = true;
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "- Select an option -";
        tipoSelect.appendChild(placeholder);

        insumo.tipos.forEach((tipo) => {
            const option = document.createElement("option");
            option.value = String(tipo.id);
            option.textContent = tipo.nombre + (tipo.unidad_medida ? " (" + tipo.unidad_medida + ")" : "");
            tipoSelect.appendChild(option);
        });

        // Conservar la selección anterior si el nuevo insumo sigue teniendo ese tipo
        if (valorAnterior) {
            const opcionExistente = Array.from(tipoSelect.options).find((o) => String(o.value) === String(valorAnterior));
            if (opcionExistente) {
                tipoSelect.value = opcionExistente.value;
            }
        }
        actualizarColumnaTipo(fila.closest("table"));
    }

    function configurarFilasInsumo() {
        const contenedores = [
            document.getElementById("insumos_utilizados-group"),
            document.getElementById("materiales_utilizados-group")
        ].filter(Boolean);
        if (contenedores.length === 0) return;

        contenedores.forEach((contenedor) => {
            contenedor.addEventListener("change", function (evento) {
                const fila = evento.target.closest("tr.form-row");
                if (!fila) return;

                const areaSelect = fila.querySelector(CAMPOS_INSUMO.area);
                const insumoSelect = fila.querySelector(CAMPOS_INSUMO.insumo);

                if (evento.target === areaSelect) {
                    poblarInsumosDeArea(fila);
                    poblarTipoDeInsumo(fila);
                    actualizarColumnaArea(fila.closest("table"));
                } else if (evento.target === insumoSelect) {
                    poblarTipoDeInsumo(fila);
                }
            });
        });

        document.addEventListener("formset:added", function (evento) {
            const fila = evento.target.closest("tr.form-row");
            if (!fila || !contenedores.some((contenedor) => contenedor.contains(fila))) return;
            poblarInsumosDeArea(fila);
            poblarTipoDeInsumo(fila);
            actualizarColumnaArea(fila.closest("table"));
        });
    }

    async function inicializarDependenciasInsumos() {
        await cargarCatalogoInsumos();
        const contenedores = [
            document.getElementById("insumos_utilizados-group"),
            document.getElementById("materiales_utilizados-group")
        ].filter(Boolean);
        contenedores.forEach((contenedor) => {
            const filas = contenedor.querySelectorAll("tr.form-row");
            filas.forEach((fila) => {
                poblarInsumosDeArea(fila);
                poblarTipoDeInsumo(fila);
            });
            actualizarColumnaArea(contenedor);
            actualizarColumnaTipo(contenedor);
        });
    }

    // Ejecutar al cargar la página por si hay valores preseleccionados
    actualizarFormulario();

    // Inicializar los selects dependientes: Área -> Insumo -> Tipo
    configurarFilasInsumo();
    inicializarDependenciasInsumos();
});