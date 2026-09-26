const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadStatus = document.getElementById("upload-status");
const tbody = document.getElementById("invoice-tbody");
const syncAllBtn = document.getElementById("sync-all-btn");
const syncAllStatus = document.getElementById("sync-all-status");

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fileInput.files.length) return;

  const formData = new FormData();
  for (const f of fileInput.files) formData.append("files", f);

  uploadStatus.textContent = "Extracting... this can take a few seconds per file.";
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    uploadStatus.textContent = `Processed ${data.results.length} file(s). Reloading...`;
    setTimeout(() => window.location.reload(), 600);
  } catch (err) {
    uploadStatus.textContent = "Upload failed: " + err;
  }
});

tbody.addEventListener("click", async (e) => {
  const row = e.target.closest("tr");
  if (!row) return;
  const id = row.dataset.id;

  if (e.target.classList.contains("save-btn")) {
    const payload = {};
    row.querySelectorAll("[data-field]").forEach((cell) => {
      payload[cell.dataset.field] = cell.textContent.trim();
    });
    await fetch(`/api/invoices/${id}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    flashRow(row, "Saved");
  }

  if (e.target.classList.contains("approve-btn")) {
    await fetch(`/api/invoices/${id}/approve`, { method: "POST" });
    row.querySelector(".status-cell").textContent = "approved";
    row.className = "status-approved";
  }

  if (e.target.classList.contains("sync-btn")) {
    flashRow(row, "Syncing...");
    const res = await fetch(`/api/invoices/${id}/sync`, { method: "POST" });
    const data = await res.json();
    row.querySelector(".status-cell").textContent = `${data.status}${data.message ? " — " + data.message : ""}`;
    row.className = `status-${data.status}`;
  }
});

syncAllBtn.addEventListener("click", async () => {
  syncAllStatus.textContent = "Syncing all approved invoices...";
  const res = await fetch("/api/sync-all-approved", { method: "POST" });
  const data = await res.json();
  syncAllStatus.textContent = `Synced: ${data.synced}, Failed: ${data.failed}, Duplicates: ${data.duplicates}`;
  setTimeout(() => window.location.reload(), 1200);
});

function flashRow(row, message) {
  const cell = row.querySelector(".status-cell");
  const original = cell.textContent;
  cell.textContent = message;
  setTimeout(() => { if (cell.textContent === message) cell.textContent = original; }, 1500);
}
