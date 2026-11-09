(() => {
  const sections = [...document.querySelectorAll("[data-section]")];
  const links = [...document.querySelectorAll("[data-section-link]")];
  const title = document.getElementById("current-section-title");
  const sidebar = document.getElementById("sidebar");
  const menuToggle = document.querySelector(".menu-toggle");
  const titles = {
    inicio: "Inicio",
    trabajos: "Trabajos",
    jornadas: "Calendario y jornadas",
    "por-cobrar": "Por cobrar",
    inventario: "Insumos",
    finanzas: "Finanzas",
  };

  function normalize(value) {
    return value
      .toLocaleLowerCase("es")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  function showSection(id, updateHash) {
    const activeId = sections.some((section) => section.id === id) ? id : "inicio";
    sections.forEach((section) => {
      const active = section.id === activeId;
      section.hidden = !active;
      section.classList.toggle("active", active);
    });
    links.forEach((link) => {
      const active = link.dataset.sectionLink === activeId;
      link.classList.toggle("active", active);
      if (active && link.matches(".nav-link")) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
    if (title) title.textContent = titles[activeId] || "Inicio";
    if (updateHash && window.location.hash !== `#${activeId}`) {
      window.history.replaceState(null, "", `#${activeId}`);
    }
    if (sidebar) sidebar.classList.remove("is-open");
    if (menuToggle) menuToggle.setAttribute("aria-expanded", "false");
  }

  links.forEach((link) => {
    link.addEventListener("click", (event) => {
      const id = link.dataset.sectionLink;
      if (!sections.some((section) => section.id === id)) return;
      event.preventDefault();
      showSection(id, true);
    });
  });

  document.querySelectorAll("[data-dashboard-search]").forEach((input) => {
    const section = input.closest(".page-section");
    const kind = input.dataset.dashboardSearch;
    const resultLabel = section.querySelector(`[data-search-count="${kind}"]`);
    const noResults = section.querySelector(`[data-no-search-results="${kind}"]`);

    input.addEventListener("input", () => {
      const query = normalize(input.value);
      let resultCount = 0;

      if (kind === "work") {
        const rows = section.querySelectorAll('[data-search-row="work"]');
        rows.forEach((row) => {
          const visible = !query || normalize(row.dataset.searchText || row.textContent).includes(query);
          row.hidden = !visible;
          if (visible) resultCount += 1;
        });
      } else if (kind === "inventory") {
        section.querySelectorAll("[data-inventory-folder]").forEach((folder) => {
          let folderCount = 0;
          folder.querySelectorAll('[data-search-row="inventory-parent"]').forEach((parent) => {
            const variantPanel = parent.nextElementSibling?.matches("[data-variant-list]")
              ? parent.nextElementSibling
              : null;
            const variantRows = variantPanel
              ? [...variantPanel.querySelectorAll('[data-search-row="inventory-variant"]')]
              : [];
            const parentMatches = !query || normalize(parent.dataset.searchText || parent.textContent).includes(query);
            const matchedVariants = variantRows.filter((row) =>
              !query || normalize(row.dataset.searchText || row.textContent).includes(query)
            );
            const variantMatches = Boolean(query && matchedVariants.length);
            const visible = parentMatches || variantMatches;
            parent.hidden = !visible;
            if (variantPanel) {
              const toggle = parent.querySelector("[data-toggle-variants]");
              const shouldExpand = query ? variantMatches : toggle?.dataset.expanded === "true";
              variantPanel.hidden = !shouldExpand;
              variantRows.forEach((row) => {
                row.hidden = Boolean(query && !normalize(row.dataset.searchText || row.textContent).includes(query));
              });
              if (toggle && query && variantMatches) {
                toggle.setAttribute("aria-expanded", "true");
              } else if (toggle && !query) {
                toggle.setAttribute("aria-expanded", toggle.dataset.expanded || "false");
              }
            }
            if (visible) folderCount += 1;
          });
          folder.hidden = folderCount === 0;
          resultCount += folderCount;
        });
      }

      if (resultLabel) {
        resultLabel.textContent = kind === "inventory"
          ? `${resultCount} ${resultCount === 1 ? "insumo" : "insumos"}`
          : `${resultCount} ${resultCount === 1 ? "resultado" : "resultados"}`;
      }
      if (noResults) noResults.hidden = resultCount !== 0;
    });
  });

  document.querySelectorAll("[data-toggle-variants]").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const panel = document.getElementById(toggle.getAttribute("aria-controls"));
      if (!panel) return;
      const isExpanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.dataset.expanded = String(!isExpanded);
      toggle.setAttribute("aria-expanded", String(!isExpanded));
      panel.hidden = isExpanded;
    });
  });

  document.querySelectorAll("[data-clear-search]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.clearSearch);
      if (!input) return;
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    });
  });

  const calendarDayButtons = [...document.querySelectorAll("[data-calendar-date]")];
  const journeyCards = [...document.querySelectorAll("[data-journey-date]")];
  const journeyFilterTitle = document.querySelector("[data-journey-filter-title]");
  const journeyFilterHint = document.querySelector("[data-journey-filter-hint]");
  const clearJourneyFilter = document.querySelector("[data-clear-calendar-filter]");
  const noJourneysForDate = document.querySelector("[data-no-journeys-for-date]");

  function filterJourneysByDate(selectedDate, showAll = false) {
    let visibleCount = 0;
    journeyCards.forEach((card) => {
      const visible = showAll || Boolean(selectedDate && card.dataset.journeyDate === selectedDate);
      card.hidden = !visible;
      card.style.display = visible ? "" : "none";
      if (visible) visibleCount += 1;
    });
    calendarDayButtons.forEach((button) => {
      const selected = button.dataset.calendarDate === selectedDate;
      button.setAttribute("aria-pressed", String(selected));
      button.classList.toggle("is-selected", selected);
    });
    if (journeyFilterTitle) {
      journeyFilterTitle.textContent = selectedDate
        ? `Jornadas del ${new Date(`${selectedDate}T00:00:00`).toLocaleDateString("es", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
          })}`
        : showAll ? "Todas las jornadas" : "Jornadas del día seleccionado";
    }
    if (journeyFilterHint) {
      journeyFilterHint.textContent = selectedDate
        ? `${visibleCount} ${visibleCount === 1 ? "jornada encontrada" : "jornadas encontradas"}.`
        : showAll
          ? `${visibleCount} ${visibleCount === 1 ? "jornada encontrada" : "jornadas encontradas"}.`
          : "Selecciona un día del calendario para ver únicamente sus jornadas.";
    }
    if (clearJourneyFilter) clearJourneyFilter.hidden = showAll;
    if (noJourneysForDate) {
      noJourneysForDate.hidden = showAll || !selectedDate || visibleCount > 0;
      if (!selectedDate && !showAll) {
        noJourneysForDate.textContent = "Selecciona un día del calendario para consultar sus jornadas.";
        noJourneysForDate.hidden = false;
      } else if (selectedDate) {
        noJourneysForDate.textContent = "No hay jornadas registradas para este día.";
      }
    }
  }

  calendarDayButtons.forEach((button) => {
    button.addEventListener("click", () => {
      filterJourneysByDate(button.dataset.calendarDate);
    });
  });
  if (clearJourneyFilter) {
    clearJourneyFilter.addEventListener("click", () => filterJourneysByDate("", true));
  }
  if (journeyCards.length) filterJourneysByDate("");

  if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => {
      const isOpen = sidebar.classList.toggle("is-open");
      menuToggle.setAttribute("aria-expanded", String(isOpen));
    });
  }

  window.addEventListener("hashchange", () => {
    showSection(window.location.hash.slice(1), false);
  });
  const querySection = new URLSearchParams(window.location.search).get("section");
  showSection(window.location.hash.slice(1) || querySection, false);
})();
