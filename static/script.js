const state = {
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
  ["step-upload", "step-progress", "step-done"].forEach((s) => {
    if (s === id) el(s).classList.remove("hidden");
    else el(s).classList.add("hidden");
  });
}

// --- Step 1: Upload (auto-starts scraping) --------------------------------

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

    state.jobId = data.job_id;
    el("upload-status").textContent = "";
    showStep("step-progress");
    el("log-box").innerHTML = "";
    pollProgress();
  } catch (err) {
    showError(err.message);
    el("upload-status").textContent = "";
  }
}

// --- Step 2: Progress ------------------------------------------------------

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

// --- Step 3: Done ------------------------------------------------------

function finishJob(data) {
  showStep("step-done");
  el("done-summary").textContent =
    `Scraped ${data.total} eligible businesses and found ${data.found_count} email addresses.`;
  el("download-link").href = `/api/download/${state.jobId}`;
}

el("reset-btn").addEventListener("click", () => {
  showStep("step-upload");
  resetAll();
});

function resetAll() {
  state.jobId = null;
  fileInput.value = "";
  el("upload-status").textContent = "";
  clearError();
}
