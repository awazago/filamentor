"use strict";

const I18N = {
  "pt-BR": {
    tagline: "Sua peça pronta para imprimir",
    catalogTitle: "Catálogo de presets",
    catalogIntro: "Presets oficiais do Bambu Studio compatíveis com o Filamentor (A1 / A1 mini, PLA, PETG e TPU, bico inox).",
    printer: "Impressora",
    nozzle: "Bico",
    material: "Material",
    allMaterials: "Todos",
    processes: "Perfis de processo",
    filaments: "Filamentos",
    preset: "Preset",
    temperature: "Bico (°C)",
    flow: "Fluxo máx. (mm³/s)",
    loading: "Carregando…",
    summary: (p, f) => `${p} perfis de processo · ${f} filamentos`,
    error: "Não foi possível carregar o catálogo: ",
  },
  en: {
    tagline: "Your model, print-ready",
    catalogTitle: "Preset catalog",
    catalogIntro: "Official Bambu Studio presets supported by Filamentor (A1 / A1 mini, PLA, PETG and TPU, stainless nozzle).",
    printer: "Printer",
    nozzle: "Nozzle",
    material: "Material",
    allMaterials: "All",
    processes: "Process profiles",
    filaments: "Filaments",
    preset: "Preset",
    temperature: "Nozzle (°C)",
    flow: "Max flow (mm³/s)",
    loading: "Loading…",
    summary: (p, f) => `${p} process profiles · ${f} filaments`,
    error: "Could not load the catalog: ",
  },
};

const PRINTER_LABELS = { A1: "Bambu Lab A1", A1M: "Bambu Lab A1 mini" };

const state = {
  lang: localStorage.getItem("filamentor.lang") || (navigator.language.startsWith("pt") ? "pt-BR" : "en"),
  printers: [],
  materials: [],
};

const $ = (id) => document.getElementById(id);
const t = (key) => I18N[state.lang][key];

async function api(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function setOptions(select, options, selected) {
  select.replaceChildren(
    ...options.map(({ value, label }) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === selected;
      return option;
    }),
  );
}

function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.lang === state.lang));
  });
  renderMaterialOptions();
}

function renderMaterialOptions() {
  const select = $("material");
  if (!state.materials.length) return;
  const current = select.value;
  setOptions(
    select,
    [{ value: "", label: t("allMaterials") }, ...state.materials.map((m) => ({ value: m, label: m }))],
    current,
  );
}

function renderNozzles() {
  const key = $("printer").value;
  const nozzles = state.printers.filter((p) => p.key === key);
  const current = $("nozzle").value;
  const fallback = nozzles.find((p) => p.nozzle === 0.4) || nozzles[0];
  const selected = nozzles.some((p) => p.preset === current) ? current : fallback?.preset;
  setOptions(
    $("nozzle"),
    nozzles.map((p) => ({ value: p.preset, label: `${p.nozzle.toFixed(1)} mm` })),
    selected,
  );
}

async function refresh() {
  const machine = $("nozzle").value;
  const material = $("material").value;
  if (!machine) return;
  $("status").textContent = t("loading");
  try {
    const query = new URLSearchParams({ machine });
    const [processes, filaments] = await Promise.all([
      api(`/api/processes?${query}`),
      api(`/api/filaments?${new URLSearchParams({ machine, ...(material && { material }) })}`),
    ]);

    $("processes").replaceChildren(
      ...processes.map((p) => {
        const li = document.createElement("li");
        li.textContent = p.preset;
        li.title = p.description;
        return li;
      }),
    );

    $("filaments").replaceChildren(
      ...filaments.map((f) => {
        const tr = document.createElement("tr");
        const cells = [
          [f.preset, ""],
          [`${f.nozzle_temperature} (${f.nozzle_temperature_range[0]}–${f.nozzle_temperature_range[1]})`, "num"],
          [String(f.max_volumetric_speed), "num"],
        ];
        for (const [text, cls] of cells) {
          const td = document.createElement("td");
          td.textContent = text;
          if (cls) td.className = cls;
          tr.append(td);
        }
        return tr;
      }),
    );

    $("status").textContent = t("summary")(processes.length, filaments.length);
  } catch (error) {
    $("status").textContent = t("error") + error.message;
  }
}

async function init() {
  applyLanguage();
  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.addEventListener("click", () => {
      state.lang = button.dataset.lang;
      localStorage.setItem("filamentor.lang", state.lang);
      applyLanguage();
      refresh();
    });
  });

  try {
    [state.printers, state.materials] = await Promise.all([api("/api/printers"), api("/api/materials")]);
  } catch (error) {
    $("status").textContent = t("error") + error.message;
    return;
  }

  const keys = [...new Set(state.printers.map((p) => p.key))];
  setOptions($("printer"), keys.map((k) => ({ value: k, label: PRINTER_LABELS[k] || k })), keys[0]);
  renderMaterialOptions();
  renderNozzles();

  $("printer").addEventListener("change", () => {
    renderNozzles();
    refresh();
  });
  $("nozzle").addEventListener("change", refresh);
  $("material").addEventListener("change", refresh);
  refresh();
}

init();
