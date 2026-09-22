const state = {
  uploadId: null,
  columns: [],
  preview: [],
  jobId: null,
  pollTimer: null,
};

const el = (id) => document.getElementById(id);

function showError(message) {
  const banner = el("error-banner");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearError() {
  el("error-banner").classList.add("hidden");
}

function showStep(id) {
  ["step-upload", "step-map", "step-progress", "step-done"].forEach((s) => {
    if (s === id) el(s).classList.remove("hidden");
  });
}

// --- Step 1: Upload ---------------------------------------------------

const dropzone = el("dropzone");
const fileInput = el("file-input");

dropzone.addEventListener("click", () => fileInput.click());

["dragover", "dragenter"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

async function handleFile(file) {
  clearError();
  el("upload-status").textContent = `Uploading ${file.name}...`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload failed.");

    state.uploadId = data.upload_id;
    state.columns = data.columns;
    state.preview = data.preview || [];
    el("upload-status").textContent = `Loaded "${file.name}" — ${data.row_count} rows, ${data.columns.length} columns.`;

    renderPreviewTable();
    populateColumnSelects();
    el("step-map").classList.remove("hidden");
  } catch (err) {
    showError(err.message);
    el("upload-status").textContent = "";
  }
}

// --- Step 2: Mapping ---------------------------------------------------

function renderPreviewTable() {
  const table = el("preview-table");
  table.innerHTML = "";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  state.columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  state.preview.forEach((row) => {
    const tr = document.createElement("tr");
    state.columns.forEach((col) => {
      const td = document.createElement("td");
      const val = row[col];
      td.textContent = val === null || val === undefined || val === "" ? "—" : val;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function populateColumnSelects() {
  const nameSel = el("col-name");
  const urlSel = el("col-url");
  const statusSel = el("col-status");

  nameSel.innerHTML = "";
  urlSel.innerHTML = "";
  statusSel.innerHTML = '<option value="">— None —</option>';

  state.columns.forEach((col) => {
    nameSel.appendChild(new Option(col, col));
    urlSel.appendChild(new Option(col, col));
    statusSel.appendChild(new Option(col, col));
  });

  // Reasonable guesses based on common header names (exact match first,
  // then substring match, so e.g. "Business Website" still matches "website").
  guessSelect(urlSel, ["website / url", "website", "url", "site", "domain", "web"]);
  guessSelect(statusSel, ["status", "stage", "deal status"]);
  guessSelect(nameSel, ["business name", "company name", "name", "company", "business", "client", "organization"]);

  validateMapping();
  if (statusSel.value) loadStatusValues(statusSel.value);
}

function guessSelect(selectEl, candidates) {
  const options = Array.from(selectEl.options).filter((o) => o.value);

  // Pass 1: exact header match.
  for (const candidate of candidates) {
    const match = options.find((o) => o.value.toLowerCase() === candidate);
    if (match) { selectEl.value = match.value; return; }
  }
  // Pass 2: header contains the candidate word (e.g. "Business Website").
  for (const candidate of candidates) {
    const match = options.find((o) => o.value.toLowerCase().includes(candidate));
    if (match) { selectEl.value = match.value; return; }
  }
}

function validateMapping() {
  const ok = el("col-name").value && el("col-url").value;
  el("start-btn").disabled = !ok;
}

el("col-name").addEventListener("change", validateMapping);
el("col-url").addEventListener("change", validateMapping);
el("col-status").addEventListener("change", (e) => {
  validateMapping();
  if (e.target.value) {
    loadStatusValues(e.target.value);
  } else {
    el("status-filter-block").classList.add("hidden");
  }
});

async function loadStatusValues(column) {
  clearError();
  try {
    const res = await fetch("/api/column-values", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: state.uploadId, column }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not load values.");

    const container = el("status-values");
    container.innerHTML = "";

    const commonExclusions = ["no deal", "awaiting response", "dead"];
    data.values.forEach((value) => {
      const id = `chip-${value.replace(/\W+/g, "_")}`;
      const checked = !commonExclusions.includes(value.toLowerCase());
      const label = document.createElement("label");
      label.className = "chip" + (checked ? " checked" : "");
      label.innerHTML = `<input type="checkbox" id="${id}" value="${value}" ${checked ? "checked" : ""}/> ${value}`;
      label.querySelector("input").addEventListener("change", (e) => {
        label.classList.toggle("checked", e.target.checked);
      });
      container.appendChild(label);
    });

    el("include-blank").checked = data.has_blank ? true : el("include-blank").checked;
    el("status-filter-block").classList.remove("hidden");
  } catch (err) {
    showError(err.message);
  }
}

el("start-btn").addEventListener("click", startJob);

async function startJob() {
  clearError();
  const statusCol = el("col-status").value;
  const includedStatuses = statusCol
    ? Array.from(document.querySelectorAll("#status-values input:checked")).map((i) => i.value)
    : [];

  const payload = {
    upload_id: state.uploadId,
    name_col: el("col-name").value,
    url_col: el("col-url").value,
    status_col: statusCol || null,
    included_statuses: includedStatuses,
    include_blank_status: el("include-blank").checked,
  };

  try {
    const res = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not start job.");

    state.jobId = data.job_id;
    el("step-map").classList.add("hidden");
    showStep("step-progress");
    el("log-box").innerHTML = "";
    pollProgress();
  } catch (err) {
    showError(err.message);
  }
}

// --- Step 3: Progress ----------------------------------------------------

function pollProgress() {
  state.pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/progress/${state.jobId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Lost track of job.");

      renderProgress(data);

      if (data.state === "done" || data.state === "error" || data.state === "cancelled") {
        clearInterval(state.pollTimer);
        if (data.state === "done") finishJob(data);
        if (data.state === "error") showError(`Scraping failed: ${data.error}`);
        if (data.state === "cancelled") {
          el("step-progress").classList.add("hidden");
          showStep("step-upload");
          resetAll();
        }
      }
    } catch (err) {
      clearInterval(state.pollTimer);
      showError(err.message);
    }
  }, 1000);
}

function renderProgress(data) {
  const pct = data.total ? Math.round((data.processed / data.total) * 100) : 0;
  el("progress-bar").style.width = `${pct}%`;
  el("progress-count").textContent = `${data.processed} / ${data.total}`;
  el("progress-found").textContent = `${data.found_count} emails found`;
  el("current-row").textContent = data.current ? `Scraping: ${data.current}` : "";

  const logBox = el("log-box");
  logBox.innerHTML = "";
  data.log_tail.slice().reverse().forEach((entry) => {
    const line = document.createElement("div");
    line.className = "log-line";
    const emailSpan = entry.email
      ? `<span class="email-found">${entry.email}</span>`
      : `<span class="email-missing">no email found</span>`;
    line.innerHTML = `<span class="biz">${entry.business}</span>${emailSpan}`;
    logBox.appendChild(line);
  });
}

el("cancel-btn").addEventListener("click", async () => {
  if (!state.jobId) return;
  await fetch(`/api/cancel/${state.jobId}`, { method: "POST" });
});

// --- Step 4: Done ----------------------------------------------------

function finishJob(data) {
  el("step-progress").classList.add("hidden");
  showStep("step-done");
  el("done-summary").textContent =
    `Scraped ${data.total} eligible businesses and found ${data.found_count} email addresses.`;
  el("download-link").href = `/api/download/${state.jobId}`;
}

el("reset-btn").addEventListener("click", () => {
  el("step-done").classList.add("hidden");
  showStep("step-upload");
  resetAll();
});

function resetAll() {
  state.uploadId = null;
  state.columns = [];
  state.jobId = null;
  fileInput.value = "";
  el("upload-status").textContent = "";
  el("step-map").classList.add("hidden");
  el("status-filter-block").classList.add("hidden");
  clearError();
}
