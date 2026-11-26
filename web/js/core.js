/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* Shared state, helpers, API client, icons and the shell (sidebar/topbar/router). */

const $ = (sel, root = document) => root.querySelector(sel);

const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const uid = (prefix = "") => prefix + Math.random().toString(36).slice(2, 10);

function getByPath(obj, path) {
  return path.split(".").reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
}

function setByPath(obj, path, value) {
  const parts = path.split(".");
  const last = parts.pop();
  const target = parts.reduce((acc, key) => acc[key], obj);
  target[last] = value;
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function fmtDate(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function fmtDuration(seconds) {
  const value = Number(seconds) || 0;
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} с`;
  const min = Math.floor(value / 60);
  const sec = Math.round(value % 60);
  return `${min} мин ${sec} с`;
}

function fmtNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value) || 0);
}

function plural(count, forms) {
  const n = Math.abs(Number(count) || 0);
  const tail = n % 100;
  const digit = n % 10;
  if (tail > 10 && tail < 20) return forms[2];
  if (digit > 1 && digit < 5) return forms[1];
  if (digit === 1) return forms[0];
  return forms[2];
}

const AGENTS = ["агент", "агента", "агентов"];

const TASKS = ["задача", "задачи", "задач"];

const FILES = ["файл", "файла", "файлов"];

const RECORDS = ["запись", "записи", "записей"];

function countLabel(count, forms) {
  return `${count} ${plural(count, forms)}`;
}

const STATUS_LABEL = {
  queued: "в очереди",
  running: "выполняется",
  cancelling: "останавливается…",
  force_stopping: "принудительно останавливается",
  completed: "завершено",
  failed: "ошибка",
  cancelled: "остановлено",
};

function toast(message, kind = "", action = null) {
  const box = document.createElement("div");
  box.className = `toast ${kind}`;
  box.innerHTML = `<span>${kind === "err" ? icon("alert", 16) : kind === "ok" ? icon("check", 16) : icon("info", 16)}</span>
    <span class="grow">${esc(message)}</span>
    ${action ? `<button class="btn btn-sm toast-action">${esc(action.label)}</button>` : ""}`;
  $("#toasts").appendChild(box);
  if (action) {
    box.querySelector(".toast-action").addEventListener("click", () => {
      action.onClick();
      box.remove();
    });
  }
  const ttl = action ? 8000 : kind === "err" ? 6000 : 3200;
  setTimeout(() => {
    box.style.opacity = "0";
    box.style.transform = "translateY(6px)";
    box.style.transition = "opacity .25s, transform .25s";
    setTimeout(() => box.remove(), 260);
  }, ttl);
}

const STUDIO_TOKEN = (document.querySelector('meta[name="studio-token"]')?.content || "").trim();

async function api(path, { method = "GET", body = null } = {}) {
  const options = { method, headers: {} };
  if (method !== "GET") options.headers["X-Studio-Token"] = STUDIO_TOKEN;
  if (body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data = null;
  const text = await response.text();
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: text || `HTTP ${response.status}` };
  }
  if (response.status === 403 && /токен/i.test(data.error || "")) {
    if (!sessionStorage.getItem("studio-reloaded")) {
      sessionStorage.setItem("studio-reloaded", "1");
      window.location.reload();
      throw new Error("Сессия обновляется");
    }
  }
  if (response.status === 403 && data.password_change_required) {
    window.location.replace("/change-password.html");
    throw new Error(data.error || "Сначала смените пароль");
  }
  if (response.status === 401 && (data.auth || path.startsWith("/api/"))) {
    window.location.replace("/login");
    throw new Error(data.error || "Требуется вход");
  }
  sessionStorage.removeItem("studio-reloaded");
  if (!response.ok) {
    const message =
      response.status === 403
        ? "Сессия устарела или запрос отклонён защитой. Обновите страницу (Ctrl+F5)."
        : data.error
          ? `${data.error}${data.error_id ? ` (код: ${data.error_id})` : ""}`
          : `HTTP ${response.status}`;
    const error = new Error(message);
    error.payload = data;
    error.status = response.status;
    throw error;
  }
  return data;
}

/* ------------------------------------------------------------------ icons */

const ICONS = {
  play: '<path d="M7 4.5v15l13-7.5z" fill="currentColor" stroke="none"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
  save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
  code: '<path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  down: '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
  key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L21 2M17 6l3 3M14 9l2 2"/>',
  folder: '<path d="M4 7a2 2 0 0 1 2-2h3l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/>',
  back: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
  tool: '<path d="M14.7 6.3a4 4 0 1 0 5 5L21 21H3l7.4-7.4a4 4 0 0 1 4.3-7.3z"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
};

function icon(name, size = 16) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

/* --------------------------------------------------------------- markdown */

function cleanOutput(text) {
  if (!text) return "";
  let value = String(text).trim();
  const finalMatch = /final answer:\s*/i.exec(value);
  if (finalMatch) value = value.slice(finalMatch.index + finalMatch[0].length).trim();
  value = value.replace(/^(thought|action|observation):.*$/gim, "").trim();
  return value || String(text).trim();
}

function mdInline(text) {
  let out = esc(text);
  out = out.replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`);
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  out = out.replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  return out;
}

function md(source) {
  if (!source) return "";
  const text = String(source).replace(/\r\n/g, "\n");
  const fences = [];
  const withPlaceholders = text.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    fences.push(`<pre><code>${esc(code.replace(/\n$/, ""))}</code></pre>`);
    return `\u0000FENCE${fences.length - 1}\u0000`;
  });

  const lines = withPlaceholders.split("\n");
  const html = [];
  let paragraph = [];
  let list = null; // {type, items}
  let quote = [];
  let table = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${mdInline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      html.push(`<${list.type}>${list.items.map((item) => `<li>${mdInline(item)}</li>`).join("")}</${list.type}>`);
      list = null;
    }
  };
  const flushQuote = () => {
    if (quote.length) {
      html.push(`<blockquote>${mdInline(quote.join(" "))}</blockquote>`);
      quote = [];
    }
  };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((row) => !/^[\s|:-]+$/.test(row));
    const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    if (rows.length) {
      const head = cells(rows[0]);
      const body = rows.slice(1).map(cells);
      html.push(
        `<table><thead><tr>${head.map((c) => `<th>${mdInline(c)}</th>`).join("")}</tr></thead><tbody>${body
          .map((row) => `<tr>${row.map((c) => `<td>${mdInline(c)}</td>`).join("")}</tr>`)
          .join("")}</tbody></table>`
      );
    }
    table = [];
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushQuote();
    flushTable();
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) {
      flushAll();
      continue;
    }
    const fence = line.match(/^\u0000FENCE(\d+)\u0000$/);
    if (fence) {
      flushAll();
      html.push(fences[Number(fence[1])]);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      html.push(`<h${level}>${mdInline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      flushAll();
      html.push("<hr>");
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (bullet) {
      flushParagraph();
      flushQuote();
      flushTable();
      if (!list || list.type !== "ul") {
        flushList();
        list = { type: "ul", items: [] };
      }
      list.items.push(bullet[1]);
      continue;
    }
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (numbered) {
      flushParagraph();
      flushQuote();
      flushTable();
      if (!list || list.type !== "ol") {
        flushList();
        list = { type: "ol", items: [] };
      }
      list.items.push(numbered[1]);
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      flushList();
      quote.push(line.replace(/^\s*>\s?/, ""));
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushParagraph();
      flushList();
      flushQuote();
      table.push(line);
      continue;
    }
    flushList();
    flushQuote();
    flushTable();
    paragraph.push(line.trim());
  }
  flushAll();
  return html.join("");
}

/* ------------------------------------------------------------------ state */

const state = {
  view: "builder",
  info: null,
  crews: [],
  crew: null,
  dirty: false,
  saving: false,
  collapsed: new Set(),
  tools: [],
  templates: [],
  roles: [],
  runs: [],
  settings: null,
  user: null,
  files: null,
  placeholders: [],
  validation: null,
  workspaceInfo: null,
  run: null,
  templateEdit: null,
  es: null,
  timer: null,
};

/* Exposed for debugging in the browser console. */

window.__studio = state;
state.__boot = Math.random().toString(36).slice(2, 8);

/* ------------------------------------------------------------ data access */

const toolByName = (name) => state.tools.find((tool) => tool.name === name);

/* ---------------------------------------------------------------- routing */

function setHash(value) {
  const target = value ? `#${value}` : location.pathname;
  if (location.hash === `#${value}`) return;
  try {
    history.replaceState(null, "", target);
  } catch {
    /* file:// or sandboxed contexts */
  }
}

function parseHash() {
  const raw = (location.hash || "").replace(/^#/, "");
  const out = { crew: "", run: "", view: "" };
  raw.split("&").forEach((pair) => {
    const [key, value] = pair.split("=");
    if (key === "crew" && value) out.crew = decodeURIComponent(value);
    if (key === "run" && value) out.run = decodeURIComponent(value);
    if (key === "view" && value) out.view = decodeURIComponent(value);
  });
  return out;
}

function crewStats(crew) {
  return {
    agents: (crew.agents || []).length,
    tasks: (crew.tasks || []).length,
    process: crew.process === "hierarchical" ? "иерархия" : "последовательно",
  };
}

function effectiveModel(crew) {
  return crew?.default_llm || state.settings?.default_llm || "";
}

/* --------------------------------------------------------------- sidebar */

function renderSidebar() {
  const list = $("#crew-list");
  list.innerHTML = state.crews.length
    ? state.crews
        .map(
          (crew) => `
      <div class="crew-item ${state.crew && state.crew.id === crew.id ? "active" : ""}" data-crew="${esc(crew.id)}" tabindex="0" role="button">
        <span class="crew-item-text">
          <span class="crew-item-name">${esc(crew.name)}</span>
          <span class="crew-item-meta">${countLabel(crew.agents, AGENTS)} <span class="sep">·</span> ${countLabel(crew.tasks, TASKS)}</span>
        </span>
        <button class="crew-del" data-action="delete-crew-by-id" data-id="${esc(crew.id)}" title="Удалить проект">${icon("trash", 14)}</button>
      </div>`
        )
        .join("")
    : '<div class="small muted" style="padding:6px 10px">Пока нет проектов</div>';
  $("#crew-count").textContent = state.crews.length ? String(state.crews.length) : "";

  const nav = $("#side-nav");
  $$("button", nav).forEach((button) => {
    button.classList.toggle("active", state.view === button.dataset.view);
  });

  const status = state.info?.crewai;
  const dot = $("#engine-dot");
  const label = $("#engine-label");
  if (!status) {
    dot.className = "dot";
    label.textContent = "проверка окружения…";
  } else if (status.installed) {
    dot.className = "dot ok";
    label.textContent = `CrewAI ${status.version} · Python ${status.python}`;
  } else {
    dot.className = "dot err";
    label.textContent = "CrewAI не установлен";
  }
  $("#brand-version").textContent = state.info ? `v${state.info.version}` : "локальный интерфейс";
}

/* ----------------------------------------------------------------- topbar */

function renderTopbar() {
  const bar = $("#topbar");
  if (state.view === "builder" && state.crew) {
    const stats = crewStats(state.crew);
    bar.innerHTML = `
      <div class="topbar-left">
        <button class="btn btn-icon mobile-menu" data-action="toggle-sidebar" title="Меню">${icon("sliders", 18)}</button>
        <div class="topbar-title">
          <h1>${esc(state.crew.name)}</h1>
          <span class="sub">${countLabel(stats.agents, AGENTS)} · ${countLabel(stats.tasks, TASKS)} · ${stats.process} <span class="save-state dirty" id="save-state"></span></span>
        </div>
      </div>
      <div class="topbar-actions">
        ${state.templateEdit
          ? `<button class="btn btn-ghost btn-sm" data-action="cancel-template-edit">${icon("back")} Отмена</button>
             <button class="btn btn-primary" data-action="save-template-crew">${icon("save")} Сохранить шаблон</button>`
          : `<button class="btn btn-ghost btn-sm" data-action="export-crew">${icon("download")} Экспорт</button>
             <button class="btn btn-ghost btn-sm" data-action="save-as-template">${icon("spark")} В шаблон</button>
             <button class="btn btn-ghost btn-sm" data-action="show-code">${icon("code")} Код</button>
             <button class="btn btn-ghost btn-sm" data-action="duplicate-crew">${icon("copy")} Дублировать</button>
             <button class="btn btn-primary" data-action="run-crew">${icon("play")} Запустить</button>`}
      </div>`;
    updateSaveState();
    return;
  }

  if (state.view === "run") {
    const run = state.run;
    const status = run?.status || "running";
    bar.innerHTML = `
      <div class="topbar-left">
        <button class="btn btn-icon mobile-menu" data-action="toggle-sidebar" title="Меню">${icon("sliders", 18)}</button>
        <button class="btn btn-icon" data-action="back-to-builder" title="К редактору">${icon("back", 18)}</button>
        <div class="topbar-title">
          <h1>${esc(run?.crewName || "Запуск")}</h1>
          <span class="sub">${run?.model ? esc(run.model) : "модель по умолчанию"}</span>
        </div>
        <span class="pill ${status}" id="run-pill"><span class="dot"></span>${STATUS_LABEL[status] || status}</span>
      </div>
      <div class="topbar-actions">
        ${status === "force_stopping" ? `<button class="btn btn-danger" data-action="detach-run">${icon("stop")} Отсоединить</button>` : ""}
        ${status === "cancelling" ? `<button class="btn btn-danger" disabled>${icon("stop")} Останавливаю…</button>` : ""}
        ${status === "running" || status === "queued" ? `<button class="btn btn-danger" data-action="cancel-run">${icon("stop")} Остановить</button>` : ""}
        ${run?.id && status !== "running" && status !== "queued" ? `<button class="btn btn-ghost btn-sm" data-action="export-run" data-format="md">${icon("download")} Отчёт .md</button>` : ""}
        ${status === "running" || status === "queued" ? "" : `<button class="btn btn-ghost btn-sm" data-action="rerun">${icon("refresh")} Ещё запуск</button>`}
      </div>`;
    return;
  }

  const titles = {
    history: ["История запусков", "Все выполненные и остановленные прогоны"],
    templates: ["Шаблоны", "Готовые команды агентов — создайте проект в один клик"],
    roles: ["Роли", "Библиотека ролей: цель, опыт и характер подставляются агенту"],
    settings: ["Настройки", "Ключи API, модели и поведение интерфейса"],
    files: ["Файлы проекта", "Данные для агентов и результаты их работы"],
  };
  const [title, sub] = titles[state.view] || ["CrewAI Studio", ""];
  bar.innerHTML = `
    <div class="topbar-left">
      <button class="btn btn-icon mobile-menu" data-action="toggle-sidebar" title="Меню">${icon("sliders", 18)}</button>
      <div class="topbar-title"><h1>${esc(title)}</h1><span class="sub">${esc(sub)}</span></div>
    </div>
    <div class="topbar-actions">
      ${state.view === "history" ? `<button class="btn btn-ghost btn-sm" data-action="refresh-history">${icon("refresh")} Обновить</button>` : ""}
      ${state.view === "files" ? `<button class="btn btn-ghost btn-sm" data-action="refresh-files">${icon("refresh")} Обновить</button>` : ""}
      ${state.view === "roles" ? `<button class="btn btn-ghost btn-sm" data-action="reset-roles">${icon("refresh")} Сбросить к стандартным</button><button class="btn btn-primary" data-action="new-role">${icon("plus")} Новая роль</button>` : ""}
      ${state.view === "templates" ? `<button class="btn btn-ghost btn-sm" data-action="goto" data-view="builder">${icon("back")} К проектам</button><button class="btn btn-ghost btn-sm" data-action="empty-template">${icon("plus")} Пустой шаблон</button><button class="btn btn-primary" data-action="new-template">${icon("plus")} Новый шаблон</button>` : ""}
    </div>`;
}

/* ---------------------------------------------------------------- builder */

function render() {
  renderSidebar();
  renderTopbar();
  if (state.view === "builder") renderBuilder();
  else if (state.view === "run") {
    renderRun();
    if (typeof updatePermissionBanner === "function") updatePermissionBanner();
  }
  else if (state.view === "history") renderHistory();
  else if (state.view === "templates") renderTemplates();
  else if (state.view === "roles") renderRoles();
  else if (state.view === "settings") renderSettings();
  else if (state.view === "files") renderFiles();
  else if (state.view === "welcome") renderWelcome();
  updateRunIndicator();
}

function go(view) {
  state.view = view;
  if (view !== "builder") state.templateEdit = null;
  if (view === "history") refreshHistory();
  if (view === "files") refreshFiles();
  setHash(`view=${view}`);
  render();
  $("#view").scrollTop = 0;
}

let modalOnClose = null;

function openModal({ title, body, footer = "", wide = false, onClose = null }) {
  modalOnClose = onClose;
  const root = $("#modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" data-action="close-modal"></div>
    <div class="modal" style="${wide ? "width:min(980px, calc(100vw - 40px))" : ""}">
      <div class="modal-head"><h2>${esc(title)}</h2><button class="btn btn-icon" data-action="close-modal">${icon("x", 18)}</button></div>
      <div class="modal-body">${body}</div>
      ${footer ? `<div class="modal-foot">${footer}</div>` : ""}
    </div>`;
  root.classList.add("open");
}

function closeModal() {
  const root = $("#modal-root");
  root.classList.remove("open");
  root.innerHTML = "";
  const callback = modalOnClose;
  modalOnClose = null;
  if (callback) callback();
}

/* ------------------------------------------------------------------- save */
