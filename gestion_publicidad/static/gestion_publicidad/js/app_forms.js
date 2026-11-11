(() => {
  const jobPaymentType = document.querySelector("[data-job-payment-type]");
  const movementType = document.querySelector("[data-movement-type]");
  const personalRole = document.querySelector('[name="role"]');

  function toggleField(form, name, hidden) {
    const field = form.querySelector(`[data-field="${name}"]`);
    if (field) {
      field.hidden = hidden;
      field.style.display = hidden ? "none" : "";
    }
  }

  function updateJobPaymentFields() {
    if (!jobPaymentType) return;
    const form = jobPaymentType.closest("form");
    const paymentType = jobPaymentType.value;
    const noPayment = paymentType === "NADA" || !paymentType;
    const paymentMethod = form.querySelector('[name="metodo_pago"]');
    const cashPayment = paymentMethod?.value === "EFECTIVO_USD";

    toggleField(form, "monto_abono", noPayment || paymentType === "TOTAL");
    toggleField(form, "metodo_pago", noPayment);
    toggleField(form, "plataforma", noPayment || cashPayment);
    toggleField(form, "tipo_cuenta", noPayment || cashPayment);

    if (paymentMethod?.value === "PAGO_MOVIL") {
      const platform = form.querySelector('[name="plataforma"]');
      const accountType = form.querySelector('[name="tipo_cuenta"]');
      if (platform) platform.value = "BANCO_NACIONAL";
      if (accountType) accountType.value = "VES";
    }
  }

  function setCategoryFromMovementType(form, type, subType) {
    const categorySelect = form.querySelector('[name="categoria_financiera"]');
    if (!categorySelect) return;
    const expectedKind = type === "INGRESO" ? "INCOME" : "EXPENSE";
    [...categorySelect.options].forEach((option) => {
      const optionKind = option.dataset.categoryKind;
      option.hidden = Boolean(option.value) && optionKind !== expectedKind && optionKind !== "BOTH";
    });

    const attribute = type === "INGRESO" ? "incomeCategory" : "expenseCategory";
    const targetName = type === "INGRESO"
      ? (subType === "ABONO_CLIENTES" ? "Abonos de clientes" : "Otros ingresos")
      : ({
          COMPRA_MATERIAL: "Materiales e insumos",
          PAGO_EMPLEADOS: "Pago a empleados",
          REEMBOLSO_CLIENTE: "Reembolsos",
        }[subType] || "");
    const matchingOption = [...categorySelect.options].find(
      (option) => option.dataset[attribute] === targetName,
    );
    if (matchingOption) categorySelect.value = matchingOption.value;
  }

  function updateMovementFields() {
    if (!movementType) return;
    const form = movementType.closest("form");
    const type = movementType.value;
    const incomeType = form.querySelector('[name="tipo_ingreso"]');
    const expenseType = form.querySelector('[name="categoria_egreso"]');
    const paymentMethod = form.querySelector('[name="metodo_pago"]');
    const incomeSubType = incomeType?.value || "";
    const expenseSubType = expenseType?.value || "";
    const isIncome = type === "INGRESO";

    if (incomeType) incomeType.required = isIncome;
    if (expenseType) expenseType.required = !isIncome;
    const employeeSelect = form.querySelector('[name="empleado"]');
    if (employeeSelect) {
      employeeSelect.required = !isIncome && expenseSubType === "PAGO_EMPLEADOS";
    }
    const cardOption = paymentMethod?.querySelector('option[value="TARJETA"]');
    if (cardOption) {
      cardOption.hidden = !isIncome;
      cardOption.disabled = !isIncome;
      if (!isIncome && paymentMethod.value === "TARJETA") paymentMethod.value = "";
    }
    toggleField(form, "tipo_ingreso", !isIncome);
    toggleField(form, "categoria_egreso", isIncome);
    toggleField(form, "empleado", isIncome || expenseSubType !== "PAGO_EMPLEADOS");
    toggleField(
      form,
      "trabajo",
      isIncome ? incomeSubType === "OTROS_INGRESOS" : expenseSubType !== "REEMBOLSO_CLIENTE",
    );
    setCategoryFromMovementType(form, type, isIncome ? incomeSubType : expenseSubType);

    const cashPayment = paymentMethod?.value === "EFECTIVO_USD";
    toggleField(form, "plataforma", cashPayment);
    toggleField(form, "tipo_cuenta", cashPayment);
    if (paymentMethod?.value === "PAGO_MOVIL") {
      const platform = form.querySelector('[name="plataforma"]');
      const accountType = form.querySelector('[name="tipo_cuenta"]');
      if (platform) platform.value = "BANCO_NACIONAL";
      if (accountType) accountType.value = "VES";
    }
  }

  if (jobPaymentType) {
    const jobForm = jobPaymentType.closest("form");
    jobPaymentType.addEventListener("change", updateJobPaymentFields);
    const jobPaymentMethod = jobForm?.querySelector('[name="metodo_pago"]');
    if (jobPaymentMethod) {
      jobPaymentMethod.addEventListener("change", updateJobPaymentFields);
    }
    updateJobPaymentFields();
  }
  if (movementType) {
    movementType.addEventListener("change", updateMovementFields);
    ["tipo_ingreso", "categoria_egreso", "metodo_pago"].forEach((name) => {
      const field = movementType.closest("form").querySelector(`[name="${name}"]`);
      if (field) field.addEventListener("change", updateMovementFields);
    });
    updateMovementFields();
  }

  if (personalRole) {
    const permissionsField = personalRole.closest("form").querySelector('[data-field="permissions"]');
    const updatePersonalPermissions = () => {
      if (permissionsField) permissionsField.hidden = personalRole.value !== "Empleado";
    };
    personalRole.addEventListener("change", updatePersonalPermissions);
    updatePersonalPermissions();
  }

  function syncTaskDelete(card) {
    if (!card) return;
    const checkbox = card.querySelector('input[type="checkbox"][name$="-DELETE"]');
    const button = card.querySelector("[data-task-delete]");
    if (!checkbox || !button) return;
    const deleted = checkbox.checked;
    card.classList.toggle("is-deleted", deleted);
    button.setAttribute("aria-pressed", deleted ? "true" : "false");
    button.textContent = deleted ? "Deshacer" : "Eliminar";
  }

  document.querySelectorAll("[data-task-form]").forEach(syncTaskDelete);
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-task-delete]");
    if (!button) return;
    const card = button.closest("[data-task-form]");
    const checkbox = card?.querySelector('input[type="checkbox"][name$="-DELETE"]');
    if (!card || !checkbox) return;
    checkbox.checked = !checkbox.checked;
    syncTaskDelete(card);
  });

  document.querySelectorAll("[data-add-formset]").forEach((button) => {
    button.addEventListener("click", () => {
      const prefix = button.dataset.addFormset;
      const formsetTemplate = document.querySelector(`[data-formset-template="${prefix}"]`);
      const formList = document.querySelector(`[data-formset-list="${prefix}"]`);
      const totalForms = document.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
      if (!formsetTemplate || !formList || !totalForms) {
        console.error(`No se pudo agregar una fila al formulario ${prefix}.`);
        return;
      }
      const index = Number.parseInt(totalForms.value, 10);
      if (!Number.isInteger(index)) {
        console.error(`El contador de formularios ${prefix} no es válido.`);
        return;
      }
      const html = formsetTemplate.innerHTML.replaceAll("__prefix__", String(index));
      const fragment = document.createRange().createContextualFragment(html);
      formList.append(fragment);
      totalForms.value = String(index + 1);
    });
  });

  const areaSelects = [...document.querySelectorAll('select[name$="-area"], select[name="area"]')];
  const typeCheckbox = document.querySelector('[name="tiene_tipos"]');

  function toggleBaseStockFields() {
    if (!typeCheckbox) return;
    const mainFields = typeCheckbox.closest("form").querySelector("[data-insumo-main]");
    if (!mainFields) return;
    ["cantidad_disponible", "stock_minimo", "unidad_medida"].forEach((name) => {
      const field = mainFields.querySelector(`[data-field="${name}"]`);
      if (field) field.hidden = typeCheckbox.checked;
    });
  }

  function setOptions(select, items, placeholder, selectedValue) {
    select.replaceChildren(new Option(placeholder, ""));
    items.forEach((item) => {
      const option = new Option(item.nombre, item.id);
      if (String(item.id) === String(selectedValue)) option.selected = true;
      select.add(option);
    });
  }

  async function loadInsums(areaSelect, preserveSelection) {
    const insumoName = areaSelect.name.replace(/area$/, "insumo");
    const typeName = areaSelect.name.replace(/area$/, "tipo_insumo");
    const insumoSelect = document.querySelector(`[name="${CSS.escape(insumoName)}"]`);
    const typeSelect = document.querySelector(`[name="${CSS.escape(typeName)}"]`);
    if (!insumoSelect || !typeSelect) return;

    const selectedInsumo = preserveSelection ? insumoSelect.value : "";
    const selectedType = preserveSelection ? typeSelect.value : "";
    if (!areaSelect.value) {
      setOptions(insumoSelect, [], "Selecciona un insumo", "");
      setOptions(typeSelect, [], "Selecciona un tipo (si aplica)", "");
      return;
    }

    const endpoint = new URL("/api/insumos/", window.location.origin);
    endpoint.searchParams.set("area", areaSelect.value);
    try {
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const items = data.insumos || [];
      setOptions(insumoSelect, items, "Selecciona un insumo", selectedInsumo);
      const selectedItem = items.find((item) => String(item.id) === String(insumoSelect.value));
      setOptions(
        typeSelect,
        selectedItem ? selectedItem.tipos : [],
        "Selecciona un tipo (si aplica)",
        selectedType,
      );
    } catch (error) {
      console.error("No se pudieron cargar los insumos del área.", error);
      const form = areaSelect.closest("form");
      if (form && !form.querySelector("[data-insumo-load-error]")) {
        const notice = document.createElement("p");
        notice.className = "form-error";
        notice.dataset.insumoLoadError = "";
        notice.setAttribute("role", "alert");
        notice.textContent = "No se pudieron cargar los insumos. Actualiza la página e inténtalo de nuevo.";
        areaSelect.closest(".form-field").append(notice);
      }
    }
  }

  areaSelects.forEach((areaSelect) => {
    const insumoName = areaSelect.name.replace(/area$/, "insumo");
    const insumoSelect = document.querySelector(`[name="${CSS.escape(insumoName)}"]`);
    areaSelect.addEventListener("change", () => loadInsums(areaSelect, false));
    if (insumoSelect) {
      insumoSelect.addEventListener("change", () => loadInsums(areaSelect, true));
    }
    if (areaSelect.value) loadInsums(areaSelect, true);
  });

  if (typeCheckbox) {
    typeCheckbox.addEventListener("change", toggleBaseStockFields);
    toggleBaseStockFields();
  }
})();
