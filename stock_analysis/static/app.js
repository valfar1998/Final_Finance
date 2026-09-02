const form = document.getElementById("form");
const btn = document.getElementById("btn");
const statusEl = document.getElementById("status");
const errorEl = document.getElementById("error");
const resultEl = document.getElementById("result");
const coverageEl = document.getElementById("coverage");
const coverageText = document.getElementById("coverage-text");
const barCrit = document.getElementById("bar-crit");
const tikrMapEl = document.getElementById("tikr-map");
const outputEl = document.getElementById("output");
const metaEl = document.getElementById("meta");
const tickerEl = document.getElementById("ticker");
const sectorEl = document.getElementById("sector");
const sectorHint = document.getElementById("sector-hint");
const sectorList = document.getElementById("sector-metrics-list");

tickerEl.addEventListener("input", () => {
  tickerEl.value = tickerEl.value.toUpperCase().replace(/\s+/g, "");
});

function refreshSectorHint() {
  const keys = (window.SECTOR_METRICS || {})[sectorEl.value] || [];
  sectorList.innerHTML = "";
  keys.forEach((k) => {
    const li = document.createElement("li");
    li.textContent = k;
    sectorList.appendChild(li);
  });
  sectorHint.hidden = keys.length === 0;
}

sectorEl.addEventListener("change", refreshSectorHint);
refreshSectorHint();

function bindFileLabel(inputId, nameId, maxOverride) {
  const input = document.getElementById(inputId);
  const name = document.getElementById(nameId);
  if (!input || !name) return;
  const drop = input.closest(".drop");
  const maxFiles = maxOverride || window.MAX_HTML_FILES || 10;

  const setFiles = (list) => {
    const dt = new DataTransfer();
    [...list].slice(0, maxFiles).forEach((f) => dt.items.add(f));
    input.files = dt.files;
    const files = [...input.files];
    if (list.length > maxFiles) {
      name.textContent = `${files.map((f) => f.name).join(", ")} (max ${maxFiles}, altri ignorati)`;
    } else {
      name.textContent = files.length ? files.map((f) => f.name).join(", ") : "Nessun file";
    }
  };

  const refresh = () => setFiles(input.files);
  input.addEventListener("change", () => setFiles(input.files));

  ["dragenter", "dragover"].forEach((ev) => {
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); });
  });
  ["dragleave", "drop"].forEach((ev) => {
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); });
  });
  drop.addEventListener("drop", (e) => {
    const incoming = [...(e.dataTransfer.files || [])];
    if (!incoming.length) return;
    setFiles([...input.files, ...incoming]);
  });
}

bindFileLabel("investing", "name-investing");
bindFileLabel("tikr_auto", "name-tikr_auto", window.MAX_TIKR_DUMP || 25);
(window.TIKR_SOURCE_IDS || []).forEach((id) => bindFileLabel(id, `name-${id}`));
(window.EXTRA_SOURCE_IDS || []).forEach((id) => bindFileLabel(id, `name-${id}`));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.hidden = true;
  resultEl.hidden = true;
  coverageEl.hidden = true;
  if (tikrMapEl) tikrMapEl.hidden = true;
  statusEl.hidden = false;
  btn.disabled = true;

  try {
    const fd = new FormData(form);
    const res = await fetch("/api/analyze", { method: "POST", body: fd });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Errore");

    const cov = data.coverage;
    coverageEl.hidden = false;
    coverageEl.classList.toggle("ok", data.reliable);
    coverageEl.classList.toggle("bad", !data.reliable);
    coverageText.textContent =
      `Critici ${cov.critical_ok.length}/7 (${Math.round(cov.critical_pct)}%) — ` +
      `mancanti: ${cov.critical_missing.join(", ") || "nessuno"}` +
      (data.reliable ? " · AFFIDABILE" : " · DATI INSUFFICIENTI");
    barCrit.style.width = `${Math.round(cov.critical_pct)}%`;

    const autoMap = (data.sources && data.sources.tikr_auto_map) || [];
    if (tikrMapEl) {
      tikrMapEl.innerHTML = "";
      if (autoMap.length) {
        tikrMapEl.hidden = false;
        autoMap.forEach((row) => {
          const li = document.createElement("li");
          const short = (row.file || "").replace(/^.*[\\/]/, "");
          li.textContent = `${row.label}${row.detail ? " · " + row.detail : ""} ← ${short}`;
          tikrMapEl.appendChild(li);
        });
      } else {
        tikrMapEl.hidden = true;
      }
    }

    outputEl.textContent = data.report;
    const tikrTabs = (data.sources.tikr_loaded || []).length;
    const tikrTotal = (window.TIKR_SOURCE_IDS || []).length || 10;
    const extraLoaded = (data.sources.extra_loaded || []).join(", ") || "nessuna";
    metaEl.textContent =
      `${data.ticker} · ${data.sector} · ${data.verdict} · ${Math.round(data.score)}/100 · rischio ${data.risk}/5 · ` +
      `Yahoo API ${data.sources.yahoo_fields} campi · ` +
      `TIKR ${tikrTabs}/${tikrTotal} tab · extra ${extraLoaded} · ${data.saved_as}`;
    resultEl.hidden = false;
    resultEl.dataset.filename = data.saved_as.split(/[/\\]/).pop();
  } catch (err) {
    errorEl.hidden = false;
    errorEl.textContent = err.message || String(err);
  } finally {
    statusEl.hidden = true;
    btn.disabled = false;
  }
});

document.getElementById("copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText(outputEl.textContent);
});

document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([outputEl.textContent], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = resultEl.dataset.filename || "report.txt";
  a.click();
  URL.revokeObjectURL(a.href);
});
