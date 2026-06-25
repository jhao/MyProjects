function toast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 1800);
}

async function api(url, options = {}) {
  const opts = { headers: {}, ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "请求失败");
  return data;
}

function openModal(html) {
  const modal = document.getElementById("modal");
  modal.innerHTML = `<div class="modal-card">${html}</div>`;
  modal.classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

function bytes(size) {
  if (!size) return "0 MB";
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

document.addEventListener("click", async event => {
  if (event.target.id === "logoutBtn") {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/auth";
  }
  if (event.target.matches("[data-close-modal]")) closeModal();
});

