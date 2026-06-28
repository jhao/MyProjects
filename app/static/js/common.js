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

function openPasswordForm() {
  openModal(`<h2>修改账号密码</h2><form id="passwordForm" class="form-grid">
    <label class="full">当前密码<input name="old_password" type="password" autocomplete="current-password" required></label>
    <label>新密码<input name="new_password" type="password" autocomplete="new-password" minlength="6" required></label>
    <label>确认新密码<input name="confirm_password" type="password" autocomplete="new-password" minlength="6" required></label>
    <div class="modal-actions full"><button type="button" class="secondary" data-close-modal>取消</button><button class="primary">保存</button></div>
  </form>`);
  document.getElementById("passwordForm").addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target));
    await api("/api/me/password", { method: "POST", body });
    closeModal();
    toast("密码已修改");
  });
}

document.addEventListener("click", async event => {
  if (event.target.id === "logoutBtn") {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/auth";
  }
  if (event.target.closest("#accountPasswordBtn")) {
    openPasswordForm();
  }
  if (event.target.matches("[data-close-modal]")) closeModal();
});
