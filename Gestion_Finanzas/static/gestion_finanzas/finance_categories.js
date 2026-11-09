document.addEventListener("DOMContentLoaded", () => {
  const currency = document.getElementById("id_tipo_cuenta");
  const paymentMethod = document.getElementById("id_metodo_pago");
  const platform = document.getElementById("id_plataforma");
  const movementType = document.getElementById("id_tipo");
  const financeCategory = document.getElementById("id_finance_category");
  const expenseCategory = document.getElementById("id_categoria_egreso");
  const incomeCategory = document.getElementById("id_tipo_ingreso");

  if (!currency || !paymentMethod || !platform) return;

  const cardOption = paymentMethod.querySelector('option[value="TARJETA"]');
  const financeCategoryRow = financeCategory?.closest(".form-row");
  const financeCategorySection = financeCategory?.closest(".module");
  const workRow = document.getElementById("id_trabajo")?.closest(".form-row");
  const expenseCategoryRow = expenseCategory?.closest(".form-row");
  const incomeCategoryRow = incomeCategory?.closest(".form-row");
  const amountRow = document.getElementById("id_monto")?.closest(".form-row");
  const financeCategoryOptions = financeCategory
    ? Array.from(financeCategory.options).filter((option) => option.dataset.kind)
    : [];

  const update = () => {
    const isCash = paymentMethod.value === "EFECTIVO_USD";
    const isMobilePayment = paymentMethod.value === "PAGO_MOVIL";
    const isExpense = movementType?.value === "EGRESO";
    const isEmployeePayment = isExpense && expenseCategory?.value === "PAGO_EMPLEADOS";
    const isCustomerRefund = isExpense && expenseCategory?.value === "REEMBOLSO_CLIENTE";
    const isCustomerAdvance = !isExpense && incomeCategory?.value === "ABONO_CLIENTES";
    const isOtherIncome = !isExpense && incomeCategory?.value === "OTROS_INGRESOS";
    const automaticExpenseCategoryKey = isEmployeePayment
      ? "PAGO_EMPLEADOS"
      : isCustomerRefund
        ? "REEMBOLSO_CLIENTE"
        : null;
    const automaticFinanceCategory = financeCategoryOptions.find((option) =>
      automaticExpenseCategoryKey
        ? option.dataset.expenseCategory === automaticExpenseCategoryKey
        : isCustomerAdvance
          ? option.dataset.incomeCategory === "ABONO_CLIENTES"
          : isOtherIncome
            ? option.dataset.incomeCategory === "OTROS_INGRESOS"
            : false,
    );
    if (expenseCategoryRow) expenseCategoryRow.style.display = isExpense ? "" : "none";
    if (incomeCategoryRow) incomeCategoryRow.style.display = isExpense ? "none" : "";
    if (workRow) workRow.style.display = isCustomerRefund ? "" : "none";
    if (incomeCategoryRow && amountRow?.parentNode === incomeCategoryRow.parentNode) {
      amountRow.after(incomeCategoryRow);
    }
    if (cardOption) cardOption.hidden = isExpense;
    if (isExpense && paymentMethod.value === "TARJETA") paymentMethod.value = "";

    const applicableKind = isExpense ? "EXPENSE" : "INCOME";
    financeCategoryOptions.forEach((option) => {
      option.hidden = option.dataset.kind !== applicableKind && option.dataset.kind !== "BOTH";
    });
    if (automaticFinanceCategory && (automaticExpenseCategoryKey || isCustomerAdvance)) {
      financeCategory.value = automaticFinanceCategory.value;
    } else if (
      financeCategory?.selectedOptions[0]?.dataset.expenseCategory
    ) {
      financeCategory.value = "";
    }
    if (financeCategory?.selectedOptions[0]?.hidden) financeCategory.value = "";
    const hideFinanceCategory = Boolean(
      (automaticExpenseCategoryKey || isCustomerAdvance || isOtherIncome) && automaticFinanceCategory,
    );
    if (financeCategoryRow) financeCategoryRow.style.display = hideFinanceCategory ? "none" : "";
    if (financeCategory) financeCategory.disabled = hideFinanceCategory;
    if (financeCategorySection) {
      financeCategorySection.style.display = hideFinanceCategory ? "none" : "";
    }

    const hideAccountFields = isCash || isMobilePayment;
    currency.closest(".form-row").style.display = hideAccountFields ? "none" : "";
    platform.closest(".form-row").style.display = hideAccountFields ? "none" : "";
    currency.disabled = hideAccountFields;
    platform.disabled = hideAccountFields;
    if (isCash) {
      currency.value = "";
      platform.value = "";
    } else if (isMobilePayment) {
      currency.value = "VES";
      platform.value = "BANCO_NACIONAL";
    }
  };

  [
    currency,
    paymentMethod,
    platform,
    movementType,
    expenseCategory,
    incomeCategory,
    financeCategory,
  ]
    .filter(Boolean)
    .forEach((input) => {
      input.addEventListener("input", update);
      input.addEventListener("change", update);
    });
  update();
});
