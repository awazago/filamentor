import { I18N } from "./i18n.js";
import { Viewer } from "./viewer.js";

const PRINTER_LABELS = { A1: "Bambu Lab A1", A1M: "Bambu Lab A1 mini" };
const DEFAULT_DENSITY = { PLA: 1.24, PETG: 1.27, TPU: 1.22 };
const FILAMENT_DIAMETER_MM = 1.75;
// Modelo simples de estimativa (até o fatiamento real na F5).
const SHELL_THICKNESS_MM = 0.84; // 2 paredes de 0,42 mm
const INFILL_RATIO = 0.15;

const $ = (id) => document.getElementById(id);

const state = {
  lang: readLang(),
  printers: [],
  filaments: [],
  analysis: null,
  orientation: 0, // índice da orientação mostrada no visualizador
  viewer: null,
};

function readLang() {
  try {
    const saved = localStorage.getItem("filamentor.lang");
    if (saved && I18N[saved]) return saved;
  } catch {
    // armazenamento indisponível (aba privada etc.)
  }
  return navigator.language.startsWith("pt") ? "pt-BR" : "en";
}

const t = (key) => I18N[state.lang][key];

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  node.append(...children);
  return node;
}

function setOptions(select, options, selected) {
  select.replaceChildren(
    ...options.map(({ value, label }) => el("option", { value, textContent: label, selected: value === selected })),
  );
}

const fmt = (value, digits = 1) =>
  Number(value).toLocaleString(state.lang, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
const pct = (ratio) => `${fmt(ratio * 100, 1)}%`;

// ---------- Respostas do questionário ----------

function radio(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value ?? "";
}

function selectedPrinter() {
  return state.printers.find((p) => p.preset === $("nozzle").value);
}

export function getAnswers() {
  const printer = selectedPrinter();
  return {
    machine: printer?.preset,
    printer: printer?.key,
    nozzle: printer?.nozzle,
    ams: radio("ams") === "yes",
    material: radio("material") || null,
    filament: $("filament").value || null,
    purpose: radio("purpose"),
    environment: radio("environment"),
    heat: radio("heat"),
    flexibility: radio("flexibility"),
    strength: radio("strength"),
    food: radio("food") === "yes",
    finish: radio("finish"),
    scale: scaleFactor(),
    orientation: state.analysis?.orientations[state.orientation]?.rotation ?? null,
  };
}

function renderNotes() {
  const a = getAnswers();
  const notes = I18N[state.lang].notes;
  const list = [];
  if (a.food) list.push(notes.foodContact);
  if (a.heat === "high") list.push(notes.highHeat);
  if (a.flexibility === "flexible" && a.material && a.material !== "TPU") list.push(notes.flexibleNotTpu);
  const isTpu = a.material === "TPU" || a.flexibility === "flexible";
  if (isTpu && a.ams && !(a.filament || "").includes("for AMS")) list.push(notes.tpuAms);
  if (isTpu && a.nozzle === 0.2) list.push(notes.tpuNozzle);
  if (a.environment === "outdoor" && a.material === "PLA") list.push(notes.outdoorPla);
  $("answer-notes").replaceChildren(...list.map((text) => el("span", { className: "alert", textContent: text })));
}

// ---------- Impressora e filamentos ----------

function renderNozzles() {
  const key = $("printer").value;
  const nozzles = state.printers.filter((p) => p.key === key);
  const current = $("nozzle").value;
  const fallback = nozzles.find((p) => p.nozzle === 0.4) || nozzles[0];
  const selected = nozzles.some((p) => p.preset === current) ? current : fallback?.preset;
  setOptions($("nozzle"), nozzles.map((p) => ({ value: p.preset, label: `${p.nozzle.toFixed(1)} mm` })), selected);
}

function onPrinterChange() {
  const printer = selectedPrinter();
  if (printer && state.viewer) state.viewer.setBed(printer.bed_x, printer.bed_y);
  loadFilaments();
  renderFit();
  renderThinWalls();
  renderNotes();
}

async function loadFilaments() {
  const material = radio("material");
  const machine = $("nozzle").value;
  $("filament-field").hidden = !material;
  if (!material || !machine) {
    state.filaments = [];
    renderScale();
    return;
  }
  const current = $("filament").value;
  try {
    state.filaments = await api(`/api/filaments?${new URLSearchParams({ machine, material })}`);
  } catch {
    state.filaments = [];
  }
  setOptions(
    $("filament"),
    [{ value: "", label: t("anyFilament") }, ...state.filaments.map((f) => ({ value: f.preset, label: f.preset }))],
    current,
  );
  renderNotes();
  renderScale();
}

// ---------- Análise ----------

function renderAnalysis() {
  const a = state.analysis;
  $("analysis-empty").hidden = !!a;
  $("analysis").hidden = !a;
  if (!a) return;

  $("filename").textContent = a.filename;
  $("plate-field").hidden = a.plates.length < 2;
  if (a.plates.length > 1) {
    setOptions(
      $("plate"),
      a.plates.map((p) => ({ value: String(p.index), label: t("plateLabel")(p.index, p.name, p.objects.length) })),
      String(a.plate),
    );
  }
  const warnings = I18N[state.lang].warnings;
  $("warnings").replaceChildren(
    ...a.warnings.map((code) => el("li", { textContent: warnings[code] || code })),
  );

  const [x, y, z] = a.dimensions_mm;
  // Overhang e contato dependem da orientação: mostram a que está no visualizador.
  const shown = a.orientations[state.orientation];
  const rows = [
    [t("dimensions"), `${fmt(x)} × ${fmt(y)} × ${fmt(z)} mm`],
    [a.volume_is_estimate ? t("volumeEstimate") : t("volume"), `${fmt(a.volume_mm3 / 1000, 2)} cm³`],
    [t("mesh"), a.health.watertight ? t("meshOk") : t("meshOpen")],
    [t("overhang45"), `${pct(shown.overhang_ratio)} · ${fmt(shown.overhang_ratio * a.surface_area_mm2, 0)} mm²`],
    [t("contact"), `${fmt(shown.contact_area_mm2, 0)} mm²`],
    [t("triangles"), fmt(a.triangles, 0)],
  ];
  $("metrics").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: v })]));

  // As 4 melhores, mas a orientação original do arquivo sempre aparece (para poder voltar a ela).
  const visible = [0, 1, 2, 3].filter((i) => i < a.orientations.length);
  const originalIndex = a.orientations.findIndex((o) => o.label === "original");
  if (!visible.includes(originalIndex)) visible[visible.length - 1] = originalIndex;

  $("orientations").replaceChildren(
    ...visible.map((index) => {
      const o = a.orientations[index];
      const name = o.label === "original" ? t("orientationOriginal") : `${t("orientationStable")} ${index + 1}`;
      const button = el(
        "button",
        { type: "button", className: index === state.orientation ? "orientation active" : "orientation" },
        el("strong", { textContent: `${name}${index === 0 ? ` · ${t("best")}` : ""}` }),
        el("span", {
          textContent: `${t("overhangShort")} ${pct(o.overhang_ratio)} · ${t("contactShort")} ${fmt(o.contact_area_mm2, 0)} mm² · ${t("heightShort")} ${fmt(o.height_mm)} mm`,
        }),
      );
      button.addEventListener("click", () => {
        state.orientation = index;
        state.viewer.setRotation(o.rotation);
        renderAnalysis();
      });
      return el("li", {}, button);
    }),
  );

  if (a.orientations.length === 1) {
    $("orientations").append(el("li", { className: "muted small", textContent: t("multiObjectNote") }));
  }

  renderThinWalls();
  renderFit();
  renderScale();
}

function renderThinWalls() {
  const a = state.analysis;
  if (!a) return;
  const nozzle = selectedPrinter()?.nozzle;
  $("thin-walls").replaceChildren(
    ...Object.entries(a.thin_walls.below_line_width).flatMap(([size, ratio]) => {
      const current = Number(size) === nozzle;
      return [
        el("dt", { textContent: `${t("nozzle")} ${size} mm`, className: current ? "current" : "" }),
        el("dd", { textContent: pct(ratio), className: current ? "current" : "" }),
      ];
    }),
  );
}

function renderFit() {
  const a = state.analysis;
  const printer = selectedPrinter();
  if (!a || !printer) {
    $("printer-fit").textContent = "";
    return;
  }
  const fit = a.fits.find((f) => f.printer === printer.model);
  if (!fit) return;
  const scale = scaleFactor();
  const max = fit.max_uniform_scale;
  $("printer-fit").textContent =
    max >= scale ? t("fitsOn")(printer.model, fmt(max / scale, 1)) : t("doesNotFit")(printer.model, max);
  $("printer-fit").classList.toggle("bad", max < scale);
}

// ---------- Escala e estimativa ----------

function scaleFactor() {
  if (!$("scale-enabled").checked) return 1;
  const percent = Number($("scale-percent").value);
  return percent > 0 ? percent / 100 : 1;
}

function renderScale() {
  const a = state.analysis;
  state.viewer?.setScale(scaleFactor());
  if (!a) {
    $("scale-result").replaceChildren();
    return;
  }
  const s = scaleFactor();
  const [x, y, z] = a.dimensions_mm.map((d) => d * s);
  const volume = a.volume_mm3 * s ** 3;
  const area = a.surface_area_mm2 * s ** 2;
  const shell = Math.min(volume, area * SHELL_THICKNESS_MM);
  const printed = shell + (volume - shell) * INFILL_RATIO;

  const material = radio("material") || "PLA";
  const chosen = state.filaments.find((f) => f.preset === $("filament").value);
  const density = chosen?.density ?? DEFAULT_DENSITY[material];
  const grams = (printed / 1000) * density;
  const meters = printed / (Math.PI * (FILAMENT_DIAMETER_MM / 2) ** 2) / 1000;

  $("scale-result").replaceChildren(
    el("dt", { textContent: t("scaledSize") }),
    el("dd", { textContent: `${fmt(x)} × ${fmt(y)} × ${fmt(z)} mm` }),
    el("dt", { textContent: t("filamentEstimate") }),
    el("dd", { textContent: `~${fmt(grams, 0)} g · ${fmt(meters, 1)} m (${material})` }),
  );
  renderFit();
}

function syncScaleFromPercent() {
  const a = state.analysis;
  if (a) $("scale-height").value = (a.dimensions_mm[2] * scaleFactor()).toFixed(1);
  renderScale();
}

function syncScaleFromHeight() {
  const a = state.analysis;
  const height = Number($("scale-height").value);
  if (a && height > 0) $("scale-percent").value = ((height / a.dimensions_mm[2]) * 100).toFixed(1);
  renderScale();
}

// ---------- Upload ----------

function setViewerStatus(text) {
  $("viewer-status").hidden = !text;
  $("viewer-status").textContent = text || "";
}

async function handleFile(file) {
  if (!file) return;
  if (!/\.(stl|3mf)$/i.test(file.name)) {
    setViewerStatus(t("error") + file.name);
    return;
  }
  state.analysis = null;
  renderAnalysis();
  $("dropzone").hidden = true;
  setViewerStatus(t("loadingModel"));

  const form = new FormData();
  form.append("file", file);
  const analysis = api("/api/analyze", { method: "POST", body: form });
  const is3mf = /\.3mf$/i.test(file.name);

  try {
    // STL abre na hora no navegador; 3MF (projetos Bambu) vem convertido pelo backend.
    if (!is3mf) {
      state.viewer.loadSTL(await file.arrayBuffer());
      $("viewer-tools").hidden = false;
    }
    setViewerStatus(t("analyzing"));
    await showAnalysis(await analysis, is3mf);
    syncScaleFromPercent();
  } catch (error) {
    setViewerStatus(t("error") + error.message);
  }
}

async function loadServerMesh(analysis) {
  const query = analysis.plate ? `?plate=${analysis.plate}` : "";
  const response = await fetch(`/api/uploads/${analysis.upload_id}/mesh${query}`);
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
  state.viewer.loadSTL(await response.arrayBuffer());
  $("viewer-tools").hidden = false;
}

async function showAnalysis(analysis, fetchMesh) {
  if (fetchMesh) await loadServerMesh(analysis);
  state.analysis = analysis;
  state.orientation = 0;
  state.viewer.setRotation(analysis.orientations[0].rotation);
  setViewerStatus("");
  renderAnalysis();
}

async function changePlate() {
  const current = state.analysis;
  if (!current) return;
  setViewerStatus(t("analyzing"));
  try {
    const next = await api(`/api/uploads/${current.upload_id}/analysis?plate=${$("plate").value}`);
    await showAnalysis(next, true);
    syncScaleFromPercent();
  } catch (error) {
    setViewerStatus(t("error") + error.message);
  }
}

function setupUpload() {
  const viewer = $("viewer");
  $("file").addEventListener("change", (e) => handleFile(e.target.files[0]));
  $("replace").addEventListener("click", () => $("file").click());
  $("plate").addEventListener("change", changePlate);
  viewer.addEventListener("dragover", (e) => {
    e.preventDefault();
    viewer.classList.add("dragging");
  });
  viewer.addEventListener("dragleave", () => viewer.classList.remove("dragging"));
  viewer.addEventListener("drop", (e) => {
    e.preventDefault();
    viewer.classList.remove("dragging");
    handleFile(e.dataTransfer.files[0]);
  });
}

// ---------- Idioma ----------

function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.lang === state.lang));
  });
  if (state.printers.length) {
    renderAnalysis();
    renderNotes();
    loadFilaments();
  }
}

// ---------- Início ----------

async function init() {
  applyLanguage();
  document.querySelectorAll("[data-lang]").forEach((button) =>
    button.addEventListener("click", () => {
      state.lang = button.dataset.lang;
      try {
        localStorage.setItem("filamentor.lang", state.lang);
      } catch {
        // ignora: preferência só vale para esta sessão
      }
      applyLanguage();
    }),
  );

  state.viewer = new Viewer($("viewer"));
  $("viewer").addEventListener("overhang", (e) => {
    $("threshold-value").textContent = `${e.detail.threshold}° · ${pct(e.detail.ratio)}`;
  });
  $("threshold").addEventListener("input", (e) => state.viewer.setThreshold(Number(e.target.value)));
  setupUpload();

  try {
    state.printers = await api("/api/printers");
  } catch (error) {
    setViewerStatus(t("error") + error.message);
    return;
  }
  const keys = [...new Set(state.printers.map((p) => p.key))];
  setOptions($("printer"), keys.map((k) => ({ value: k, label: PRINTER_LABELS[k] || k })), keys[0]);
  renderNozzles();

  $("printer").addEventListener("change", () => {
    renderNozzles();
    onPrinterChange();
  });
  $("nozzle").addEventListener("change", onPrinterChange);
  document.querySelectorAll('input[name="material"]').forEach((input) => input.addEventListener("change", loadFilaments));
  $("filament").addEventListener("change", () => {
    renderNotes();
    renderScale();
  });
  document.querySelectorAll(".chips input").forEach((input) => input.addEventListener("change", renderNotes));
  $("scale-enabled").addEventListener("change", (e) => {
    $("scale-fields").hidden = !e.target.checked;
    syncScaleFromPercent();
  });
  $("scale-percent").addEventListener("input", syncScaleFromPercent);
  $("scale-height").addEventListener("input", syncScaleFromHeight);

  onPrinterChange();
}

init();
