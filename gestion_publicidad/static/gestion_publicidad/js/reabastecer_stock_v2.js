document.addEventListener("DOMContentLoaded", function () {
    const formset = document.querySelector("#reabastecimiento-formset");
    const emptyFormTemplate = document.querySelector("#reabastecimiento-empty-form");
    const addButton = document.querySelector("#agregar-reabastecimiento");
    const totalForms = document.querySelector("#id_form-TOTAL_FORMS");

    if (!formset || !emptyFormTemplate || !addButton || !totalForms) return;

    let catalogo = [];
    let catalogoDisponible = false;

    function poblarTipos(fila, conservarSeleccion = true) {
        const insumoSelect = fila.querySelector('[id$="-insumo"]');
        const tipoSelect = fila.querySelector('[id$="-tipo_insumo"]');
        const tipoField = tipoSelect?.closest(".form-row");
        if (!insumoSelect || !tipoSelect || !tipoField) return;

        const seleccion = conservarSeleccion ? tipoSelect.value : "";
        const insumo = catalogo.find((item) => String(item.id) === insumoSelect.value);
        const tipos = insumo ? insumo.tipos : [];
        const tieneTipos = Boolean(insumo && insumo.tiene_tipos);

        tipoSelect.replaceChildren(new Option("- Select an option -", ""));
        tipos.forEach((tipo) => {
            const unidad = tipo.unidad_medida ? ` (${tipo.unidad_medida})` : "";
            tipoSelect.add(new Option(`${tipo.nombre}${unidad}`, String(tipo.id)));
        });

        tipoField.hidden = !tieneTipos;
        tipoSelect.required = tieneTipos;
        tipoSelect.disabled = !tieneTipos || tipos.length === 0;
        const ayuda = tipoField.querySelector(".help");
        if (ayuda) {
            ayuda.textContent = tieneTipos && tipos.length === 0
                ? "Registra primero un tipo de insumo para poder reabastecerlo."
                : "Selecciona una variante si el insumo maneja tipos.";
        }
        if (tipos.some((tipo) => String(tipo.id) === seleccion)) {
            tipoSelect.value = seleccion;
        }
    }

    function poblarInsumos(fila, conservarSeleccion = true) {
        const areaSelect = fila.querySelector('[id$="-area"]');
        const insumoSelect = fila.querySelector('[id$="-insumo"]');
        if (!areaSelect || !insumoSelect) return;

        const seleccion = conservarSeleccion ? insumoSelect.value : "";
        const insumos = catalogo.filter(
            (insumo) => String(insumo.area) === areaSelect.value,
        );
        insumoSelect.replaceChildren(new Option("- Select an option -", ""));
        insumos.forEach((insumo) => {
            insumoSelect.add(new Option(insumo.nombre, String(insumo.id)));
        });
        insumoSelect.disabled = !areaSelect.value;
        insumoSelect.value = insumos.some((insumo) => String(insumo.id) === seleccion)
            ? seleccion
            : "";
        poblarTipos(fila, conservarSeleccion);
    }

    function actualizarBotonesEliminar() {
        const filas = Array.from(formset.querySelectorAll(".reabastecimiento-item"));
        filas.forEach((fila) => {
            const boton = fila.querySelector(".remove-reabastecimiento");
            if (boton) boton.disabled = filas.length === 1;
        });
    }

    function reindexarFilas() {
        const filas = Array.from(formset.querySelectorAll(".reabastecimiento-item"));
        const prefijo = formset.dataset.formsetPrefix;
        const indiceAnterior = new RegExp(`^(id_)?${prefijo}-\\d+-`);

        filas.forEach((fila, index) => {
            fila.querySelectorAll("[name], [id], label[for]").forEach((elemento) => {
                ["name", "id", "for", "aria-describedby"].forEach((atributo) => {
                    const valor = elemento.getAttribute(atributo);
                    if (valor) {
                        elemento.setAttribute(
                            atributo,
                            valor.replace(indiceAnterior, `$1${prefijo}-${index}-`),
                        );
                    }
                });
            });
            const encabezado = fila.querySelector("h2");
            if (encabezado) encabezado.textContent = `Insumo ${index + 1}`;
        });
        totalForms.value = String(filas.length);
        actualizarBotonesEliminar();
    }

    function conectarFila(fila) {
        const areaSelect = fila.querySelector('[id$="-area"]');
        const insumoSelect = fila.querySelector('[id$="-insumo"]');
        if (!areaSelect || !insumoSelect) return;

        areaSelect.addEventListener("change", () => poblarInsumos(fila, false));
        insumoSelect.addEventListener("change", () => poblarTipos(fila, false));
        if (catalogoDisponible) poblarInsumos(fila, false);
    }

    function agregarFila() {
        const index = Number(totalForms.value);
        const fragmento = emptyFormTemplate.content.cloneNode(true);
        const fila = fragmento.querySelector(".reabastecimiento-item");
        const prefijoVacio = `${formset.dataset.formsetPrefix}-__prefix__-`;
        const prefijoNuevo = `${formset.dataset.formsetPrefix}-${index}-`;
        fila.querySelectorAll("*").forEach((elemento) => {
            ["name", "id", "for", "aria-describedby"].forEach((atributo) => {
                const valor = elemento.getAttribute(atributo);
                if (valor && valor.includes(prefijoVacio)) {
                    elemento.setAttribute(
                        atributo,
                        valor.replaceAll(prefijoVacio, prefijoNuevo),
                    );
                }
            });
        });
        formset.append(fila);
        totalForms.value = String(index + 1);
        conectarFila(fila);
        reindexarFilas();
    }

    addButton.addEventListener("click", agregarFila);
    formset.addEventListener("click", (evento) => {
        const boton = evento.target instanceof Element
            ? evento.target.closest(".remove-reabastecimiento")
            : null;
        if (!boton || boton.disabled) return;
        const filas = formset.querySelectorAll(".reabastecimiento-item");
        if (filas.length <= 1) return;
        boton.closest(".reabastecimiento-item").remove();
        reindexarFilas();
    });
    formset.querySelectorAll(".reabastecimiento-item").forEach(conectarFila);

    fetch("/api/insumos/")
        .then((response) => {
            if (!response.ok) throw new Error(`Error al cargar insumos (${response.status}).`);
            return response.json();
        })
        .then((data) => {
            catalogo = data.insumos || [];
            catalogoDisponible = true;
            formset.querySelectorAll(".reabastecimiento-item").forEach((fila) => {
                if (!fila.hidden) poblarInsumos(fila);
            });
        })
        .catch((error) => {
            console.error(error);
            formset.querySelectorAll(".reabastecimiento-item").forEach((fila) => {
                fila.querySelectorAll("select").forEach((select) => {
                    if (select.matches('[id$="-insumo"], [id$="-tipo_insumo"]')) {
                        select.disabled = true;
                    }
                });
            });
            const aviso = document.createElement("p");
            aviso.className = "errornote";
            aviso.textContent = "No se pudo cargar el catálogo de insumos. Recarga la página para intentarlo de nuevo.";
            formset.before(aviso);
        });

    actualizarBotonesEliminar();
});
