let usersCache = [];
let statusesCache = [];

async function bootAdmin() {
  const me = await api("/api/me");
  document.getElementById("meName").textContent = me.user?.nickname || me.user?.email || "当前账号";
  await Promise.all([loadUsers(), loadStatuses()]);
}

async function loadUsers() {
  const data = await api("/api/admin/users");
  usersCache = data.items;
  const totalProjects = data.items.reduce((sum, u) => sum + Number(u.project_count || 0), 0);
  const totalFiles = data.items.reduce((sum, u) => sum + Number(u.file_count || 0), 0);
  const totalDisk = data.items.reduce((sum, u) => sum + Number(u.disk_usage || 0), 0);
  document.getElementById("userTotal").textContent = data.items.length;
  document.getElementById("projectTotal").textContent = totalProjects;
  document.getElementById("fileTotal").textContent = totalFiles;
  document.getElementById("diskTotal").textContent = bytes(totalDisk);
  document.getElementById("userRows").innerHTML = data.items.map(u => `<tr>
    <td><strong>${esc(u.nickname)}</strong><br><span class="muted">${esc(u.email)}</span></td>
    <td>${esc(u.role)}</td>
    <td><span class="tag">${esc(u.status)}</span></td>
    <td>${u.project_count}</td>
    <td>${u.file_count}</td>
    <td>${bytes(u.disk_usage)}</td>
    <td>${esc(u.last_login_at || "")}</td>
    <td class="right"><div class="ops"><button class="text-btn" data-edit-user="${u.id}">编辑</button><button class="text-btn" data-reset-user="${u.id}">重置密码</button><button class="text-btn" data-toggle-user="${u.id}:${u.status === "active" ? "frozen" : "active"}">${u.status === "active" ? "冻结" : "启用"}</button></div></td>
  </tr>`).join("");
}

document.addEventListener("click", async event => {
  if (event.target.id === "newUserBtn") openUserForm();
  if (event.target.id === "newStatusBtn") openStatusForm();
  const uid = event.target.dataset.editUser;
  if (uid) openUserForm(uid);
  const statusId = event.target.dataset.editStatus;
  if (statusId) openStatusForm(statusId);
  const reset = event.target.dataset.resetUser;
  if (reset) {
    const ret = await api(`/api/admin/users/${reset}/reset-password`, { method: "POST", body: { password: "Reset123456" } });
    toast(`已重置：${ret.temporary_password}`);
  }
  const toggle = event.target.dataset.toggleUser;
  if (toggle) {
    const [id, status] = toggle.split(":");
    const user = usersCache.find(item => String(item.id) === String(id));
    await api(`/api/admin/users/${id}`, { method: "PUT", body: { email: user.email, nickname: user.nickname, role: user.role, status } });
    await loadUsers();
  }
});

async function openUserForm(id) {
  const user = usersCache.find(item => String(item.id) === String(id)) || {};
  openModal(`<h2>${id ? "编辑用户" : "新增用户"}</h2><form id="userForm" class="form-grid">
    <label>邮箱<input name="email" value="${esc(user.email || "")}" required></label>
    <label>昵称<input name="nickname" value="${esc(user.nickname || "")}" required></label>
    <label>角色<select name="role"><option value="user" selected>普通用户</option></select></label>
    <label>状态<select name="status"><option value="active" ${user.status === "active" ? "selected" : ""}>启用</option><option value="frozen" ${user.status === "frozen" ? "selected" : ""}>冻结</option></select></label>
    <label class="full">初始密码<input name="password" value="Init123456"></label>
    <div class="modal-actions full"><button type="button" class="secondary" data-close-modal>取消</button><button class="primary">保存</button></div>
  </form>`);
  document.getElementById("userForm").addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target));
    await api(id ? `/api/admin/users/${id}` : "/api/admin/users", { method: id ? "PUT" : "POST", body });
    closeModal();
    await loadUsers();
    toast("用户已保存");
  });
}

async function loadStatuses() {
  const data = await api("/api/admin/statuses");
  statusesCache = data.items;
  document.getElementById("statusRows").innerHTML = data.items.map(item => `<tr>
    <td><strong>${esc(item.name)}</strong></td>
    <td><span class="tag" style="background:${item.color}22;color:${item.color}">${esc(item.color)}</span></td>
    <td>${item.type === "control" ? "控制状态" : "业务状态"}</td>
    <td>${item.sort_order}</td>
    <td>${item.enabled ? "是" : "否"}</td>
    <td class="right"><button class="text-btn" data-edit-status="${item.id}">编辑</button></td>
  </tr>`).join("");
}

function openStatusForm(id) {
  const item = statusesCache.find(row => String(row.id) === String(id)) || {};
  openModal(`<h2>${id ? "编辑项目状态" : "新增项目状态"}</h2><form id="statusForm" class="form-grid">
    <label>状态名称<input name="name" value="${esc(item.name || "")}" required></label>
    <label>颜色<input name="color" type="color" value="${esc(item.color || "#2563eb")}"></label>
    <label>类型<select name="type"><option value="business" ${item.type !== "control" ? "selected" : ""}>业务状态</option><option value="control" ${item.type === "control" ? "selected" : ""}>控制状态</option></select></label>
    <label>排序<input name="sort_order" type="number" value="${esc(item.sort_order ?? 0)}"></label>
    <label>启用<select name="enabled"><option value="1" ${item.enabled !== 0 ? "selected" : ""}>启用</option><option value="0" ${item.enabled === 0 ? "selected" : ""}>停用</option></select></label>
    <div class="modal-actions full"><button type="button" class="secondary" data-close-modal>取消</button><button class="primary">保存</button></div>
  </form>`);
  document.getElementById("statusForm").addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target));
    await api(id ? `/api/admin/statuses/${id}` : "/api/admin/statuses", { method: id ? "PUT" : "POST", body });
    closeModal();
    await loadStatuses();
    toast("项目状态已保存");
  });
}

bootAdmin().catch(err => toast(err.message));
