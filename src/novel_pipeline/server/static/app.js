"use strict";

const state = {
  health: null,
  settings: null,
  genres: [],
  projects: [],
  project: null,
  memory: null,
  selectedSeq: null,
  retrySeq: null,
  job: null,
  pollTimer: null,
  eventSource: null,
};

const DEFAULT_HINT = "生成会先过质量门；未通过会保存为待确认，不写记忆。";

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function formatDetail(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join("；");
  }
  return JSON.stringify(detail);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const raw = await response.text();
  let data = null;
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    throw new Error(
      formatDetail(data && data.detail) || `请求失败（HTTP ${response.status}）`
    );
  }
  return data;
}

let toastTimer = null;
function toast(message, bad = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("bad", Boolean(bad));
  node.hidden = false;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.hidden = true;
  }, 3800);
}

function formatStatus(status) {
  const map = {
    planned: "计划中",
    trial: "试写",
    generating: "生成中",
    pending: "待确认",
    final: "定稿",
    queued: "排队中",
    running: "生成中",
    done: "完成",
    failed: "失败",
  };
  return map[status] || status || "未知";
}

function statusClass(status) {
  return ["final", "pending", "failed"].includes(status) ? status : "";
}

function findProfile(genre) {
  const target = String(genre || "").trim().toLowerCase();
  return (
    state.genres.find((profile) => {
      const names = [profile.key, profile.label, ...(profile.aliases || [])];
      return names.some((name) => String(name).toLowerCase() === target);
    }) || state.genres[0] || null
  );
}

function llmConfigured() {
  return Boolean(state.health && state.health.llm && state.health.llm.configured);
}

function renderSetupCard() {
  $("setup-card").hidden = llmConfigured();
}

function renderHealth() {
  const node = $("health");
  const health = state.health || {};
  const llm = health.llm || {};
  node.classList.remove("health--checking", "health--ok", "health--bad");
  if (llm.configured) {
    node.classList.add("health--ok");
    node.textContent = `AI 已就绪 · ${llm.provider || "?"} · ${llm.model || "?"}`;
    node.title = llm.base_url || "";
  } else {
    node.classList.add("health--bad");
    node.textContent = "AI 未配置 · 点此配置";
    node.title = llm.error || "点击打开 AI 设置；Key 只保存在本机。";
  }
  renderSetupCard();
}

function renderHealthError(message) {
  const node = $("health");
  node.classList.remove("health--checking", "health--ok");
  node.classList.add("health--bad");
  node.textContent = `服务未就绪：${message}`;
}

async function refreshHealth() {
  state.health = await api("/api/health");
  renderHealth();
}

function providerInfo(key) {
  const providers = (state.settings && state.settings.providers) || [];
  return providers.find((item) => item.key === key) || null;
}

function populateSettingsProviders(selected) {
  const select = $("settings-provider");
  clear(select);
  const providers = (state.settings && state.settings.providers) || [];
  for (const provider of providers) {
    const option = el("option", "", provider.label);
    option.value = provider.key;
    select.appendChild(option);
  }
  if (selected) select.value = selected;
}

function renderProviderHints() {
  const select = $("settings-provider");
  const info = providerInfo(select.value);
  const baseHint = $("settings-base-hint");
  if (info) {
    $("settings-base-url").placeholder = info.requires_base_url
      ? "必填，例如 https://your-endpoint/v1"
      : info.default_base_url || "留空使用服务商默认地址";
    baseHint.textContent = info.requires_base_url
      ? "兼容接口必须填写完整地址，通常以 /v1 结尾。"
      : "留空时使用该服务商的默认地址。";
  }

  const keyInput = $("settings-api-key");
  const keyHint = $("settings-key-hint");
  const saved = state.settings || {};
  if (info && !info.requires_key) {
    keyInput.placeholder = "Ollama 不需要 Key";
    keyHint.textContent = "本地 Ollama 不需要 API Key，确认服务已启动即可。";
  } else if (saved.provider && select.value !== saved.provider) {
    keyInput.placeholder = "更换服务商请填写新的 Key";
    keyHint.textContent = "更换服务商后通常需要新的 API Key。";
  } else if (saved.key_configured) {
    keyInput.placeholder = "已保存，留空保持不变";
    keyHint.textContent = "已保存 Key。留空保存不会覆盖；填新值会替换旧 Key。";
  } else {
    keyInput.placeholder = "粘贴你的 API Key";
    keyHint.textContent = "Key 只保存在本机 .env，不会出现在页面或接口返回里。";
  }
}

function applyProviderDefaults(providerKey) {
  const info = providerInfo(providerKey);
  if (!info) return;
  $("settings-model").value = info.default_model || "";
  $("settings-base-url").value = info.default_base_url || "";
  renderProviderHints();
}

function setSettingsMessage(message, bad = false) {
  const node = $("settings-message");
  node.textContent = message || "";
  node.hidden = !message;
  node.classList.toggle("bad", Boolean(message) && Boolean(bad));
  node.classList.toggle("ok", Boolean(message) && !bad);
}

function collectSettings() {
  return {
    provider: $("settings-provider").value,
    model: $("settings-model").value.trim(),
    base_url: $("settings-base-url").value.trim(),
    api_key: $("settings-api-key").value,
  };
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  return state.settings;
}

async function openSettings() {
  const dialog = $("settings-dialog");
  if (dialog.open) return;
  try {
    const settings = await loadSettings();
    populateSettingsProviders(settings.provider);
    $("settings-model").value = settings.model || "";
    $("settings-base-url").value = settings.base_url || "";
    $("settings-api-key").value = "";
    $("settings-data-path").textContent = settings.data_path || "data/novel.db";
    $("settings-env-path").textContent = settings.env_path || ".env";
    renderProviderHints();
    setSettingsMessage(
      settings.error ? `当前配置不完整：${settings.error}` : "",
      Boolean(settings.error)
    );
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  } catch (error) {
    toast(error.message, true);
  }
}

function closeSettings() {
  const dialog = $("settings-dialog");
  if (dialog.open) dialog.close();
  else dialog.removeAttribute("open");
}

async function saveSettings(event) {
  event.preventDefault();
  const button = event.target.querySelector("button[type=submit]");
  button.disabled = true;
  setSettingsMessage("保存中…");
  try {
    const settings = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(collectSettings()),
    });
    state.settings = settings;
    $("settings-api-key").value = "";
    renderProviderHints();
    await refreshHealth();
    setSettingsMessage("已保存到本机 .env，现在可以测试连接或关闭窗口。");
    toast("AI 设置已保存");
  } catch (error) {
    setSettingsMessage(error.message, true);
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function testSettingsConnection() {
  const button = $("settings-test");
  button.disabled = true;
  setSettingsMessage("正在测试连接…");
  try {
    const result = await api("/api/settings/test", {
      method: "POST",
      body: JSON.stringify(collectSettings()),
    });
    setSettingsMessage(
      result.message || (result.ok ? "连接成功" : "连接失败"),
      !result.ok
    );
    toast(
      result.ok ? "连接成功" : "连接失败，原因见设置窗口",
      !result.ok
    );
  } catch (error) {
    setSettingsMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function populateGenres() {
  const select = $("create-genre");
  clear(select);
  for (const profile of state.genres) {
    const option = el("option", "", `${profile.label}（${profile.key}）`);
    option.value = profile.key;
    select.appendChild(option);
  }
  if (!state.genres.length) {
    const option = el("option", "", "通用");
    option.value = "default";
    select.appendChild(option);
  }
}

function renderProjects() {
  const list = $("project-list");
  clear(list);
  $("no-projects").hidden = state.projects.length > 0;
  for (const project of state.projects) {
    const item = el("li");
    const button = el("button");
    if (state.project && state.project.id === project.id) {
      button.classList.add("active");
    }
    button.type = "button";
    button.appendChild(el("strong", "", project.title));
    const detail = `第 ${project.chapter_count} 章 · 定稿 ${project.final_count}` +
      (project.pending_count ? ` · 待确认 ${project.pending_count}` : "");
    button.appendChild(el("small", "", detail));
    button.addEventListener("click", () => {
      selectProject(project.id).catch((error) => toast(error.message, true));
    });
    item.appendChild(button);
    list.appendChild(item);
  }
}

async function loadProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects || [];
  renderProjects();
}

async function createProject(event) {
  event.preventDefault();
  const title = $("create-title").value.trim();
  const genre = $("create-genre").value;
  const rawTarget = $("create-target").value.trim();
  if (!title) {
    toast("先给作品起个名字", true);
    return;
  }
  const button = event.target.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const project = await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({
        title,
        genre,
        target_chapters: rawTarget ? Number(rawTarget) : null,
      }),
    });
    $("create-title").value = "";
    $("create-target").value = "";
    await loadProjects();
    await selectProject(project.id);
    toast("作品已创建");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function selectProject(projectId) {
  const [project, memory] = await Promise.all([
    api(`/api/projects/${projectId}`),
    api(`/api/projects/${projectId}/memory`),
  ]);
  state.project = project;
  state.memory = memory;
  state.selectedSeq = null;
  setRetry(null);
  renderProjects();
  $("welcome").hidden = true;
  $("project-view").hidden = false;
  $("memory-card").hidden = false;
  renderProject();
  renderChapterList();
  renderMemory();
  renderSceneFields();
  const chapters = project.chapters || [];
  if (chapters.length) {
    await loadChapter(chapters[chapters.length - 1].seq);
  } else {
    clearReader();
  }
}

function renderProject() {
  const project = state.project;
  if (!project) return;
  $("project-genre").textContent =
    `题材 · ${project.genre_label || project.genre}`;
  $("project-title").textContent = project.title;
  const target = project.target_chapters
    ? ` · 计划 ${project.target_chapters} 章`
    : "";
  $("project-meta").textContent =
    `已写 ${project.chapter_count} 章 · 定稿 ${project.final_count} 章` +
    ` · 待确认 ${project.pending_count} 章${target}`;
  $("chapter-count").textContent = `${project.chapter_count} 章`;
}

function renderChapterList() {
  const project = state.project;
  const list = $("chapter-list");
  clear(list);
  const chapters = (project && project.chapters) || [];
  $("chapter-empty").hidden = chapters.length > 0;
  for (const chapter of chapters) {
    const item = el("li");
    const button = el("button");
    button.type = "button";
    if (state.selectedSeq === chapter.seq) button.classList.add("active");
    const top = el("div", "chapter-top");
    const title = chapter.title || `第${chapter.seq}章`;
    top.appendChild(el("strong", "", `第${chapter.seq}章 · ${title}`));
    const pill = el("span", `status-pill ${statusClass(chapter.status)}`,
      formatStatus(chapter.status));
    top.appendChild(pill);
    button.appendChild(top);
    const score = chapter.score === null || chapter.score === undefined
      ? "未评分"
      : `${chapter.score} 分`;
    button.appendChild(el("div", "chapter-meta",
      `${chapter.chars} 字 · ${score} · 重写 ${chapter.rewrite_count} 次`));
    button.addEventListener("click", () => {
      loadChapter(chapter.seq).catch((error) => toast(error.message, true));
    });
    item.appendChild(button);
    list.appendChild(item);
  }
}

function renderMemory() {
  const counts = (state.memory && state.memory.counts) || {};
  const box = $("memory-counts");
  clear(box);
  const entries = [
    ["人物", counts.characters || 0],
    ["物品", counts.ledger_items || 0],
    ["未回收伏笔", counts.open_foreshadowing || 0],
    ["未还情感债", counts.open_emotional_threads || 0],
    ["世界规则", counts.active_world_rules || 0],
  ];
  for (const [label, value] of entries) {
    const chip = el("span", "count-chip");
    chip.appendChild(el("strong", "", String(value)));
    chip.appendChild(document.createTextNode(` ${label}`));
    box.appendChild(chip);
  }

  const detail = $("memory-detail");
  clear(detail);
  const memory = state.memory || {};
  const groups = [];
  if ((memory.open_foreshadowing || []).length) {
    groups.push([
      "未回收伏笔",
      memory.open_foreshadowing.map((item) => {
        const target = item.target_chapter
          ? `，目标第 ${item.target_chapter} 章`
          : "";
        return `第 ${item.planted_chapter} 章埋：${item.title}${target}`;
      }),
    ]);
  }
  if ((memory.open_emotional_threads || []).length) {
    groups.push([
      "未还情感债",
      memory.open_emotional_threads.map((item) => {
        const target = item.target_payoff_chapter
          ? `，目标第 ${item.target_payoff_chapter} 章`
          : "";
        return `${item.debt_from} → ${item.debt_to}：${item.title}${target}`;
      }),
    ]);
  }
  if ((memory.active_world_rules || []).length) {
    groups.push([
      "世界规则",
      memory.active_world_rules.map((item) => item.name),
    ]);
  }
  if (!groups.length) {
    detail.appendChild(el("p", "hint", "记忆账本会在章节定稿后自动更新。"));
    return;
  }
  for (const [title, lines] of groups) {
    const group = el("div", "memory-group");
    group.appendChild(el("h4", "", title));
    const ul = el("ul");
    for (const line of lines) ul.appendChild(el("li", "", line));
    group.appendChild(ul);
    detail.appendChild(group);
  }
}

function renderSceneFields() {
  const container = $("scene-fields");
  clear(container);
  const project = state.project;
  const profile = findProfile(project && project.genre);
  if (!profile || !profile.scene_fields) {
    container.appendChild(el("p", "hint", "这个题材没有额外场景卡字段。"));
    return;
  }
  for (const field of profile.scene_fields) {
    const label = el("label", field.required ? "required" : "");
    label.appendChild(document.createTextNode(field.label));
    if (field.required) label.appendChild(el("span", "req", "*"));
    const input = document.createElement("input");
    input.type = "text";
    input.dataset.scene = field.name;
    input.placeholder = field.required ? "本题材必填" : "可选";
    label.appendChild(input);
    container.appendChild(label);
  }
}

function collectScenePlan() {
  const plan = {};
  for (const input of document.querySelectorAll("[data-scene]")) {
    const value = input.value.trim();
    if (value) plan[input.dataset.scene] = value;
  }
  return plan;
}

function fillScenePlan(plan) {
  if (!plan) return;
  for (const input of document.querySelectorAll("[data-scene]")) {
    const value = plan[input.dataset.scene];
    if (typeof value === "string") input.value = value;
  }
}

function clearReader() {
  state.selectedSeq = null;
  $("reader").hidden = true;
  $("reader-empty").hidden = false;
  $("reader-empty").textContent = "选择左侧章节查看正文，或直接生成下一章。";
}

const REVIEW_KIND_LABELS = {
  character: "人物",
  item: "物品",
  info_gain: "情报",
  foreshadowing: "伏笔",
  emotional_thread: "情感债",
  world_rule: "世界规则",
};

const REVIEW_REASON_LABELS = {
  unknown_character: "记忆里还没有这个人物",
  unknown_item: "物品账本里还没有这个物品",
  foreshadowing_already_exists: "同名伏笔已经存在",
  over_plant_budget: "本章新埋伏笔超过上限",
  target_chapter_not_future: "伏笔回收目标章必须晚于本章",
  no_open_foreshadowing: "没有匹配的未回收伏笔",
  negative_stock: "物品数量会变成负数",
  low_confidence: "抽取置信度不足",
};

function reviewReason(item) {
  return REVIEW_REASON_LABELS[item.reason] || item.reason || "需要人工确认";
}

function canRegisterCharacter(item) {
  return (
    item.kind === "character" ||
    (item.kind === "info_gain" && item.reason === "unknown_character")
  );
}

function initialAttributes(item) {
  const attributes = {};
  const delta = (item.detail && item.detail.attributes_delta) || {};
  for (const [key, value] of Object.entries(delta)) {
    if (value === null || value === undefined || typeof value === "object") {
      continue;
    }
    attributes[key] = String(value);
  }
  return attributes;
}

async function refreshMemoryOnly() {
  if (!state.project) return;
  const memory = await api(`/api/projects/${state.project.id}/memory`);
  state.memory = memory;
  renderMemory();
}

async function registerReviewCharacter(item, row, statusInput, button) {
  if (!state.project || state.selectedSeq === null) return;
  button.disabled = true;
  const status = statusInput.value.trim();
  try {
    await api(`/api/projects/${state.project.id}/characters`, {
      method: "POST",
      body: JSON.stringify({
        name: item.name,
        status: status || null,
        core_attributes: initialAttributes(item),
        first_chapter: state.selectedSeq,
      }),
    });
    row.remove();
    await refreshMemoryOnly();
    if (!$("review-list").children.length) $("review-box").hidden = true;
    toast(`已登记人物「${item.name}」；请点“重写本章”继续`);
  } catch (error) {
    button.disabled = false;
    toast(error.message, true);
  }
}

async function registerReviewItem(item, row, quantityInput, unitInput, button) {
  if (!state.project || state.selectedSeq === null) return;
  button.disabled = true;
  const quantity = Number(quantityInput.value);
  const unit = unitInput.value.trim() || "件";
  try {
    await api(`/api/projects/${state.project.id}/items`, {
      method: "POST",
      body: JSON.stringify({
        name: item.name,
        quantity: Number.isFinite(quantity) ? Math.max(0, quantity) : 1,
        unit,
        updated_chapter: state.selectedSeq,
      }),
    });
    row.remove();
    await refreshMemoryOnly();
    if (!$("review-list").children.length) $("review-box").hidden = true;
    toast(`已登记物品「${item.name}」；请点“重写本章”继续`);
  } catch (error) {
    button.disabled = false;
    toast(error.message, true);
  }
}

function renderReviewItems(items) {
  const box = $("review-box");
  const list = $("review-list");
  clear(list);
  const entries = items || [];
  box.hidden = entries.length === 0;
  for (const item of entries) {
    const row = el("li", "review-item");
    const head = el("div", "review-item-head");
    head.appendChild(el(
      "strong",
      "",
      `${REVIEW_KIND_LABELS[item.kind] || item.kind}「${item.name}」`
    ));
    head.appendChild(el("span", "hint", reviewReason(item)));
    row.appendChild(head);

    if (canRegisterCharacter(item)) {
      const form = el("div", "review-form");
      const statusInput = document.createElement("input");
      statusInput.type = "text";
      statusInput.maxLength = 200;
      statusInput.placeholder = "身份或状态（可选，如：外门弟子）";
      statusInput.value =
        typeof item.detail?.status === "string" ? item.detail.status : "";
      const button = el("button", "ghost small", "登记人物");
      button.type = "button";
      button.addEventListener("click", () => {
        registerReviewCharacter(item, row, statusInput, button);
      });
      form.appendChild(statusInput);
      form.appendChild(button);
      row.appendChild(form);
    } else if (item.kind === "item") {
      const form = el("div", "review-form");
      const quantityInput = document.createElement("input");
      quantityInput.type = "number";
      quantityInput.min = "0";
      quantityInput.step = "1";
      quantityInput.value = "0";
      quantityInput.title = "本章开始前的数量；重写时会再应用本章的增减";
      const unitInput = document.createElement("input");
      unitInput.type = "text";
      unitInput.maxLength = 20;
      unitInput.value = "件";
      unitInput.title = "单位";
      const button = el("button", "ghost small", "登记物品");
      button.type = "button";
      button.addEventListener("click", () => {
        registerReviewItem(item, row, quantityInput, unitInput, button);
      });
      form.appendChild(quantityInput);
      form.appendChild(unitInput);
      form.appendChild(button);
      row.appendChild(form);
    }
    list.appendChild(row);
  }
}

function renderChapter(chapter) {
  state.selectedSeq = chapter.seq;
  $("reader-empty").hidden = true;
  $("reader").hidden = false;
  $("reader-seq").textContent = `第 ${chapter.seq} 章`;
  $("reader-title").textContent = chapter.title || `第${chapter.seq}章`;
  const pill = $("reader-status");
  pill.textContent = formatStatus(chapter.status);
  pill.className = `status-pill ${statusClass(chapter.status)}`;
  $("reader-content").textContent = chapter.content || "（本章暂无正文）";
  $("retry-btn").hidden = chapter.status !== "pending";
  renderReviewItems(chapter.status === "pending" ? chapter.review_items : []);
  renderChapterList();
}

async function loadChapter(seq) {
  if (!state.project) return;
  const chapter = await api(
    `/api/projects/${state.project.id}/chapters/${seq}`
  );
  setRetry(null);
  renderChapter(chapter);
}

function setRetry(seq) {
  state.retrySeq = seq || null;
  $("chapter-seq").value = state.retrySeq ? String(state.retrySeq) : "";
  $("cancel-retry").hidden = !state.retrySeq;
  $("generate-btn").textContent = state.retrySeq ? "重写本章" : "开始生成";
  $("compose-hint").textContent = state.retrySeq
    ? `正在重写第 ${state.retrySeq} 章；只有待确认章节可以重写。`
    : DEFAULT_HINT;
  if (state.retrySeq) {
    restoreLastRequest(state.retrySeq);
  }
}

function requestKey(projectId, seq) {
  return `novel:last:${projectId}:${seq}`;
}

function saveLastRequest(projectId, seq, payload) {
  try {
    localStorage.setItem(requestKey(projectId, seq), JSON.stringify(payload));
  } catch {
    // Private browsing or a locked-down browser may reject storage.
  }
}

function restoreLastRequest(seq) {
  if (!state.project) return;
  try {
    const raw = localStorage.getItem(requestKey(state.project.id, seq));
    if (!raw) return;
    const payload = JSON.parse(raw);
    if (payload.outline) $("gen-outline").value = payload.outline;
    if (payload.style_constraints) $("gen-style").value = payload.style_constraints;
    if (payload.character_brief) $("gen-brief").value = payload.character_brief;
    if (payload.title) $("gen-title").value = payload.title;
    fillScenePlan(payload.scene_plan);
  } catch {
    // A stale or malformed local entry should not block rewriting.
  }
}

function renderJob(job) {
  const box = $("job-result");
  box.hidden = false;
  const result = job.result || null;
  $("job-result-title").textContent = `第 ${job.chapter_seq} 章 · ${job.message}`;
  const score = result && result.quality ? result.quality.score : null;
  $("job-result-score").textContent =
    score === null || score === undefined ? "" : `${score} 分`;
  $("job-progress-bar").style.width = `${job.progress || 0}%`;
  const resultStatus = result ? formatStatus(result.status) : "";
  $("job-result-message").textContent = resultStatus
    ? `${job.message} · 管线状态：${resultStatus}`
    : job.message;
  $("job-status").textContent = job.message;

  const failures = $("job-failures");
  clear(failures);
  const items = (result && result.quality && result.quality.failures) || [];
  for (const finding of items) {
    const item = el("li");
    item.appendChild(el("span", "sev", `[${finding.severity}] ${finding.rule_id}`));
    item.appendChild(document.createTextNode(finding.evidence || ""));
    if (finding.suggestion) {
      item.appendChild(el("span", "suggestion", finding.suggestion));
    }
    failures.appendChild(item);
  }

  const error = $("job-error");
  const message = job.error || (result && result.error) || "";
  error.textContent = message;
  error.hidden = !message;
}

function stopJobUpdates() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

function startJobUpdates(jobId) {
  stopJobUpdates();
  if (typeof EventSource !== "function") {
    pollJob(jobId);
    return;
  }
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  state.eventSource = source;
  source.onmessage = (event) => {
    let job;
    try {
      job = JSON.parse(event.data);
    } catch (error) {
      return;
    }
    state.job = job;
    renderJob(job);
    if (job.status === "queued" || job.status === "running") return;
    source.close();
    if (state.eventSource === source) state.eventSource = null;
    finishJob(job);
  };
  source.onerror = () => {
    source.close();
    if (state.eventSource === source) state.eventSource = null;
    pollJob(jobId);
  };
}

async function finishJob(job) {
  setBusy(false);
  if (job.result && job.result.chapter) {
    renderChapter({
      seq: job.chapter_seq,
      title: (findChapterTitle(job.chapter_seq)) || `第${job.chapter_seq}章`,
      status: job.result.status,
      content: job.result.chapter.content,
    });
  }
  await refreshProjectData();
  if (job.result && job.result.chapter) {
    await loadChapter(job.chapter_seq);
  }
  if (job.status === "failed") {
    toast("生成失败，原因见下方", true);
  } else if (job.result && job.result.status === "pending") {
    toast("已保存为待确认；正文没有丢，可改大纲后重写本章");
  } else {
    toast("本章已定稿");
  }
}

async function pollJob(jobId) {
  try {
    const job = await api(`/api/jobs/${jobId}`);
    state.job = job;
    renderJob(job);
    if (job.status === "queued" || job.status === "running") {
      state.pollTimer = setTimeout(() => pollJob(jobId), 1500);
      return;
    }
    await finishJob(job);
  } catch (error) {
    setBusy(false);
    toast(error.message, true);
  }
}

function findChapterTitle(seq) {
  const chapters = (state.project && state.project.chapters) || [];
  const found = chapters.find((item) => item.seq === seq);
  return found ? found.title : null;
}

async function refreshProjectData() {
  if (!state.project) return;
  const projectId = state.project.id;
  const [project, memory] = await Promise.all([
    api(`/api/projects/${projectId}`),
    api(`/api/projects/${projectId}/memory`),
  ]);
  state.project = project;
  state.memory = memory;
  renderProject();
  renderChapterList();
  renderMemory();
  await loadProjects();
  refreshReaderMeta();
}

function refreshReaderMeta() {
  if (state.selectedSeq === null || !state.project) return;
  const found = (state.project.chapters || []).find(
    (item) => item.seq === state.selectedSeq
  );
  if (!found) return;
  $("reader-seq").textContent = `第 ${found.seq} 章`;
  $("reader-title").textContent = found.title || `第${found.seq}章`;
  const pill = $("reader-status");
  pill.textContent = formatStatus(found.status);
  pill.className = `status-pill ${statusClass(found.status)}`;
  $("retry-btn").hidden = found.status !== "pending";
}

function setBusy(busy) {
  const button = $("generate-btn");
  button.disabled = busy;
  button.textContent = busy
    ? "生成中…"
    : state.retrySeq
      ? "重写本章"
      : "开始生成";
}

async function generateChapter(event) {
  event.preventDefault();
  if (!state.project) {
    toast("先选择或新建一本作品", true);
    return;
  }
  if (!llmConfigured()) {
    openSettings();
    toast("先配置 AI API 再生成", true);
    return;
  }
  const outline = $("gen-outline").value.trim();
  if (!outline) {
    toast("本章大纲不能为空", true);
    $("gen-outline").focus();
    return;
  }
  const payload = {
    outline,
    target_words: Number($("gen-target").value) || 2000,
    pov: $("gen-pov").value.trim() || "第三人称",
    style_constraints: $("gen-style").value.trim(),
    character_brief: $("gen-brief").value.trim(),
    scene_plan: collectScenePlan(),
    quality_mode: $("gen-mode").value || null,
  };
  const title = $("gen-title").value.trim();
  if (title) payload.title = title;
  if (state.retrySeq) payload.chapter_seq = state.retrySeq;

  stopJobUpdates();
  setBusy(true);
  $("job-result").hidden = true;
  $("job-status").textContent = "提交中…";
  try {
    const job = await api(
      `/api/projects/${state.project.id}/chapters/generate`,
      { method: "POST", body: JSON.stringify(payload) }
    );
    state.job = job;
    saveLastRequest(state.project.id, job.chapter_seq, payload);
    renderJob(job);
    if (job.status === "queued" || job.status === "running") {
      startJobUpdates(job.id);
    } else {
      setBusy(false);
    }
  } catch (error) {
    setBusy(false);
    $("job-status").textContent = "";
    toast(error.message, true);
  }
}

function bindEvents() {
  $("create-form").addEventListener("submit", createProject);
  $("generate-form").addEventListener("submit", generateChapter);
  $("settings-btn").addEventListener("click", openSettings);
  $("setup-open").addEventListener("click", openSettings);
  $("settings-close").addEventListener("click", closeSettings);
  $("settings-cancel").addEventListener("click", closeSettings);
  $("settings-form").addEventListener("submit", saveSettings);
  $("settings-test").addEventListener("click", testSettingsConnection);
  $("settings-provider").addEventListener("change", () => {
    applyProviderDefaults($("settings-provider").value);
  });
  $("health").addEventListener("click", () => {
    if (!llmConfigured()) openSettings();
  });
  $("refresh-projects").addEventListener("click", () => {
    loadProjects()
      .then(() => toast("作品列表已刷新"))
      .catch((error) => toast(error.message, true));
  });
  $("export-btn").addEventListener("click", () => {
    if (!state.project) return;
    window.location.href = `/api/projects/${state.project.id}/export`;
  });
  $("retry-btn").addEventListener("click", () => {
    if (!state.selectedSeq) return;
    setRetry(state.selectedSeq);
    document.querySelector(".compose-card").scrollIntoView({ behavior: "smooth" });
    toast("已切换为重写本章；确认大纲后提交");
  });
  $("cancel-retry").addEventListener("click", () => {
    setRetry(null);
    $("chapter-seq").value = "";
    toast("已取消重写，下一次会写新章节");
  });
}

async function init() {
  bindEvents();
  try {
    const [health, genres] = await Promise.all([
      api("/api/health"),
      api("/api/genres"),
    ]);
    state.health = health;
    state.genres = genres.genres || [];
    renderHealth();
    populateGenres();
    await loadProjects();
    if (state.projects.length) {
      await selectProject(state.projects[0].id);
    }
  } catch (error) {
    renderHealthError(error.message);
    toast(`初始化失败：${error.message}`, true);
  }
}

init();
