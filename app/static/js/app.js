let state = { page: 1, perPage: 10, sort: "updated_at", direction: "desc", appliedFilters: null, project: null, categories: [], statuses: [], logDate: new Date().toISOString().slice(0, 10), logMonth: new Date(), logSnapshot: null, sourceMode: false, copiedFormat: null, selectedDirId: "root", expandedDirs: new Set(["root"]), metricsCollapsed: false, filtersCollapsed: false, selectedCategories: new Set(), selectedStatuses: new Set() };

async function boot() {
  const me = await api("/api/me");
  document.getElementById("meName").textContent = me.user?.nickname || "";
  applySavedPerPage();
  state.categories = (await api("/api/categories")).items;
  state.statuses = (await api("/api/statuses")).items;
  initMultiSelect("category", state.categories);
  initMultiSelect("status", state.statuses);
  state.appliedFilters = collectFilters();
  document.getElementById("perPage").addEventListener("change", async event => {
    savePerPage(event.target.value);
    state.page = 1;
    state.appliedFilters = collectFilters();
    await loadProjects();
  });
  bindCollapseHandlers();
  await loadProjects();
}

function initMultiSelect(type, items) {
  const selectEl = document.getElementById(`${type}Select`);
  const inputEl = document.getElementById(`${type}Input`);
  const dropdownEl = document.getElementById(`${type}Dropdown`);
  const clearEl = document.getElementById(`${type}Clear`);
  const tagsEl = document.getElementById(`${type}Tags`);
  const selectedSet = type === "category" ? state.selectedCategories : state.selectedStatuses;

  function renderDropdown() {
    dropdownEl.innerHTML = items.map(item => {
      const isSelected = selectedSet.has(String(item.id));
      return `<div class="multi-select-option ${isSelected ? "selected" : ""}" data-${type}-id="${item.id}">${esc(item.name)}</div>`;
    }).join("");
  }

  function renderTags() {
    const selectedNames = Array.from(selectedSet).map(id => {
      const item = items.find(i => String(i.id) === String(id));
      return item ? item.name : "";
    }).filter(Boolean);
    tagsEl.innerHTML = "";
    inputEl.value = selectedNames.join("，");
    inputEl.title = selectedNames.join("，");
    inputEl.placeholder = selectedSet.size > 0 ? "" : "全部数据";
    inputEl.classList.toggle("has-value", selectedSet.size > 0);
  }

  function toggleDropdown(show) {
    dropdownEl.classList.toggle("open", show);
  }

  selectEl.addEventListener("click", event => {
    if (event.target.closest(".multi-select-tag .remove") || event.target.closest(".multi-select-clear")) return;
    const isOpen = dropdownEl.classList.contains("open");
    document.querySelectorAll(".multi-select-dropdown.open").forEach(el => el.classList.remove("open"));
    if (!isOpen) {
      renderDropdown();
      toggleDropdown(true);
    }
  });

  dropdownEl.addEventListener("click", event => {
    event.stopPropagation();
    const option = event.target.closest(`.multi-select-option[data-${type}-id]`);
    if (!option) return;
    const id = String(option.getAttribute(`data-${type}-id`));
    if (selectedSet.has(id)) {
      selectedSet.delete(id);
    } else {
      selectedSet.add(id);
    }
    renderTags();
    renderDropdown();
    toggleDropdown(true);
  });

  tagsEl.addEventListener("click", event => {
    const removeBtn = event.target.closest(`[data-${type}-remove]`);
    if (!removeBtn) return;
    const id = String(removeBtn.dataset[`${type}Remove`]);
    selectedSet.delete(id);
    renderTags();
    renderDropdown();
    toggleDropdown(true);
  });

  clearEl.addEventListener("click", event => {
    event.stopPropagation();
    selectedSet.clear();
    renderTags();
    renderDropdown();
    toggleDropdown(true);
  });

  renderDropdown();
  renderTags();
}

function bindCollapseHandlers() {
  const toggleMetrics = document.getElementById("toggleMetrics");
  const toggleFilters = document.getElementById("toggleFilters");
  if (toggleMetrics) {
    toggleMetrics.addEventListener("click", () => {
      state.metricsCollapsed = !state.metricsCollapsed;
      document.getElementById("metricsSection").classList.toggle("collapsed", state.metricsCollapsed);
      toggleMetrics.textContent = state.metricsCollapsed ? "▶" : "▼";
      updateMetricsSummary();
    });
  }
  if (toggleFilters) {
    toggleFilters.addEventListener("click", () => {
      state.filtersCollapsed = !state.filtersCollapsed;
      document.getElementById("filtersSection").classList.toggle("collapsed", state.filtersCollapsed);
      toggleFilters.textContent = state.filtersCollapsed ? "▶" : "▼";
      updateFiltersSummary();
    });
  }
}

function updateMetricsSummary() {
  const el = document.getElementById("metricsSummary");
  if (!el) return;
  if (!state.metricsCollapsed) { el.textContent = ""; return; }
  const total = document.getElementById("metricTotal").textContent;
  const filtered = document.getElementById("metricFiltered").textContent;
  el.innerHTML = `共 <strong>${total}</strong> 个项目，已筛选 <strong>${filtered}</strong> 个`;
}

function updateFiltersSummary() {
  const el = document.getElementById("filtersSummary");
  if (!el) return;
  if (!state.filtersCollapsed) { el.textContent = ""; return; }
  const chips = [];
  const q = document.getElementById("q").value.trim();
  if (q) chips.push(`关键词: ${q}`);
  const folder = document.getElementById("folder").value.trim();
  if (folder) chips.push(`目录: ${folder}`);
  const cats = Array.from(state.selectedCategories);
  if (cats.length) {
    const names = cats.map(id => state.categories.find(c => String(c.id) === String(id))?.name || id);
    chips.push(`分类: ${names.join(", ")}`);
  }
  const stats = Array.from(state.selectedStatuses);
  if (stats.length) {
    const names = stats.map(id => state.statuses.find(s => String(s.id) === String(id))?.name || id);
    chips.push(`状态: ${names.join(", ")}`);
  }
  const startFrom = document.getElementById("startFrom").value;
  const startTo = document.getElementById("startTo").value;
  if (startFrom || startTo) chips.push(`启动日期: ${startFrom || "..."} ~ ${startTo || "..."}`);
  const updatedFrom = document.getElementById("updatedFrom").value;
  const updatedTo = document.getElementById("updatedTo").value;
  if (updatedFrom || updatedTo) chips.push(`更新日期: ${updatedFrom || "..."} ~ ${updatedTo || "..."}`);
  if (!chips.length) { el.textContent = "无筛选条件"; return; }
  el.innerHTML = chips.map(c => `<span class="chip">${esc(c)}</span>`).join("");
}

function collectFilters() {
  const params = new URLSearchParams({
    page: state.page,
    per_page: document.getElementById("perPage").value,
    sort: state.sort,
    direction: state.direction,
  });
  const map = { q: "q", folder: "folder", startFrom: "start_from", startTo: "start_to", updatedFrom: "updated_from", updatedTo: "updated_to" };
  Object.entries(map).forEach(([id, key]) => {
    const value = document.getElementById(id).value;
    if (value) params.append(key, value);
  });
  Array.from(state.selectedCategories).forEach(v => params.append("category_ids", v));
  Array.from(state.selectedStatuses).forEach(v => params.append("status_ids", v));
  return params;
}

async function loadProjects() {
  if (!state.appliedFilters) state.appliedFilters = collectFilters();
  state.appliedFilters.set("page", state.page);
  state.appliedFilters.set("per_page", document.getElementById("perPage").value);
  state.appliedFilters.set("sort", state.sort);
  state.appliedFilters.set("direction", state.direction);
  const data = await api(`/api/projects?${state.appliedFilters}`);
  state.page = data.page;
  state.total = data.total;
  state.perPage = data.per_page;
  document.getElementById("metricTotal").textContent = data.total;
  document.getElementById("metricFiltered").textContent = data.total;
  document.getElementById("metricPage").textContent = data.page;
  renderCategoryAmountStats(data.category_amounts || []);
  document.getElementById("pageInfo").textContent = `共 ${data.total} 个项目，当前第 ${data.page} 页`;
  updatePager(data);
  updateMetricsSummary();
  updateFiltersSummary();
  const rows = document.getElementById("projectRows");
  rows.innerHTML = data.items.map(projectRow).join("");
}

function renderCategoryAmountStats(items) {
  const el = document.getElementById("categoryAmountStats");
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<span class="muted">当前筛选无分类金额统计</span>';
    return;
  }
  el.innerHTML = items.map(item => `<div class="category-metric">
    <span class="category-dot" style="background:${esc(item.category_color || "#64748b")}"></span>
    <strong>${esc(item.category_name || "未分类")}</strong>
    <span>合同 <b class="amount-contract">${formatMoney(item.contract_amount)}</b></span>
    <span>开票 <b class="amount-invoice">${formatMoney(item.invoiced_amount)}</b></span>
    <span>回款 <b class="amount-receive">${formatMoney(item.received_amount)}</b></span>
  </div>`).join("");
}

function projectRow(p) {
  const total = Number(p.milestone_total || 0);
  const done = Number(p.milestone_done || 0);
  const pct = total ? Math.round(done * 100 / total) : 0;
  return `<tr>
    <td><button class="project-link" data-open="${p.id}">${esc(p.name)}</button><br><span class="muted">${esc(p.description || "")}</span></td>
    <td>${esc(p.folder)}</td>
    <td><span class="tag" style="background:${p.category_color}22;color:${p.category_color}">${esc(p.category_name || "")}</span></td>
    <td>${esc(p.start_date || "")}</td>
    <td>${p.statuses.map(s => `<span class="tag" style="background:${s.color}22;color:${s.color}">${esc(s.name)}</span>`).join("")}${p.is_frozen ? '<span class="tag">冻结</span>' : ""}</td>
    <td>${amountBlock(p)}</td>
    <td>${esc((p.updated_at || "").slice(0, 10))}</td>
    <td>${logSnippet(p.latest_log_text || "")}</td>
    <td><strong>${esc(p.next_node_date || "")}</strong><br>${esc(p.next_node || "")}</td>
    <td>${done}/${total}<div class="progress"><div class="bar" style="width:${pct}%"></div></div></td>
    <td class="right"><div class="ops">
      ${p.is_frozen ? `<button class="text-btn" data-state="${p.id}:start">启动</button>` : `<button class="text-btn" data-state="${p.id}:freeze">冻结</button>`}
      <button class="text-btn" data-edit="${p.id}">编辑</button>
      <button class="text-btn" data-state="${p.id}:delete">删除</button>
    </div></td>
  </tr>`;
}

function amountBlock(p) {
  return `<div class="amount-row">
    <span class="amount-contract">${formatMoney(p.contract_amount)}</span>
    <span class="amount-invoice">${formatMoney(p.invoiced_amount)}</span>
    <span class="amount-receive">${formatMoney(p.received_amount)}</span>
  </div>`;
}

function formatMoney(value) {
  const number = Number(value || 0);
  return number.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function updatePager(data) {
  const totalPages = Math.max(Math.ceil(Number(data.total || 0) / Number(data.per_page || 10)), 1);
  document.getElementById("prevPage").disabled = Number(data.page) <= 1;
  document.getElementById("nextPage").disabled = Number(data.page) >= totalPages;
}

function applySavedPerPage() {
  const saved = localStorage.getItem("mpj_per_page") || readCookie("mpj_per_page");
  if (saved && ["10", "20", "50", "100"].includes(saved)) {
    document.getElementById("perPage").value = saved;
  }
}

function savePerPage(value) {
  localStorage.setItem("mpj_per_page", value);
  document.cookie = `mpj_per_page=${encodeURIComponent(value)}; path=/; max-age=31536000`;
}

function readCookie(name) {
  return document.cookie.split("; ").find(row => row.startsWith(`${name}=`))?.split("=")[1];
}

function logSnippet(text) {
  const plain = cleanPlainText(text || "");
  if (!plain) return '<span class="muted">无</span>';
  return `<div class="log-snippet">${esc(plain.slice(0, 20))}${plain.length > 20 ? "..." : ""}<div class="floating">${esc(plain)}</div></div>`;
}

document.addEventListener("click", async event => {
  // 点击外部关闭下拉框
  if (!event.target.closest(".multi-select")) {
    document.querySelectorAll(".multi-select-dropdown.open").forEach(el => el.classList.remove("open"));
  }

  const openId = event.target.dataset.open;
  if (openId) openProject(openId);
  const editId = event.target.dataset.edit;
  if (editId) openProjectForm(editId);
  const stateAction = event.target.dataset.state;
  if (stateAction) {
    const [id, action] = stateAction.split(":");
    if (action === "delete" && !confirm("确定要逻辑删除该项目吗？")) return;
    await api(`/api/projects/${id}/state`, { method: "POST", body: { action } });
    toast("操作成功");
    loadProjects();
  }
  if (event.target.id === "newProjectBtn") openProjectForm();
  if (event.target.id === "searchBtn") {
    state.page = 1;
    state.appliedFilters = collectFilters();
    await loadProjects();
    toast("已按当前条件检索");
  }
  if (event.target.id === "exportBtn") {
    state.appliedFilters = state.appliedFilters || collectFilters();
    window.location.href = `/api/projects/export?${state.appliedFilters}`;
  }
  if (event.target.id === "resetFilters") {
    ["q", "folder", "startFrom", "startTo", "updatedFrom", "updatedTo"].forEach(id => document.getElementById(id).value = "");
    state.selectedCategories.clear();
    state.selectedStatuses.clear();
    document.querySelectorAll(".multi-select-tags").forEach(el => el.innerHTML = "");
    document.querySelectorAll(".multi-select-placeholder").forEach(el => {
      el.value = "";
      el.title = "";
      el.placeholder = "全部数据";
      el.classList.remove("has-value");
    });
    state.page = 1;
    toast("筛选条件已重置，请点击检索");
  }
  if (event.target.id === "prevPage" && !event.target.disabled && state.page > 1) { state.page--; loadProjects(); }
  if (event.target.id === "nextPage" && !event.target.disabled) { state.page++; loadProjects(); }
  if (event.target.id === "closeDrawer") closeDrawer();
  if (event.target.matches(".drawer-tabs button")) switchTab(event.target.dataset.tab);
  const saveMilestoneId = event.target.dataset.saveMile;
  if (saveMilestoneId) {
    const form = event.target.closest(".milestone-row");
    const body = Object.fromEntries(new FormData(form));
    body.sort_order = [...document.querySelectorAll("#milestoneList .milestone-row")].indexOf(form);
    await api(`/api/milestones/${saveMilestoneId}`, { method: "PUT", body });
    await loadMilestones();
    await loadProjects();
    toast("里程碑已保存");
  }
  const deleteMilestoneId = event.target.dataset.delMile;
  if (deleteMilestoneId) {
    if (!confirm("确定要删除该里程碑吗？")) return;
    await api(`/api/milestones/${deleteMilestoneId}`, { method: "DELETE" });
    await loadMilestones();
    await loadProjects();
    toast("里程碑已删除");
  }
  const sort = event.target.dataset.sort;
  if (sort) {
    state.direction = state.sort === sort && state.direction === "asc" ? "desc" : "asc";
    state.sort = sort;
    document.querySelectorAll(".sort").forEach(btn => btn.classList.remove("asc", "desc"));
    event.target.classList.add(state.direction);
    loadProjects();
  }
});

async function openProject(id) {
  const data = await api(`/api/projects/${id}`);
  state.project = data.project;
  state.selectedDirId = "root";
  state.expandedDirs = new Set(["root"]);
  document.getElementById("drawerTitle").textContent = state.project.name;
  document.getElementById("drawerMeta").textContent = `${state.project.folder} / 下一步：${state.project.next_node_date || ""} ${state.project.next_node || ""}`;
  document.getElementById("drawer").classList.add("open");
  document.getElementById("drawerOverlay").addEventListener("click", handleDrawerOverlay);
  await loadMilestones();
  await loadLogs();
  await loadDocuments();
  await loadPeople();
}

function closeDrawer() {
  document.getElementById("drawer").classList.remove("open");
}

function handleDrawerOverlay(event) {
  if (event.target.id === "drawerOverlay") {
    closeDrawer();
  }
}

function switchTab(tab) {
  document.querySelectorAll(".drawer-tabs button").forEach(btn => btn.classList.toggle("active", btn.dataset.tab === tab));
  document.querySelectorAll(".tab-body").forEach(body => body.classList.add("hidden"));
  document.getElementById(`tab-${tab}`).classList.remove("hidden");
}

async function openProjectForm(id) {
  const p = id ? (await api(`/api/projects/${id}`)).project : {};
  const milestones = id ? (await api(`/api/projects/${id}/milestones`)).items : [];
  openModal(`<h2>${id ? "编辑项目" : "新建项目"}</h2>
    <form id="projectForm" class="form-grid">
      <label>项目名称<input name="name" value="${esc(p.name || "")}" required></label>
      <label>所属目录<input name="folder" value="${esc(p.folder || "")}" required></label>
      <label>分类<select name="category_id">${state.categories.map(c => `<option value="${c.id}" ${p.category_id == c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
      <label>状态<select name="status_ids" multiple>${state.statuses.map(s => `<option value="${s.id}" ${(p.statuses || []).some(x => x.id === s.id) ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
      <label>启动日期<input name="start_date" type="date" value="${esc(p.start_date || "")}"></label>
      <label>合同额<input name="contract_amount" type="number" min="0" step="0.01" value="${esc(p.contract_amount ?? 0)}"></label>
      <label>已开票金额<input name="invoiced_amount" type="number" min="0" step="0.01" value="${esc(p.invoiced_amount ?? 0)}"></label>
      <label>已回款金额<input name="received_amount" type="number" min="0" step="0.01" value="${esc(p.received_amount ?? 0)}"></label>
      <label>下一步节点<select name="next_milestone_id"><option value="">无</option>${milestones.map(m => `<option value="${m.id}" data-name="${esc(m.name || "")}" data-date="${esc(m.plan_date || "")}" ${p.next_node === m.name ? "selected" : ""}>${esc(m.plan_date || "")} ${esc(m.name || "")}</option>`).join("")}</select></label>
      <label class="full">说明<textarea name="description">${esc(p.description || "")}</textarea></label>
      <div class="modal-actions full"><button type="button" class="secondary" data-close-modal>取消</button><button class="primary">保存</button></div>
    </form>`);
  document.getElementById("projectForm").addEventListener("submit", async event => {
    event.preventDefault();
    const fd = new FormData(event.target);
    const body = Object.fromEntries(fd);
    body.status_ids = Array.from(event.target.elements.status_ids.selectedOptions).map(o => o.value);
    const nextOption = event.target.elements.next_milestone_id.selectedOptions[0];
    body.next_node = nextOption?.dataset.name || "";
    body.next_node_date = nextOption?.dataset.date || "";
    delete body.next_milestone_id;
    await api(id ? `/api/projects/${id}` : "/api/projects", { method: id ? "PUT" : "POST", body });
    closeModal();
    await loadProjects();
    toast("项目已保存");
  });
}

async function loadMilestones() {
  const data = await api(`/api/projects/${state.project.id}/milestones`);
  document.getElementById("tab-milestones").innerHTML = `<div class="box">
    <h3>里程碑</h3>
    <div id="milestoneList" class="milestone-list">
      ${data.items.map(milestoneRow).join("")}
    </div>
    <form id="milestoneForm" class="milestone-form">
      <input name="name" placeholder="里程碑名称" required>
      <input name="plan_date" type="date" title="计划日期">
      <input name="completed_date" type="date" title="完成日期">
      <select name="status"><option>未开始</option><option>进行中</option><option>已完成</option><option>延期</option></select>
      <input name="owner" placeholder="负责人">
      <button class="primary">新增</button>
    </form>
  </div>`;
  bindMilestoneDrag();
  document.getElementById("milestoneForm").addEventListener("submit", async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.target));
    body.sort_order = document.querySelectorAll("#milestoneList .milestone-row").length;
    await api(`/api/projects/${state.project.id}/milestones`, { method: "POST", body });
    loadMilestones();
  });
}

function milestoneRow(m) {
  return `<form class="milestone-row" draggable="true" data-mile-row="${m.id}">
    <span class="drag-handle" title="拖拽排序">⋮⋮</span>
    <input name="name" value="${esc(m.name || "")}" required>
    <input name="plan_date" type="date" value="${esc(m.plan_date || "")}">
    <input name="completed_date" type="date" value="${esc(m.completed_date || "")}">
    <select name="status">
      ${["未开始", "进行中", "已完成", "延期"].map(item => `<option ${m.status === item ? "selected" : ""}>${item}</option>`).join("")}
    </select>
    <input name="owner" value="${esc(m.owner || "")}" placeholder="负责人">
    <div class="ops">
      <button type="button" class="text-btn" data-save-mile="${m.id}">保存</button>
      <button type="button" class="text-btn" data-del-mile="${m.id}">删除</button>
    </div>
  </form>`;
}

function bindMilestoneDrag() {
  const list = document.getElementById("milestoneList");
  let dragging = null;
  list.querySelectorAll(".milestone-row").forEach(row => {
    row.addEventListener("dragstart", event => {
      dragging = row;
      row.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
    });
    row.addEventListener("dragend", async () => {
      row.classList.remove("dragging");
      dragging = null;
      await saveMilestoneOrder();
    });
  });
  list.addEventListener("dragover", event => {
    event.preventDefault();
    const after = getDragAfterElement(list, event.clientY);
    if (!dragging) return;
    if (after == null) list.appendChild(dragging);
    else list.insertBefore(dragging, after);
  });
}

function getDragAfterElement(container, y) {
  const rows = [...container.querySelectorAll(".milestone-row:not(.dragging)")];
  return rows.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) return { offset, element: child };
    return closest;
  }, { offset: Number.NEGATIVE_INFINITY }).element;
}

async function saveMilestoneOrder() {
  const item_ids = [...document.querySelectorAll("#milestoneList .milestone-row")].map(row => row.dataset.mileRow);
  await api(`/api/projects/${state.project.id}/milestones/reorder`, { method: "POST", body: { item_ids } });
  await loadProjects();
  toast("里程碑排序已保存");
}

async function loadLogs() {
  state.sourceMode = false;
  const logs = await api(`/api/projects/${state.project.id}/logs`);
  const logMap = Object.fromEntries(logs.items.map(item => [item.log_date, item]));
  const dayData = await api(`/api/projects/${state.project.id}/logs?date=${state.logDate}`);
  document.getElementById("tab-logs").innerHTML = `<div class="log-layout">
    <aside class="log-side">
      <div class="calendar-head">
        <button class="secondary small" type="button" data-log-month="-1">上月</button>
        <button class="month-title" type="button" id="monthTitle">${state.logMonth.getFullYear()}-${String(state.logMonth.getMonth() + 1).padStart(2, "0")}</button>
        <button class="secondary small" type="button" data-log-month="1">下月</button>
      </div>
      <div id="monthPicker" class="month-picker hidden">
        <select id="logYearSelect">${Array.from({ length: 11 }, (_, i) => state.logMonth.getFullYear() - 5 + i).map(y => `<option ${y === state.logMonth.getFullYear() ? "selected" : ""}>${y}</option>`).join("")}</select>
        <select id="logMonthSelect">${Array.from({ length: 12 }, (_, i) => `<option value="${i}" ${i === state.logMonth.getMonth() ? "selected" : ""}>${i + 1}月</option>`).join("")}</select>
        <button class="secondary small" type="button" id="applyMonth">切换</button>
      </div>
      <div class="calendar-grid">${renderCalendar(logMap)}</div>
      <div class="log-search">
        <input id="logSearchInput" placeholder="检索日志标题或内容">
        <div id="logSearchResults" class="log-results"></div>
      </div>
    </aside>
    <section class="log-main">
      <h3>${esc(state.logDate)} 项目日志</h3>
      <form id="logForm">
        <input name="title" id="logTitle" placeholder="日志标题" value="${esc(dayData.item?.title || "")}">
        <div class="editor-toolbar">
          <select data-font-name><option value="">字体</option><option value="Arial">Arial</option><option value="Microsoft YaHei">微软雅黑</option><option value="SimSun">宋体</option><option value="KaiTi">楷体</option></select>
          <select data-font-size><option value="">字号</option><option value="2">小</option><option value="3">正文</option><option value="4">中</option><option value="5">大</option><option value="6">特大</option></select>
          <input type="color" data-fore-color title="字体颜色">
          <button type="button" data-cmd="bold">B</button>
          <button type="button" data-cmd="italic">I</button>
          <button type="button" data-cmd="insertUnorderedList">列表</button>
          <button type="button" data-cmd="insertOrderedList">编号</button>
          <button type="button" data-cmd="formatBlock" data-value="blockquote">引用</button>
          <button type="button" data-cmd="createLink">链接</button>
          <button type="button" id="copyFormat">格式刷</button>
          <button type="button" data-cmd="removeFormat">清除格式</button>
          <button type="button" id="toggleSource">源码</button>
        </div>
        <div id="logEditor" class="rich-editor" contenteditable="true">${dayData.item?.content || ""}</div>
        <textarea id="logSource" class="source-editor hidden"></textarea>
        <div class="modal-actions"><button id="saveLogBtn" class="primary" disabled>保存日志</button></div>
      </form>
    </section>
  </div>`;
  state.logSnapshot = getLogDraft();
  bindLogEvents();
}

function renderCalendar(logMap) {
  const year = state.logMonth.getFullYear();
  const month = state.logMonth.getMonth();
  const today = new Date().toISOString().slice(0, 10);
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  const weeks = ["日", "一", "二", "三", "四", "五", "六"].map(w => `<div class="calendar-week">${w}</div>`);
  const days = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const iso = toDateString(d);
    const inMonth = d.getMonth() === month;
    const status = iso > today ? "future" : logMap[iso] && cleanPlainText(logMap[iso].plain_text || logMap[iso].content || "") ? "done" : "missing";
    days.push(`<button type="button" class="calendar-day ${inMonth ? "" : "out-month"} ${iso === state.logDate ? "active" : ""}" data-log-date="${iso}">
      <span>${d.getDate()}</span><span class="dot ${status}"></span>
    </button>`);
  }
  return weeks.concat(days).join("");
}

function toDateString(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function bindLogEvents() {
  document.querySelectorAll("[data-log-date]").forEach(btn => btn.addEventListener("click", async () => {
    state.logDate = btn.dataset.logDate;
    state.logMonth = new Date(`${state.logDate}T00:00:00`);
    await loadLogs();
  }));
  document.querySelectorAll("[data-log-month]").forEach(btn => btn.addEventListener("click", async () => {
    state.logMonth.setMonth(state.logMonth.getMonth() + Number(btn.dataset.logMonth));
    await loadLogs();
  }));
  document.getElementById("monthTitle").addEventListener("click", () => document.getElementById("monthPicker").classList.toggle("hidden"));
  document.getElementById("applyMonth").addEventListener("click", async () => {
    state.logMonth = new Date(Number(document.getElementById("logYearSelect").value), Number(document.getElementById("logMonthSelect").value), 1);
    state.logDate = toDateString(new Date(state.logMonth.getFullYear(), state.logMonth.getMonth(), 1));
    await loadLogs();
  });
  document.querySelector("[data-font-name]").addEventListener("change", event => runEditorCommand("fontName", event.target.value));
  document.querySelector("[data-font-size]").addEventListener("change", event => runEditorCommand("fontSize", event.target.value));
  document.querySelector("[data-fore-color]").addEventListener("input", event => runEditorCommand("foreColor", event.target.value));
  document.querySelectorAll("[data-cmd]").forEach(btn => btn.addEventListener("click", () => {
    const cmd = btn.dataset.cmd;
    if (cmd === "createLink") {
      const url = prompt("请输入链接地址");
      if (url) runEditorCommand(cmd, url);
    } else {
      runEditorCommand(cmd, btn.dataset.value || null);
    }
  }));
  document.getElementById("copyFormat").addEventListener("click", copyCurrentFormat);
  document.getElementById("logEditor").addEventListener("mouseup", applyCopiedFormat);
  document.getElementById("toggleSource").addEventListener("click", toggleLogSource);
  document.getElementById("logTitle").addEventListener("input", markLogDirty);
  document.getElementById("logEditor").addEventListener("input", markLogDirty);
  document.getElementById("logSource").addEventListener("input", markLogDirty);
  document.getElementById("logForm").addEventListener("submit", async event => {
    event.preventDefault();
    const draft = getLogDraft();
    await api(`/api/projects/${state.project.id}/logs`, { method: "POST", body: { log_date: state.logDate, title: draft.title, content: draft.content } });
    state.logSnapshot = draft;
    markLogDirty();
    await loadProjects();
    await loadLogs();
    toast("日志已保存");
  });
  let searchTimer;
  document.getElementById("logSearchInput").addEventListener("input", event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => searchLogs(event.target.value), 250);
  });
}

function getLogDraft() {
  if (state.sourceMode) {
    return {
      title: document.getElementById("logTitle")?.value || "",
      content: document.getElementById("logSource")?.value || "",
    };
  }
  return {
    title: document.getElementById("logTitle")?.value || "",
    content: document.getElementById("logEditor")?.innerHTML || "",
  };
}

function runEditorCommand(cmd, value) {
  if (state.sourceMode) toggleLogSource();
  document.getElementById("logEditor").focus();
  document.execCommand(cmd, false, value);
  markLogDirty();
}

function toggleLogSource() {
  const editor = document.getElementById("logEditor");
  const source = document.getElementById("logSource");
  if (!state.sourceMode) {
    source.value = editor.innerHTML;
    editor.classList.add("hidden");
    source.classList.remove("hidden");
    state.sourceMode = true;
  } else {
    editor.innerHTML = source.value;
    source.classList.add("hidden");
    editor.classList.remove("hidden");
    state.sourceMode = false;
  }
  markLogDirty();
}

function copyCurrentFormat() {
  const selection = window.getSelection();
  const node = selection && selection.anchorNode ? (selection.anchorNode.nodeType === 1 ? selection.anchorNode : selection.anchorNode.parentElement) : null;
  const style = node ? getComputedStyle(node) : null;
  state.copiedFormat = style ? { fontFamily: style.fontFamily, fontSize: style.fontSize, color: style.color, fontWeight: style.fontWeight, fontStyle: style.fontStyle } : null;
  toast(state.copiedFormat ? "已复制当前文字格式，请选择目标文字" : "请先选中一段文字");
}

function applyCopiedFormat() {
  if (!state.copiedFormat) return;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) return;
  const span = document.createElement("span");
  span.style.fontFamily = state.copiedFormat.fontFamily;
  span.style.fontSize = state.copiedFormat.fontSize;
  span.style.color = state.copiedFormat.color;
  span.style.fontWeight = state.copiedFormat.fontWeight;
  span.style.fontStyle = state.copiedFormat.fontStyle;
  span.appendChild(selection.getRangeAt(0).extractContents());
  selection.getRangeAt(0).insertNode(span);
  state.copiedFormat = null;
  markLogDirty();
}

function markLogDirty() {
  const draft = getLogDraft();
  const dirty = !state.logSnapshot || draft.title !== state.logSnapshot.title || draft.content !== state.logSnapshot.content;
  const btn = document.getElementById("saveLogBtn");
  if (btn) btn.disabled = !dirty;
}

async function searchLogs(keyword) {
  const box = document.getElementById("logSearchResults");
  if (!keyword.trim()) {
    box.innerHTML = "";
    return;
  }
  const data = await api(`/api/projects/${state.project.id}/logs?q=${encodeURIComponent(keyword.trim())}`);
  box.innerHTML = data.items.length ? data.items.map(item => `<button type="button" class="log-result" data-log-date="${item.log_date}">
    <strong>${esc(item.log_date)}</strong><br>${esc(item.title || "未命名日志")}<br><span class="muted">${esc((item.plain_text || "").slice(0, 60))}</span>
  </button>`).join("") : `<span class="muted">没有匹配的日志</span>`;
  box.querySelectorAll("[data-log-date]").forEach(btn => btn.addEventListener("click", async () => {
    state.logDate = btn.dataset.logDate;
    state.logMonth = new Date(`${state.logDate}T00:00:00`);
    await loadLogs();
  }));
}

function cleanPlainText(html) {
  const el = document.createElement("div");
  el.innerHTML = html;
  return (el.textContent || el.innerText || "").trim();
}

async function loadDocuments() {
  const dirs = await api(`/api/projects/${state.project.id}/dirs`);
  if (!state.selectedDirId) state.selectedDirId = "root";
  if (state.selectedDirId !== "root" && dirs.items.length && !dirs.items.some(d => String(d.id) === String(state.selectedDirId))) state.selectedDirId = "root";
  if (dirs.items.length && state.expandedDirs.size === 0) dirs.items.filter(d => !d.parent_id).forEach(d => state.expandedDirs.add(String(d.id)));
  const docs = await api(`/api/projects/${state.project.id}/documents?dir_id=${state.selectedDirId}`);
  const selected = dirs.items.find(d => String(d.id) === String(state.selectedDirId));
  document.getElementById("tab-documents").innerHTML = `<div class="doc-layout">
    <aside class="log-side">
      <h3>文档目录</h3>
      <div class="dir-tree">${renderRootDir(dirs.items)}${state.expandedDirs.has("root") ? renderDirTree(dirs.items) : ""}</div>
    </aside>
    <section class="log-main">
      <h3>${esc(state.selectedDirId === "root" ? "根目录" : selected?.name || "文档")} 文件列表</h3>
      <table class="file-table"><thead><tr><th>文件名</th><th>大小</th><th>索引</th><th class="right">操作</th></tr></thead><tbody>
        ${docs.items.map(d => `<tr><td>${esc(d.original_name)}</td><td>${bytes(d.size_bytes)}</td><td>${esc(d.index_status)}</td><td class="right"><div class="ops"><button class="text-btn" data-preview-doc="${d.id}" data-name="${esc(d.original_name)}" data-type="${esc(d.file_type || "")}">预览</button><button class="text-btn" data-move-doc="${d.id}">移动</button><button class="text-btn" data-del-doc="${d.id}">删除</button></div></td></tr>`).join("") || `<tr><td colspan="4" class="muted">当前目录暂无文件</td></tr>`}
      </tbody></table>
      <form id="uploadForm" class="form-grid"><input name="files" type="file" multiple><button class="primary">上传到当前目录</button></form>
    </section>
  </div>`;
  bindDocumentEvents(dirs.items);
  document.getElementById("uploadForm").addEventListener("submit", async event => {
    event.preventDefault();
    const fd = new FormData(event.target);
    if (state.selectedDirId !== "root") fd.append("dir_id", state.selectedDirId);
    await api(`/api/projects/${state.project.id}/documents`, { method: "POST", body: fd });
    toast("文件已上传");
    await loadDocuments();
  });
}

function renderRootDir(items) {
  const expanded = state.expandedDirs.has("root");
  const active = state.selectedDirId === "root";
  return `<div class="dir-row ${active ? "active" : ""}">
    <button type="button" class="dir-toggle" data-toggle-dir="root">${expanded ? "▾" : "▸"}</button>
    <button type="button" class="dir-name" data-select-dir="root">📁 根目录</button>
    <span class="dir-actions"><button class="text-btn" data-add-dir="root">新建</button></span>
  </div>`;
}

function renderDirTree(items, parentId = null, level = 0) {
  return items.filter(item => String(item.parent_id || "") === String(parentId || "")).map(item => {
    const children = items.filter(child => String(child.parent_id || "") === String(item.id));
    const expanded = state.expandedDirs.has(String(item.id));
    const active = String(item.id) === String(state.selectedDirId);
    return `<div>
      <div class="dir-row ${active ? "active" : ""}" style="padding-left:${level * 16 + 5}px">
        <button type="button" class="dir-toggle" data-toggle-dir="${item.id}">${children.length ? (expanded ? "▾" : "▸") : ""}</button>
        <button type="button" class="dir-name" data-select-dir="${item.id}">📁 ${esc(item.name)}</button>
        <span class="dir-actions"><button class="text-btn" data-add-dir="${item.id}">新建</button><button class="text-btn" data-move-dir="${item.id}">移动</button><button class="text-btn" data-del-dir="${item.id}">删除</button></span>
      </div>
      ${expanded ? renderDirTree(items, item.id, level + 1) : ""}
    </div>`;
  }).join("");
}

function bindDocumentEvents(dirs) {
  const tree = document.querySelector("#tab-documents .dir-tree");
  tree.addEventListener("click", async event => {
    const target = event.target;
    if (target.dataset.toggleDir) {
      const id = String(target.dataset.toggleDir);
      if (state.expandedDirs.has(id)) state.expandedDirs.delete(id);
      else state.expandedDirs.add(id);
      await loadDocuments();
      return;
    }
    if (target.dataset.selectDir) {
      state.selectedDirId = target.dataset.selectDir;
      state.expandedDirs.add(String(state.selectedDirId));
      await loadDocuments();
      return;
    }
    if (target.dataset.addDir) {
      const name = prompt("请输入新目录名称");
      if (!name) return;
      await api(`/api/projects/${state.project.id}/dirs`, { method: "POST", body: { name, parent_id: target.dataset.addDir === "root" ? "" : target.dataset.addDir } });
      state.expandedDirs.add(String(target.dataset.addDir));
      await loadDocuments();
      return;
    }
    if (target.dataset.moveDir) {
      openDirMoveModal(target.dataset.moveDir, dirs);
      return;
    }
    if (target.dataset.delDir) {
      if (!confirm("确定删除该目录及目录下文件吗？")) return;
      await api(`/api/dirs/${target.dataset.delDir}`, { method: "DELETE" });
      state.selectedDirId = "root";
      await loadDocuments();
    }
  });
  document.querySelectorAll("[data-preview-doc]").forEach(btn => btn.addEventListener("click", () => openDocPreview(btn.dataset.previewDoc, btn.dataset.name, btn.dataset.type)));
  document.querySelectorAll("[data-move-doc]").forEach(btn => btn.addEventListener("click", () => openDocMoveModal(btn.dataset.moveDoc, dirs)));
  document.querySelectorAll("[data-del-doc]").forEach(btn => btn.addEventListener("click", async () => {
    if (!confirm("确定删除该文件吗？")) return;
    await api(`/api/documents/${btn.dataset.delDoc}`, { method: "DELETE" });
    await loadDocuments();
  }));
}

function dirOptions(dirs, selectedId = "", excludeId = "") {
  return `<option value="root" ${selectedId === "root" || selectedId === "" ? "selected" : ""}>根目录</option>` + dirs.filter(d => String(d.id) !== String(excludeId)).map(d => `<option value="${d.id}" ${String(d.id) === String(selectedId) ? "selected" : ""}>${esc(d.name)}</option>`).join("");
}

function openDirMoveModal(dirId, dirs) {
  const dir = dirs.find(d => String(d.id) === String(dirId));
  openModal(`<h2>移动目录</h2><form id="moveDirForm"><label>目录名称<input name="name" value="${esc(dir.name)}"></label><label>移动到<select name="parent_id">${dirOptions(dirs, dir.parent_id || "", dirId)}</select></label><div class="modal-actions"><button type="button" class="secondary" data-close-modal>取消</button><button class="primary">保存</button></div></form>`);
  document.getElementById("moveDirForm").addEventListener("submit", async event => {
    event.preventDefault();
    await api(`/api/dirs/${dirId}`, { method: "PUT", body: Object.fromEntries(new FormData(event.target)) });
    closeModal();
    await loadDocuments();
  });
}

function openDocMoveModal(docId, dirs) {
  openModal(`<h2>移动文件</h2><form id="moveDocForm"><label>移动到<select name="dir_id">${dirOptions(dirs, state.selectedDirId)}</select></label><div class="modal-actions"><button type="button" class="secondary" data-close-modal>取消</button><button class="primary">移动</button></div></form>`);
  document.getElementById("moveDocForm").addEventListener("submit", async event => {
    event.preventDefault();
    await api(`/api/projects/${state.project.id}/documents/${docId}/move`, { method: "POST", body: Object.fromEntries(new FormData(event.target)) });
    closeModal();
    await loadDocuments();
  });
}

function openDocPreview(docId, name, type) {
  const url = `/api/documents/${docId}/download`;
  const lower = (type || "").toLowerCase();
  const body = ["jpg", "jpeg", "png", "gif", "webp", "bmp"].includes(lower)
    ? `<img src="${url}" alt="${esc(name)}">`
    : ["mp4", "webm", "mov"].includes(lower)
      ? `<video src="${url}" controls></video>`
      : ["mp3", "wav", "ogg", "m4a"].includes(lower)
        ? `<audio src="${url}" controls></audio>`
        : `<iframe src="${url}" title="${esc(name)}"></iframe>`;
  const modal = document.getElementById("modal");
  modal.innerHTML = `<div class="preview-frame"><div class="preview-head"><strong>${esc(name)}</strong><div><a class="secondary small" href="${url}" download>下载源文件</a> <button class="secondary small" data-close-modal>关闭</button></div></div><div class="preview-body">${body}</div></div>`;
  modal.classList.remove("hidden");
}

async function loadPeople() {
  const data = await api(`/api/projects/${state.project.id}/people`);
  document.getElementById("tab-people").innerHTML = `<div class="box"><h3>相关人</h3>
    ${data.items.map(p => `<form class="person-row" data-person-row="${p.id}"><input name="name" value="${esc(p.name || "")}" placeholder="姓名"><input name="organization" value="${esc(p.organization || "")}" placeholder="单位职务"><input name="note" value="${esc(p.note || "")}" placeholder="备注"><div class="ops"><button type="button" class="text-btn" data-save-person="${p.id}">保存</button><button type="button" class="text-btn" data-del-person="${p.id}">删除</button></div></form>`).join("")}
    <form id="personForm" class="person-form"><input name="name" placeholder="姓名" required><input name="organization" placeholder="单位职务"><input name="note" placeholder="备注"><button class="primary">新增相关人</button></form></div>`;
  document.querySelectorAll("[data-save-person]").forEach(btn => btn.addEventListener("click", async () => {
    const form = btn.closest(".person-row");
    await api(`/api/people/${btn.dataset.savePerson}`, { method: "PUT", body: Object.fromEntries(new FormData(form)) });
    toast("相关人已保存");
    await loadPeople();
  }));
  document.querySelectorAll("[data-del-person]").forEach(btn => btn.addEventListener("click", async () => {
    if (!confirm("确定删除该相关人吗？")) return;
    await api(`/api/people/${btn.dataset.delPerson}`, { method: "DELETE" });
    await loadPeople();
  }));
  document.getElementById("personForm").addEventListener("submit", async event => {
    event.preventDefault();
    await api(`/api/projects/${state.project.id}/people`, { method: "POST", body: Object.fromEntries(new FormData(event.target)) });
    loadPeople();
  });
}

boot().catch(err => toast(err.message));
