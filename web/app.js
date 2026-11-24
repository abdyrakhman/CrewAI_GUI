/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* ------------------------------------------------------------------ utils */
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
  if (!response.ok) {
    const message =
      response.status === 403
        ? "Сессия устарела или запрос отклонён защитой. Обновите страницу (Ctrl+F5)."
        : data.error || `HTTP ${response.status}`;
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
  files: null,
  placeholders: [],
  validation: null,
  workspaceInfo: null,
  run: null,
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
        <button class="btn btn-ghost btn-sm" data-action="save-as-template">${icon("spark")} В шаблон</button>
        <button class="btn btn-ghost btn-sm" data-action="show-code">${icon("code")} Код</button>
        <button class="btn btn-ghost btn-sm" data-action="duplicate-crew">${icon("copy")} Дублировать</button>
        <button class="btn btn-primary" data-action="run-crew">${icon("play")} Запустить</button>
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
      ${state.view === "templates" ? `<button class="btn btn-ghost btn-sm" data-action="goto" data-view="builder">${icon("back")} К проектам</button><button class="btn btn-primary" data-action="new-template">${icon("plus")} Новый шаблон</button>` : ""}
    </div>`;
}

/* ---------------------------------------------------------------- builder */
function toolOption(tool, selected, index) {
  return `<button type="button" class="tool-option ${selected ? "on" : ""} ${tool.available ? "" : "unavailable"}"
    data-action="toggle-tool" data-index="${index}" data-tool="${esc(tool.name)}"
    title="${esc(tool.description)}${tool.available ? "" : " — не установлен, нажмите, чтобы поставить пакет"}">
    ${esc(tool.label)}${tool.available ? "" : " ↓"}
  </button>`;
}

function agentCard(agent, index) {
  const collapsed = state.collapsed.has(agent.id);
  const initials = (agent.role || "A").trim().slice(0, 2).toUpperCase();
  const tools = agent.tools || [];
  const extrasPending = state.tools.some((tool) => tool.source !== "builtin" && !tool.available);
  return `
  <div class="agent-card ${collapsed ? "collapsed" : ""}" data-agent-card="${esc(agent.id)}">
    <div class="agent-head" data-action="toggle-agent" data-id="${esc(agent.id)}">
      <div class="agent-avatar">${esc(initials)}</div>
      <div class="agent-title">
        <strong>${esc(agent.role || "Без роли")}</strong>
        <span>${esc(agent.goal || "цель не задана")}</span>
      </div>
      ${tools.length ? `<span class="chip" title="Инструменты">${icon("tool", 12)} ${tools.length}</span>` : ""}
      <button class="btn btn-icon" data-action="delete-agent" data-index="${index}" title="Удалить агента">${icon("trash", 15)}</button>
      <span class="chev">${icon("chevron", 16)}</span>
    </div>
    <div class="agent-body">
      <div class="two-col">
        <div class="field">
          <label>Роль <span class="hint">или выберите готовую кнопкой справа</span></label>
          <div class="row" style="gap:6px">
            <input type="text" data-field="agents.${index}.role" list="role-list" value="${esc(agent.role)}" placeholder="Например: Исследователь">
            <button class="btn btn-sm" data-action="apply-role" data-index="${index}" title="Применить роль из библиотеки">${icon("spark", 14)}</button>
          </div>
          ${agent.role_id ? `<span class="hint-text">роль из библиотеки</span>` : ""}
        </div>
        <div class="field">
          <label>Модель <span class="hint">пусто — модель проекта</span></label>
          <input type="text" data-field="agents.${index}.llm" value="${esc(agent.llm)}" list="model-list" placeholder="openai/gpt-4o-mini">
        </div>
      </div>
      <div class="field">
        <label>Цель</label>
        <textarea data-field="agents.${index}.goal" rows="2" placeholder="Что агент должен сделать">${esc(agent.goal)}</textarea>
      </div>
      <div class="field">
        <label>Предыстория <span class="hint">характер и опыт — влияет на стиль</span></label>
        <textarea data-field="agents.${index}.backstory" rows="3" placeholder="Опишите опыт, подход и характер агента">${esc(agent.backstory)}</textarea>
      </div>
      <div class="field">
        <label>Инструменты ${extrasPending ? '<span class="hint">серые — из пакета crewai-tools, нажмите, чтобы установить</span>' : ""}</label>
        <div class="tools-picker">
          ${state.tools
            .filter((tool) => tool.source === "builtin")
            .map((tool) => toolOption(tool, tools.includes(tool.name), index))
            .join("")}
        </div>
        <div class="tools-group">Дополнительные · пакет crewai-tools</div>
        <div class="tools-picker">
          ${state.tools
            .filter((tool) => tool.source !== "builtin")
            .map((tool) => toolOption(tool, tools.includes(tool.name), index))
            .join("")}
        </div>
      </div>
      <div class="row-wrap" style="gap:18px">
        <label class="toggle">
          <input type="checkbox" data-field="agents.${index}.allow_delegation" ${agent.allow_delegation ? "checked" : ""}>
          <span class="track"></span> Делегирование
        </label>
        <label class="toggle">
          <input type="checkbox" data-field="agents.${index}.reasoning" ${agent.reasoning ? "checked" : ""}>
          <span class="track"></span> Рассуждения
        </label>
        <label class="toggle" title="Перед каждым изменением файла спрашивать подтверждение">
          <input type="checkbox" data-field="agents.${index}.confirm_changes" ${agent.confirm_changes ? "checked" : ""}>
          <span class="track"></span> Подтверждение изменений
        </label>
        <div class="row" style="gap:6px">
          <span class="tiny muted">Макс. итераций</span>
          <input type="number" min="1" max="100" data-field="agents.${index}.max_iter" value="${agent.max_iter}" style="width:70px">
        </div>
        <div class="row" style="gap:6px" title="0 — без ограничения. Агент будет остановлен по времени.">
          <span class="tiny muted">Лимит времени, с</span>
          <input type="number" min="0" max="86400" data-field="agents.${index}.max_execution_time" value="${agent.max_execution_time || 0}" style="width:80px">
        </div>
      </div>
    </div>
  </div>`;
}

function taskCard(task, index) {
  const agents = state.crew.agents || [];
  const otherTasks = (state.crew.tasks || []).filter((t) => t.id !== task.id);
  const context = task.context || [];
  return `
  <div class="task-card" data-task-card="${esc(task.id)}">
    <div class="task-head">
      <span class="task-index">${index + 1}</span>
      <input type="text" class="task-name" data-field="tasks.${index}.name" value="${esc(task.name)}"
             placeholder="Название задачи" style="background:transparent;border:none;padding:2px 0;font-weight:600">
      <div class="task-actions">
        <button class="btn btn-icon" data-action="move-task" data-index="${index}" data-dir="-1" title="Выше" ${index === 0 ? "disabled" : ""}>${icon("up", 15)}</button>
        <button class="btn btn-icon" data-action="move-task" data-index="${index}" data-dir="1" title="Ниже" ${index === (state.crew.tasks || []).length - 1 ? "disabled" : ""}>${icon("down", 15)}</button>
        <button class="btn btn-icon" data-action="delete-task" data-index="${index}" title="Удалить задачу">${icon("trash", 15)}</button>
      </div>
    </div>
    <div class="task-body">
      <div class="field">
        <label>Описание <span class="hint">можно вставлять {переменные} из входных данных</span></label>
        <textarea data-field="tasks.${index}.description" rows="3" placeholder="Что нужно сделать, шаг за шагом">${esc(task.description)}</textarea>
      </div>
      <div class="field">
        <label>Ожидаемый результат</label>
        <textarea data-field="tasks.${index}.expected_output" rows="2" placeholder="Формат и критерии готового результата">${esc(task.expected_output)}</textarea>
      </div>
      <div class="two-col">
        <div class="field">
          <label>Исполнитель</label>
          <select data-field="tasks.${index}.agent">
            <option value="">— не выбран —</option>
            ${agents
              .map(
                (agent) =>
                  `<option value="${esc(agent.id)}" ${agent.id === task.agent ? "selected" : ""}>${esc(agent.role || "Без роли")}</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label>Формат результата</label>
          <select data-field="tasks.${index}.output_format">
            <option value="text" ${task.output_format === "text" ? "selected" : ""}>Текст</option>
            <option value="markdown" ${task.output_format === "markdown" ? "selected" : ""}>Markdown</option>
            <option value="file" ${task.output_format === "file" ? "selected" : ""}>Файл в data/outputs</option>
            <option value="json" ${task.output_format === "json" ? "selected" : ""}>JSON</option>
          </select>
        </div>
      </div>
      ${task.output_format === "file" ? `
      <div class="field">
        <label>Имя файла результата</label>
        <input type="text" data-field="tasks.${index}.output_file" value="${esc(task.output_file)}" placeholder="report.md">
      </div>` : ""}
      <details style="margin-top:4px">
        <summary class="small muted" style="cursor:pointer;padding:4px 0">Дополнительно: контекст и флаги</summary>
        <div style="padding-top:10px">
          ${otherTasks.length ? `
          <div class="field">
            <label>Контекст <span class="hint">результаты этих задач попадут в промпт</span></label>
            <div class="tools-picker">
              ${otherTasks
                .map(
                  (other, otherIndex) => `
                <button type="button" class="tool-option ${context.includes(other.id) ? "on" : ""}"
                  data-action="toggle-context" data-index="${index}" data-ctx="${esc(other.id)}">
                  ${esc(other.name || `Задача ${otherIndex + 1}`)}
                </button>`
                )
                .join("")}
            </div>
          </div>` : ""}
          <div class="row-wrap" style="gap:18px">
            <label class="toggle">
              <input type="checkbox" data-field="tasks.${index}.async_execution" ${task.async_execution ? "checked" : ""}>
              <span class="track"></span> Асинхронно
            </label>
            <label class="toggle">
              <input type="checkbox" data-field="tasks.${index}.human_input" ${task.human_input ? "checked" : ""}>
              <span class="track"></span> Запрос подтверждения у человека
            </label>
          </div>
        </div>
      </details>
    </div>
  </div>`;
}

function renderBuilder() {
  const crew = state.crew;
  if (!crew) return renderEmptyView();
  const knownPlaceholders = state.placeholders || [];
  const declared = new Set((crew.inputs || []).map((item) => item.key));
  const missing = knownPlaceholders.filter((name) => !declared.has(name));

  $("#view").innerHTML = `
  <div class="view-inner">
    <div class="builder-grid">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <h2>Проект</h2>
            <span class="spacer"></span>
            <button class="btn btn-ghost btn-sm" data-action="delete-crew">${icon("trash", 14)} Удалить</button>
          </div>
          <div class="card-body">
            <div class="field">
              <label>Название</label>
              <input type="text" data-field="name" value="${esc(crew.name)}" placeholder="Например: Исследование рынка">
            </div>
            <div class="field">
              <label>Описание</label>
              <input type="text" data-field="description" value="${esc(crew.description)}" placeholder="Что делает эта команда">
            </div>
            <div class="field">
              <label>Рабочая область <span class="hint">папка, в которой агенты читают и пишут файлы</span></label>
              <div class="row" style="gap:6px">
                <input type="text" id="workspace-input" value="${esc(crew.workspace)}" placeholder="${esc(state.workspaceInfo?.path || "по умолчанию — data/workspaces/<проект>")}" spellcheck="false">
                <button class="btn btn-sm" data-action="pick-workspace">${icon("folder", 14)} Выбрать</button>
                ${crew.workspace ? `<button class="btn btn-ghost btn-sm" data-action="reset-workspace" title="Вернуть папку по умолчанию">${icon("refresh", 14)}</button>` : ""}
              </div>
              <div class="row-wrap" style="gap:8px;margin-top:2px">
                <span class="hint-text mono" style="word-break:break-all">${esc(state.workspaceInfo?.path || "")}</span>
                <span class="chip ${state.workspaceInfo?.exists ? "ok" : "warn"}">${state.workspaceInfo?.exists ? "папка есть" : "будет создана"}</span>
                ${state.workspaceInfo?.exists && !state.workspaceInfo?.writable ? '<span class="chip err">нет прав на запись</span>' : ""}
                ${state.workspaceInfo?.is_default ? '<span class="chip">по умолчанию</span>' : ""}
              </div>
            </div>
          </div>
        </div>

        <div class="section-title">
          <h2>Команда</h2>
          <span class="count">${(crew.agents || []).length} агент(ов)</span>
          <span class="spacer grow"></span>
          <button class="btn btn-sm" data-action="add-agent">${icon("plus", 14)} Агент</button>
        </div>
        <div class="stack" id="agents-list">
          ${(crew.agents || []).map((agent, index) => agentCard(agent, index)).join("") ||
            `<div class="card"><div class="empty-state"><h3>Нет агентов</h3><p>Добавьте первого агента: роль, цель и предыстория.</p></div></div>`}
        </div>

        <div class="section-title" style="margin-top:8px">
          <h2>Задачи</h2>
          <span class="count">${(crew.tasks || []).length} шаг(ов)</span>
          <span class="spacer grow"></span>
          <button class="btn btn-sm" data-action="add-task">${icon("plus", 14)} Задача</button>
        </div>
        <div id="tasks-list">
          ${(crew.tasks || []).map((task, index) => taskCard(task, index)).join("") ||
            `<div class="card"><div class="empty-state"><h3>Нет задач</h3><p>Опишите шаги, которые должна выполнить команда.</p></div></div>`}
        </div>
      </div>

      <div class="stack" style="position:sticky;top:12px">
        <div class="card">
          <div class="card-head"><h2>Параметры</h2></div>
          <div class="card-body">
            <div class="field">
              <label>Процесс</label>
              <select data-field="process">
                <option value="sequential" ${crew.process === "sequential" ? "selected" : ""}>Последовательный</option>
                <option value="hierarchical" ${crew.process === "hierarchical" ? "selected" : ""}>Иерархический (с менеджером)</option>
              </select>
            </div>
            ${crew.process === "hierarchical" ? `
            <div class="field">
              <label>Модель менеджера</label>
              <input type="text" data-field="manager_llm" value="${esc(crew.manager_llm)}" list="model-list" placeholder="openai/gpt-4o">
            </div>` : ""}
            <div class="field">
              <label>Модель проекта <span class="hint">используется по умолчанию</span></label>
              <input type="text" data-field="default_llm" value="${esc(crew.default_llm)}" list="model-list" placeholder="${esc(state.settings?.default_llm || "openai/gpt-4o-mini")}">
            </div>
            <div class="row-wrap" style="gap:14px">
              <label class="toggle"><input type="checkbox" data-field="memory" ${crew.memory ? "checked" : ""}><span class="track"></span> Память</label>
              <label class="toggle"><input type="checkbox" data-field="planning" ${crew.planning ? "checked" : ""}><span class="track"></span> Планирование</label>
              <label class="toggle"><input type="checkbox" data-field="verbose" ${crew.verbose ? "checked" : ""}><span class="track"></span> Подробный лог</label>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h2>Входные данные</h2>
            <span class="spacer"></span>
            <button class="btn btn-ghost btn-sm" data-action="add-input">${icon("plus", 14)}</button>
          </div>
          <div class="card-body">
            ${(crew.inputs || []).length
              ? (crew.inputs || [])
                  .map(
                    (item, index) => `
              <div class="field" data-input-row="${index}">
                <label>
                  <input type="text" data-field="inputs.${index}.key" value="${esc(item.key)}" placeholder="имя" style="width:120px;padding:3px 7px;font-family:var(--mono);font-size:11.5px">
                  <span class="spacer grow"></span>
                  <button class="btn btn-icon" data-action="delete-input" data-index="${index}" title="Удалить">${icon("x", 13)}</button>
                </label>
                <textarea data-field="inputs.${index}.value" rows="2" placeholder="${esc(item.description || "значение")}">${esc(item.value)}</textarea>
              </div>`
                  )
                  .join("")
              : `<p class="hint-text">Переменные, которые подставляются в текст задач через <code>{имя}</code>.</p>`}
            ${missing.length
              ? `<div class="alert info" style="margin-top:10px;flex-direction:column;gap:8px">
                   <span>Найдены переменные без значений: ${missing.map((n) => `<code>{${esc(n)}}</code>`).join(", ")}</span>
                   <button class="btn btn-sm" data-action="add-missing-inputs">Добавить их</button>
                 </div>`
              : ""}
          </div>
        </div>

        <div class="card">
          <div class="card-body">
            <button class="btn btn-primary btn-block" data-action="run-crew" style="padding:11px">${icon("play")} Запустить команду</button>
            <p class="hint-text" style="margin:9px 0 0;text-align:center">${icon("info", 12)} Ctrl + Enter</p>
          </div>
        </div>
      </div>
    </div>
    <datalist id="model-list">
      ${(state.info?.providers || [])
        .flatMap((provider) => provider.models)
        .map((model) => `<option value="${esc(model)}"></option>`)
        .join("")}
    </datalist>
    <datalist id="role-list">
      ${(state.roles || []).map((role) => `<option value="${esc(role.name)}">${esc(role.goal || "")}</option>`).join("")}
    </datalist>
  </div>`;
}

/* -------------------------------------------------------------------- run */
function runTaskIndexByName(name) {
  if (!state.run) return -1;
  const tasks = state.run.tasks;
  if (name) {
    const exact = tasks.findIndex((task) => task.name === name);
    if (exact !== -1) return exact;
  }
  const active = tasks.findIndex((task) => task.status === "active");
  if (active !== -1) return active;
  return tasks.findIndex((task) => task.status === "pending");
}

function cleanStream(text) {
  return String(text || "")
    .replace(/^[ \t]*(Thought|Action|Observation):[^\n]*$/gim, "")
    .replace(/^[ \t]*Final Answer:[ \t]*/gim, "")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^\s+/, "");
}

function renderRun() {
  const run = state.run;
  if (!run) return renderEmptyView();
  const done = run.tasks.filter((task) => task.status === "done").length;
  const status = run.status;
  $("#view").innerHTML = `
  <div class="view-inner run-layout">
    <div class="run-banner">
      <div class="metric"><b id="run-timer">0:00</b><span>время</span></div>
      <div class="divider"></div>
      <div class="metric"><b id="run-progress">${done}/${run.tasks.length}</b><span>задач</span></div>
      <div class="divider"></div>
      <div class="metric"><b id="run-tokens">${fmtNumber(run.usage.total_tokens || 0)}</b><span>токенов</span></div>
      <div class="grow"></div>
      <div class="row" style="gap:8px">
        <span class="small muted">${esc(run.model || "модель по умолчанию")}</span>
      </div>
    </div>
    ${run.workspace
      ? `<div class="workspace-line">${icon("folder", 13)} <span class="muted">Рабочая область:</span>
           <span class="mono">${esc(run.workspace)}</span>
           <button class="btn btn-icon" data-action="copy-workspace" title="Скопировать путь">${icon("copy", 13)}</button>
         </div>`
      : ""}

    <div id="run-error"></div>

    <div class="stack" id="run-tasks">
      ${run.tasks.length
        ? run.tasks.map((task, index) => taskRunCard(task, index)).join("")
        : `<div class="card"><div class="empty-state"><div class="spinner"></div><p>Готовлю команду агентов…</p></div></div>`}
    </div>

    <div class="card" id="run-result-card" style="display:${run.result || run.error || run.status === "cancelled" ? "block" : "none"}">
      <div class="card-head">
        <h2>Итог</h2>
        <span class="spacer"></span>
        <div class="tabs" style="border:none;padding:0">
          <button data-action="run-tab" data-tab="result" class="${run.tab === "result" ? "active" : ""}">Результат</button>
          <button data-action="run-tab" data-tab="tasks" class="${run.tab === "tasks" ? "active" : ""}">По задачам</button>
          <button data-action="run-tab" data-tab="log" class="${run.tab === "log" ? "active" : ""}">Журнал</button>
        </div>
      </div>
      <div class="card-body" id="run-result-body">${runTabBody()}</div>
    </div>
  </div>`;

  updateTimer();
  run.__topStatus = run.status;
  if (["running", "queued", "cancelling"].includes(status)) startTimer();
  scrollRunToActive();
}

function taskRunCard(task, index) {
  const statusLabel = { pending: "ожидает", active: "работает", done: "готово", error: "ошибка" }[task.status] || task.status;
  const chipClass = task.status === "done" ? "ok" : task.status === "active" ? "accent" : task.status === "error" ? "err" : "";
  const live = task.status === "active" || task.status === "pending";
  return `
  <div class="task-run ${task.status}" data-run-task="${index}">
    <div class="task-run-head">
      <span class="task-index">${index + 1}</span>
      <span class="name">${esc(task.name || task.description || "Задача " + (index + 1))}</span>
      ${task.agent ? `<span class="chip">${esc(task.agent)}</span>` : ""}
      <span class="chip ${chipClass}">${statusLabel}</span>
    </div>
    <div class="task-run-body">
      ${task.tools.length ? `<div class="tool-strip">${task.tools.map(toolChip).join("")}</div>` : ""}
      ${live ? `<div class="stream-text" data-idx="${index}" data-state="${task.status}">${esc(cleanStream(task.text))}</div>` : ""}
      ${task.output ? `<div class="final prose" data-final="${index}">${md(task.output)}</div>` : ""}
      ${task.error ? `<div class="alert err" style="margin-top:10px">${esc(task.error)}</div>` : ""}
    </div>
  </div>`;
}

function toolChip(tool) {
  const cls = tool.failed ? "err" : tool.done ? "ok" : "accent";
  const label = tool.done ? (tool.failed ? "сбой" : "готово") : "вызов";
  return `<span class="chip ${cls}" title="${esc(tool.args || tool.output || "")}">${icon("tool", 12)} ${esc(tool.name)} · ${label}</span>`;
}

function runTabBody() {
  const run = state.run;
  if (!run) return "";
  if (run.tab === "tasks") {
    const filled = run.tasks.filter((task) => task.output || task.text);
    return filled.length
      ? filled
          .map(
            (task, index) => `
        <div style="margin-bottom:18px">
          <div class="row" style="margin-bottom:6px"><span class="task-index">${index + 1}</span><strong style="font-size:13px">${esc(task.name || "Задача")}</strong><span class="chip">${esc(task.agent || "")}</span></div>
          ${task.output ? `<div class="prose">${md(task.output)}</div>` : `<div class="stream-text">${esc(task.text || "")}</div>`}
        </div>`
          )
          .join("")
      : '<p class="muted">Пока нет результатов по задачам.</p>';
  }
  if (run.tab === "log") {
    return `<div class="console" id="run-console">${esc(run.logs.join("\n") || "Журнал пуст.")}</div>`;
  }
  if (run.error) return `<div class="alert err">${esc(run.error)}</div>`;
  if (run.result) {
    return `
      <div class="prose" id="run-final">${md(run.result.raw || "")}</div>
      <div class="row" style="margin-top:16px;gap:8px">
        <button class="btn btn-sm" data-action="copy-result">${icon("copy", 14)} Скопировать</button>
        <button class="btn btn-sm" data-action="export-run" data-format="md">${icon("download", 14)} Скачать .md</button>
        <button class="btn btn-sm" data-action="export-run" data-format="json">${icon("download", 14)} JSON</button>
      </div>`;
  }
  if (run.status === "cancelled") {
    return `<div class="alert warn">Запуск остановлен до получения итогового ответа. Перейдите на вкладку «По задачам», чтобы увидеть, что успели сделать агенты.</div>`;
  }
  return '<p class="muted">Результат появится здесь.</p>';
}

function updateRunBanner() {
  const run = state.run;
  if (!run) return;
  if (state.view === "run" && run.__topStatus !== run.status) {
    run.__topStatus = run.status;
    renderTopbar();
  }
  const progress = $("#run-progress");
  if (progress) progress.textContent = `${run.tasks.filter((t) => t.status === "done").length}/${run.tasks.length}`;
  const tokens = $("#run-tokens");
  if (tokens) tokens.textContent = fmtNumber(run.usage.total_tokens || 0);
  const pill = $("#run-pill");
  if (pill) {
    pill.className = `pill ${run.status}`;
    pill.innerHTML = `<span class="dot"></span>${STATUS_LABEL[run.status] || run.status}`;
  }
  updateRunIndicator();
}

function updateTaskCard(index) {
  const run = state.run;
  if (!run || !run.tasks[index]) return;
  const card = $(`[data-run-task="${index}"]`);
  if (!card) {
    if (state.view === "run") renderRun();
    return;
  }
  const task = run.tasks[index];
  card.className = `task-run ${task.status}`;
  const chip = $(".task-run-head .chip:last-child", card);
  if (chip) {
    chip.className = `chip ${task.status === "done" ? "ok" : task.status === "active" ? "accent" : task.status === "error" ? "err" : ""}`;
    chip.textContent = { pending: "ожидает", active: "работает", done: "готово", error: "ошибка" }[task.status] || task.status;
  }
  const strip = $(".tool-strip", card);
  if (task.tools.length) {
    if (strip) strip.innerHTML = task.tools.map(toolChip).join("");
    else $(".task-run-body", card).insertAdjacentHTML("afterbegin", `<div class="tool-strip">${task.tools.map(toolChip).join("")}</div>`);
  }
  if (task.output) {
    const body = $(".task-run-body", card);
    let final = $(`[data-final="${index}"]`, card);
    if (!final) {
      body.insertAdjacentHTML("beforeend", `<div class="final prose" data-final="${index}"></div>`);
      final = $(`[data-final="${index}"]`, card);
    }
    final.innerHTML = md(task.output);
  }
  if (task.error) {
    const body = $(".task-run-body", card);
    if (!$(".alert.err", body)) body.insertAdjacentHTML("beforeend", `<div class="alert err" style="margin-top:10px">${esc(task.error)}</div>`);
  }
  const stream = $(`[data-idx="${index}"]`);
  if (stream) {
    if (task.status === "done" || task.status === "error") stream.remove();
    else {
      stream.dataset.state = task.status;
      stream.textContent = cleanStream(task.text);
    }
  }
}

/* ------------------------------------------------------------------- init */
async function init() {
  try {
    const [info, crews, tools, templates, runs, settings, roles] = await Promise.all([
      api("/api/info"),
      api("/api/crews"),
      api("/api/tools"),
      api("/api/templates"),
      api("/api/runs"),
      api("/api/settings"),
      api("/api/roles"),
    ]);
    state.info = info;
    state.crews = crews.crews || [];
    if ((crews.broken || []).length) {
      toast(`Повреждённые файлы проектов: ${crews.broken.map((item) => item.file).join(", ")}`, "err");
    }
    state.tools = tools.tools || [];
    state.templates = templates.templates || [];
    state.runs = runs.runs || [];
    state.settings = settings.settings;
    state.roles = roles.roles || [];
    document.documentElement.dataset.theme = state.settings?.theme === "light" ? "light" : "dark";
    renderSidebar();

    const route = parseHash();
    // The user may have started working while these requests were in flight:
    // never steal their view in that case.
    if (!state.crew) {
      if (route.run) {
        await openRunDetail(route.run);
      } else if (route.crew) {
        await openCrew(route.crew);
      } else if (route.view) {
        go(route.view);
      } else if (state.crews.length) {
        await openCrew(state.crews[0].id);
      } else {
        state.view = "welcome";
        render();
      }
    } else {
      // Someone already opened a project while these requests were in flight:
      // the snapshot above may predate it, so ask for the current list.
      await refreshCrews();
    }

    const status = await api("/api/status");
    if (status.active_run && state.run?.id !== status.active_run) {
      toast("Возобновляю просмотр активного запуска");
      attachRun(status.active_run);
    }
  } catch (error) {
    $("#view").innerHTML = `<div class="empty-state"><h3>Не удалось загрузить приложение</h3><p>${esc(error.message)}</p></div>`;
  }
}

async function refreshCrews() {
  const data = await api("/api/crews");
  state.crews = data.crews || [];
  renderSidebar();
}

async function openCrew(crewId) {
  // A running crew keeps streaming in the background; the indicator brings it back.
  const data = await api(`/api/crews/${crewId}`);
  state.crew = data.crew;
  state.validation = data.validation;
  state.workspaceInfo = data.workspace || null;
  state.placeholders = data.validation?.placeholders || [];
  state.view = "builder";
  state.dirty = false;
  setHash(`crew=${encodeURIComponent(crewId)}`);
  render();
}

/* -------------------------------------------------------------- navigation */
function render() {
  renderSidebar();
  renderTopbar();
  if (state.view === "builder") renderBuilder();
  else if (state.view === "run") renderRun();
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
  if (view === "history") refreshHistory();
  if (view === "files") refreshFiles();
  setHash(`view=${view}`);
  render();
  $("#view").scrollTop = 0;
}

function renderWelcome() {
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="card" style="overflow:hidden">
        <div style="padding:44px 40px;background:radial-gradient(900px 220px at 10% -10%, rgba(139,92,246,.18), transparent)">
          <div class="row" style="gap:10px"><span class="chip accent">${icon("spark", 13)} CrewAI Studio</span></div>
          <h1 style="margin:14px 0 8px;font-size:26px;letter-spacing:-.6px">Команда ИИ-агентов — в графическом интерфейсе</h1>
          <p class="muted" style="max-width:620px;margin:0 0 22px;font-size:14px">
            Соберите агентов и задачи, задайте модель и нажмите «Запустить». Всё, что раньше требовало консоли,
            доступно здесь: настройки, живые ответы модели, история запусков и готовый Python-код.
          </p>
          <div class="row-wrap">
            <button class="btn btn-primary" data-action="new-crew">${icon("plus")} Создать проект</button>
            <button class="btn" data-action="goto" data-view="templates">${icon("spark")} Взять шаблон</button>
            <button class="btn btn-ghost" data-action="goto" data-view="settings">${icon("key")} Ключи API</button>
          </div>
        </div>
      </div>
      <div class="template-grid" style="margin-top:18px">
        ${(state.info?.crewai?.installed
          ? [
              ["1", "Опишите команду", "Роль, цель и предыстория для каждого агента — от этого зависит качество."],
              ["2", "Задайте шаги", "Задачи выполняются по порядку, результат предыдущей виден следующей."],
              ["3", "Нажмите «Запустить»", "Ответы моделей печатаются в реальном времени, итог сохраняется в историю."],
            ]
          : [
              ["!", "CrewAI не установлен", "Запустите start.bat один раз — он создаст окружение и поставит зависимости."],
              ["2", "Откройте настройки", "Вставьте ключ API (OpenAI, OpenRouter, DeepSeek, Ollama — любой)."],
              ["3", "Соберите команду", "Или возьмите готовый шаблон из раздела «Шаблоны»."],
            ]
        )
          .map(
            ([num, title, text]) => `
          <div class="card" style="padding:16px">
            <div class="row" style="gap:10px;margin-bottom:6px"><span class="task-index">${esc(num)}</span><strong style="font-size:13.5px">${esc(title)}</strong></div>
            <p class="small muted" style="margin:0">${esc(text)}</p>
          </div>`
          )
          .join("")}
      </div>
    </div>`;
}

function renderEmptyView() {
  $("#view").innerHTML = `<div class="empty-state"><h3>Проект не выбран</h3><p>Создайте новый проект или выберите существующий в списке слева.</p></div>`;
}

/* --------------------------------------------------------------- history */
async function refreshHistory() {
  try {
    const data = await api("/api/runs");
    state.runs = data.runs || [];
    if (state.view === "history") {
      renderHistory();
    }
  } catch (error) {
    toast(error.message, "err");
  }
}

function renderHistory() {
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="card">
        <div class="card-head"><h2>Запуски</h2><span class="spacer"></span><span class="small muted">${countLabel(state.runs.length, RECORDS)}</span></div>
        ${
          state.runs.length
            ? `<table class="table">
          <thead><tr><th>Проект</th><th style="width:120px">Статус</th><th style="width:150px">Начало</th><th style="width:120px">Длительность</th><th style="width:100px">Токены</th><th style="width:210px"></th></tr></thead>
          <tbody>
            ${state.runs
              .map(
                (run) => `
              <tr>
                <td><strong>${esc(run.crew_name || "—")}</strong></td>
                <td><span class="chip ${run.status === "completed" ? "ok" : run.status === "failed" ? "err" : run.status === "cancelled" ? "warn" : "accent"}">${STATUS_LABEL[run.status] || run.status}</span></td>
                <td class="muted nowrap">${fmtDate(run.started_at)}</td>
                <td class="muted nowrap">${fmtDuration(run.duration)}</td>
                <td class="muted nowrap">${fmtNumber(run.tokens)}</td>
                <td class="actions">
                  <button class="btn btn-sm" data-action="open-run" data-run="${esc(run.id)}">Открыть</button>
                  <button class="btn btn-icon" data-action="export-run" data-run="${esc(run.id)}" data-format="md" title="Скачать отчёт">${icon("download", 15)}</button>
                  <button class="btn btn-icon" data-action="delete-run" data-run="${esc(run.id)}" title="Удалить">${icon("trash", 15)}</button>
                </td>
              </tr>`
              )
              .join("")}
          </tbody></table>`
            : `<div class="empty-state"><h3>Пока нет запусков</h3><p>История появится после первого запуска команды.</p></div>`
        }
      </div>
    </div>`;
}

/* -------------------------------------------------------------- templates */
function templateCard(template) {
  return `
    <div class="template-card ${template.custom ? "custom" : ""}" data-action="use-template" data-key="${esc(template.key)}">
      <div class="row" style="gap:8px">
        <h3>${esc(template.title)}</h3>
        <span class="spacer grow"></span>
        ${template.badge ? `<span class="badge">${esc(template.badge)}</span>` : ""}
        ${template.custom
          ? `<button class="btn btn-icon template-edit" data-action="edit-template" data-key="${esc(template.key)}"
                     data-title="${esc(template.title)}" data-description="${esc(template.description || "")}"
                     title="Изменить шаблон">${icon("edit", 15)}</button>
             <button class="btn btn-icon template-del" data-action="delete-template" data-key="${esc(template.key)}"
                     data-title="${esc(template.title)}" title="Удалить шаблон">${icon("trash", 15)}</button>`
          : ""}
      </div>
      <p>${esc(template.description || "Без описания")}</p>
      <div class="meta">
        <span class="chip">${esc(template.subtitle || "")}</span>
        ${template.custom ? '<span class="chip ok">ваш шаблон</span>' : ""}
      </div>
    </div>`;
}

function renderTemplates() {
  const custom = state.templates.filter((template) => template.custom);
  const builtin = state.templates.filter((template) => !template.custom);
  $("#view").innerHTML = `
    <div class="view-inner stack">
      <div class="section-title">
        <h2>Мои шаблоны</h2>
        <span class="count">${custom.length ? countLabel(custom.length, ["шаблон", "шаблона", "шаблонов"]) : "пока пусто"}</span>
      </div>
      ${
        custom.length
          ? `<div class="template-grid">${custom.map(templateCard).join("")}</div>`
          : `<div class="card"><div class="empty-state" style="padding:28px 20px">
               <h3>Своих шаблонов нет</h3>
               <p>Откройте любой проект и нажмите «В шаблон» в верхней панели — он появится здесь.</p>
               <button class="btn btn-primary" data-action="goto" data-view="builder">${icon("back", 15)} К проектам</button>
             </div></div>`
      }
      <div class="section-title" style="margin-top:8px">
        <h2>Стандартные</h2>
        <span class="count">${builtin.length}</span>
      </div>
      <div class="template-grid">${builtin.map(templateCard).join("")}</div>
    </div>`;
}

/* ------------------------------------------------------------------ roles */
function roleBackstory(role) {
  return [role?.experience, role?.character].filter(Boolean).join(" ");
}

function roleByName(name) {
  const target = String(name || "").trim().toLowerCase();
  if (!target) return null;
  return (state.roles || []).find((role) => role.name.trim().toLowerCase() === target) || null;
}

function applyRole(index, roleId = "") {
  const agent = state.crew?.agents?.[index];
  if (!agent) return;
  const role = roleId ? (state.roles || []).find((item) => item.id === roleId) : roleByName(agent.role);
  if (!role) {
    toast("Такой роли нет в библиотеке. Откройте раздел «Роли», чтобы создать её.", "err");
    return;
  }
  const previous = {
    role: agent.role,
    goal: agent.goal,
    backstory: agent.backstory,
    role_id: agent.role_id || "",
    tools: [...(agent.tools || [])],
  };
  agent.role = role.name;
  agent.goal = role.goal || agent.goal;
  agent.backstory = roleBackstory(role) || agent.backstory;
  agent.role_id = role.id;
  const tools = [...(agent.tools || [])];
  (role.tools || []).forEach((tool) => {
    if (!tools.includes(tool)) tools.push(tool);
  });
  agent.tools = tools;
  markDirty();
  renderBuilder();
  renderTopbar();
  toast(`Роль «${role.name}» применена`, "ok", {
    label: "Отменить",
    onClick: () => {
      Object.assign(agent, previous);
      markDirty();
      renderBuilder();
    },
  });
}

function openRolePicker(index) {
  const roles = state.roles || [];
  if (!roles.length) {
    toast("Библиотека ролей пуста — создайте роль в разделе «Роли»", "err");
    return;
  }
  const agent = state.crew?.agents?.[index];
  openModal({
    title: `Роль для агента «${agent?.role || "без роли"}»`,
    wide: true,
    body: `<p class="hint-text" style="margin-top:0">Выберите роль — цель, предыстория и инструменты подставятся автоматически.</p>
      <div class="role-pick-list">
        ${roles
          .map(
            (role) => `<button class="role-pick" data-action="pick-role" data-index="${index}" data-id="${esc(role.id)}">
            <span class="role-pick-name">${esc(role.name)}</span>
            <span class="role-pick-goal">${esc(role.goal || "Без цели")}</span>
            <span class="role-pick-meta">${esc([role.experience, role.character].filter(Boolean).join(" ").slice(0, 120))}</span>
          </button>`
          )
          .join("")}
      </div>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>`,
  });
}

function roleCard(role) {
  return `
    <div class="role-card">
      <div class="row" style="gap:8px">
        <div class="role-avatar">${esc((role.name || "?").trim().slice(0, 2).toUpperCase())}</div>
        <div class="grow">
          <h3>${esc(role.name)}</h3>
          <p class="role-goal">${esc(role.goal || "Цель не задана")}</p>
        </div>
        <button class="btn btn-icon" data-action="edit-role" data-id="${esc(role.id)}" title="Редактировать">${icon("edit", 15)}</button>
        <button class="btn btn-icon" data-action="delete-role" data-id="${esc(role.id)}" data-name="${esc(role.name)}" title="Удалить роль">${icon("trash", 15)}</button>
      </div>
      ${role.experience ? `<div class="role-part"><span>Опыт</span>${esc(role.experience)}</div>` : ""}
      ${role.character ? `<div class="role-part"><span>Характер</span>${esc(role.character)}</div>` : ""}
      ${(role.tools || []).length
        ? `<div class="row-wrap" style="gap:6px">${role.tools.map((tool) => `<span class="chip">${icon("tool", 11)} ${esc(tool)}</span>`).join("")}</div>`
        : ""}
    </div>`;
}

function renderRoles() {
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="role-grid">
        ${(state.roles || []).map(roleCard).join("")}
        <button class="role-card role-new" data-action="new-role">
          ${icon("plus", 22)}
          <span>Новая роль</span>
          <small>название, цель, опыт, характер</small>
        </button>
      </div>
    </div>`;
}

function openRoleEditor(role = null) {
  const isNew = !role;
  const data = role || { name: "", goal: "", experience: "", character: "", tools: [] };
  const tools = (data.tools || []).slice();
  openModal({
    title: isNew ? "Новая роль" : `Роль «${data.name}»`,
    wide: true,
    body: `
      <div class="field">
        <label>Название роли</label>
        <input type="text" id="role-name" value="${esc(data.name)}" placeholder="Например: Исследователь">
      </div>
      <div class="field">
        <label>Цель</label>
        <textarea id="role-goal" rows="2" placeholder="Что этот агент должен делать">${esc(data.goal)}</textarea>
      </div>
      <div class="two-col">
        <div class="field">
          <label>Опыт</label>
          <textarea id="role-experience" rows="3" placeholder="Опыт и профессиональный бэкграунд">${esc(data.experience)}</textarea>
        </div>
        <div class="field">
          <label>Характер</label>
          <textarea id="role-character" rows="3" placeholder="Как агент думает и пишет">${esc(data.character)}</textarea>
        </div>
      </div>
      <div class="field">
        <label>Инструменты <span class="hint">подставятся агенту вместе с ролью</span></label>
        <div class="tools-picker" id="role-tools">
          ${(state.tools || [])
            .filter((tool) => tool.available)
            .map(
              (tool) => `<button type="button" class="tool-option ${tools.includes(tool.name) ? "on" : ""}"
                 data-action="toggle-role-tool" data-tool="${esc(tool.name)}" title="${esc(tool.description)}">${esc(tool.label)}</button>`
            )
            .join("")}
        </div>
      </div>
      <p class="hint-text" style="margin:0">Предыстория агента собирается из полей «Опыт» и «Характер».</p>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-primary" data-action="save-role" data-id="${esc(data.id || "")}">Сохранить</button>`,
  });
}

async function refreshRoles() {
  try {
    const data = await api("/api/roles");
    state.roles = data.roles || [];
    if (state.view === "roles") renderRoles();
    if (state.view === "builder" && state.crew) renderBuilder();
  } catch (error) {
    toast(error.message, "err");
  }
}

async function refreshTemplates() {
  try {
    const data = await api("/api/templates");
    state.templates = data.templates || [];
    if (state.view === "templates") renderTemplates();
  } catch (error) {
    toast(error.message, "err");
  }
}

/* -------------------------------------------------------------- workspace */
let pickerPath = "";

async function setWorkspace(raw) {
  if (!state.crew) return;
  try {
    saveGeneration += 1; // cancel any pending debounced save of the old workspace
    const data = await api(`/api/crews/${state.crew.id}/workspace`, { method: "POST", body: { path: raw } });
    state.crew = data.crew;
    state.workspaceInfo = data.workspace || null;
    state.dirty = false;
    if (state.view === "builder") {
      renderBuilder();
      renderTopbar();
    }
    toast(data.workspace?.is_default ? "Рабочая область: папка по умолчанию" : "Рабочая область сохранена", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function parentPath(path) {
  const clean = String(path || "").replace(/[\\/]+$/, "");
  const index = Math.max(clean.lastIndexOf("\\"), clean.lastIndexOf("/"));
  return index > 2 ? clean.slice(0, index) : "";
}

async function openWorkspacePicker(startPath) {
  // The project folder is created lazily: materialise it first so the picker
  // opens exactly where the project lives instead of a sibling folder.
  if (state.crew && state.workspaceInfo && !state.workspaceInfo.exists) {
    try {
      const data = await api(`/api/crews/${state.crew.id}/workspace`, {
        method: "POST",
        body: { path: state.crew.workspace || "" },
      });
      state.crew = data.crew;
      state.workspaceInfo = data.workspace || state.workspaceInfo;
      startPath = state.workspaceInfo.path;
      if (state.view === "builder") renderBuilder();
    } catch {
      /* keep the original path and fall back to its parent below */
    }
  }
  pickerPath = startPath || "";
  openModal({
    title: "Рабочая область проекта",
    wide: true,
    body: `<p class="hint-text" style="margin-top:0">Агенты смогут читать и записывать файлы только в выбранной папке.
             Остальные папки компьютера для них закрыты.</p>
           <div id="fs-picker"><div class="loading-screen" style="padding:30px 0"><div class="spinner"></div></div></div>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-primary" data-action="fs-choose">${icon("check", 15)} Выбрать эту папку</button>`,
  });
  // The project folder may not exist yet: try it, then its parent, then home.
  const candidates = [startPath || "", parentPath(startPath), ""];
  for (const candidate of candidates) {
    try {
      await loadPicker(candidate);
      return;
    } catch {
      /* try the next candidate */
    }
  }
}

async function loadPicker(path) {
  const container = $("#fs-picker");
  if (!container) return;
  try {
    const data = await api(`/api/fs?path=${encodeURIComponent(path || "")}`);
    pickerPath = data.path;
    container.innerHTML = `
      <div class="field">
        <label>Путь</label>
        <div class="row" style="gap:6px">
          <input type="text" id="fs-path" value="${esc(data.path)}" spellcheck="false">
          <button class="btn btn-sm" data-action="fs-go">Перейти</button>
        </div>
      </div>
      <div class="row-wrap" style="gap:6px;margin-bottom:10px">
        ${(data.drives || []).map((drive) => `<button class="chip" data-action="fs-open" data-path="${esc(drive)}">${esc(drive)}</button>`).join("")}
        <button class="chip" data-action="fs-open" data-path="${esc(data.home)}">Домашняя папка</button>
      </div>
      <div class="fs-list">
        ${data.parent ? `<button class="fs-item" data-action="fs-open" data-path="${esc(data.parent)}">${icon("back", 15)} <span>..</span></button>` : ""}
        ${(data.dirs || [])
          .map((dir) => `<button class="fs-item" data-action="fs-open" data-path="${esc(dir.path)}">${icon("folder", 15)} <span>${esc(dir.name)}</span></button>`)
          .join("")}
        ${(data.files || []).slice(0, 10).map((file) => `<div class="fs-item is-file">${icon("file", 15)} <span>${esc(file.name)}</span></div>`).join("")}
        ${!(data.dirs || []).length && !(data.files || []).length ? '<p class="hint-text">Папка пуста</p>' : ""}
      </div>
      <div class="row" style="margin-top:12px;gap:6px">
        <input type="text" id="fs-new-name" placeholder="Имя новой папки" style="max-width:240px">
        <button class="btn btn-sm" data-action="fs-mkdir">${icon("plus", 14)} Создать</button>
        <span class="hint-text">${data.writable ? "папка доступна для записи" : "нет прав на запись"}</span>
      </div>`;
  } catch (error) {
    container.innerHTML = `<div class="alert err">${esc(error.message)}</div>`;
    throw error;
  }
}

async function makePickerDir() {
  const name = $("#fs-new-name")?.value?.trim();
  if (!name) {
    toast("Укажите имя папки", "err");
    return;
  }
  try {
    const data = await api("/api/fs/mkdir", { method: "POST", body: { parent: pickerPath, name } });
    await loadPicker(data.path).catch(() => {});
  } catch (error) {
    toast(error.message, "err");
  }
}

/* --------------------------------------------------------------- settings */
function providerBlock(provider) {
  const settings = state.settings || {};
  if (!provider.key_field && provider.id !== "openai") {
    return `
      <div class="key-row">
        <div class="key-label"><b>${esc(provider.label)}</b><span>локальный сервер</span></div>
        <div class="row"><span class="chip ok">не требует ключа</span><span class="small muted">модели: ${esc(provider.models.join(", "))}</span></div>
      </div>`;
  }
  const field = provider.key_field || "openai_api_key";
  const saved = Boolean(settings.secret_flags?.[field]);
  const baseField = provider.base_field;
  return `
    <div class="key-row">
      <div class="key-label"><b>${esc(provider.label)}</b><span>${esc(provider.models[0] || "")}</span></div>
      <div class="stack" style="gap:8px">
        <div class="row" style="gap:6px">
          <input type="password" data-setting="${field}" value=""
                 placeholder="${saved ? "ключ сохранён — введите новый, чтобы заменить" : "Ключ API"}"
                 autocomplete="off" spellcheck="false">
          ${saved ? `<button class="btn btn-icon" data-action="clear-key" data-field="${field}" title="Удалить ключ">${icon("trash", 15)}</button>` : ""}
        </div>
        ${saved ? `<span class="chip ok">${icon("check", 12)} ключ сохранён и зашифрован</span>` : ""}
        ${baseField && provider.id === "openai"
          ? `<input type="text" data-setting="${baseField}" value="${esc(settings[baseField] || "")}" placeholder="Базовый URL (необязательно, для прокси и совместимых API)">`
          : ""}
      </div>
    </div>`;
}

function renderSettings() {
  const settings = state.settings || {};
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="settings-grid">
        <div class="stack">
          <div class="card">
            <div class="card-head"><h2>Модели по умолчанию</h2></div>
            <div class="card-body">
              <div class="field">
                <label>Модель</label>
                <input type="text" data-setting="default_llm" value="${esc(settings.default_llm || "")}" list="settings-models" placeholder="openai/gpt-4o-mini">
                <span class="hint-text">Формат: провайдер/модель, например <code>openai/gpt-4o-mini</code>, <code>ollama/llama3.1</code>.</span>
              </div>
              <div class="row-wrap" style="gap:18px;margin-top:4px">
                <label class="toggle"><input type="checkbox" data-setting="live_stream" ${settings.live_stream ? "checked" : ""}><span class="track"></span> Потоковая передача ответов</label>
                <label class="toggle"><input type="checkbox" data-setting="allow_network_tools" ${((settings.allow_network_tools || []).length || settings.allow_network_tools === true) ? "checked" : ""}><span class="track"></span> Сетевые инструменты третьих сторон</label>
              </div>
              <p class="hint-text" style="margin:8px 0 0">Сторонние инструменты («crewai-tools») работают вне песочницы приложения:
                их запросы и чтение файлов не проходят проверку доступа. Включайте, только если доверяете инструменту.</p>
              <div class="row" style="margin-top:14px;gap:8px">
                <button class="btn" data-action="test-llm">${icon("spark", 15)} Проверить подключение</button>
                <span class="small muted" id="test-result"></span>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Ключи API</h2><span class="spacer"></span><span class="small muted">хранятся локально в data/settings.json</span></div>
            <div class="card-body">
              ${(state.info?.providers || []).map(providerBlock).join("")}
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Дополнительные переменные окружения</h2></div>
            <div class="card-body">
              <p class="hint-text" style="margin-top:0">Например <code>SERPER_API_KEY</code> для веб-поиска или <code>OPENAI_API_BASE</code> для локальной модели.</p>
              <div id="env-rows">
                ${Object.keys(settings.extra_env || {})
                  .map(
                    (key, index) => `
                  <div class="row" style="margin-bottom:8px" data-env-row="${index}" data-env-original="${esc(key)}">
                    <input type="text" value="${esc(key)}" data-env-key placeholder="ПЕРЕМЕННАЯ" style="max-width:220px;font-family:var(--mono);font-size:12px">
                    <input type="password" value="" data-env-value placeholder="${settings.env_flags?.[key] ? "значение сохранено (зашифровано)" : "значение"}">
                    <button class="btn btn-icon" data-action="remove-env" data-index="${index}">${icon("x", 14)}</button>
                  </div>`
                  )
                  .join("")}
              </div>
              <button class="btn btn-sm" data-action="add-env">${icon("plus", 14)} Добавить переменную</button>
            </div>
          </div>
        </div>

        <div class="stack">
          <div class="card">
            <div class="card-head"><h2>Оформление</h2></div>
            <div class="card-body">
              <div class="field">
                <label>Тема</label>
                <div class="segmented" id="theme-switch">
                  <button data-action="set-theme" data-theme="dark" class="${settings.theme !== "light" ? "active" : ""}">Тёмная</button>
                  <button data-action="set-theme" data-theme="light" class="${settings.theme === "light" ? "active" : ""}">Светлая</button>
                </div>
              </div>
              <button class="btn btn-primary btn-block" data-action="save-settings">${icon("save", 15)} Сохранить настройки</button>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Доступ к папкам</h2></div>
            <div class="card-body">
              <p class="hint-text" style="margin-top:0">Проводник рабочей области видит домашнюю папку и папку проекта.
                Добавьте нужные корни — по одному в строке.</p>
              <textarea id="fs-roots" rows="3" placeholder="D:\Проекты">${esc((settings.fs_roots || []).join("\n"))}</textarea>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Окружение</h2></div>
            <div class="card-body">
              <div class="row" style="justify-content:space-between"><span class="small muted">CrewAI</span><span class="chip ${state.info?.crewai?.installed ? "ok" : "err"}">${esc(state.info?.crewai?.version || "не установлен")}</span></div>
              <div class="row" style="justify-content:space-between;margin-top:8px"><span class="small muted">Python</span><span class="mono small">${esc(state.info?.crewai?.python || "—")}</span></div>
              <div class="row" style="justify-content:space-between;margin-top:8px"><span class="small muted">Потоковые события</span><span class="chip ${state.info?.crewai?.stream_support ? "ok" : "warn"}">${state.info?.crewai?.stream_support ? "доступны" : "нет"}</span></div>
              <p class="hint-text" style="margin:12px 0 0;word-break:break-all">${esc(state.info?.crewai?.executable || "")}</p>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Данные</h2></div>
            <div class="card-body">
              <p class="hint-text" style="margin-top:0">Проекты, история и ключи лежат в папке <code>data</code> рядом с приложением.</p>
              <button class="btn btn-danger btn-block btn-sm" data-action="clear-history">${icon("trash", 14)} Очистить историю запусков</button>
            </div>
          </div>
        </div>
      </div>
      <datalist id="settings-models">
        ${(state.info?.providers || []).flatMap((p) => p.models).map((m) => `<option value="${esc(m)}"></option>`).join("")}
      </datalist>
    </div>`;
}

/* ------------------------------------------------------------------ files */
async function refreshFiles() {
  try {
    const suffix = state.crew ? `?crew_id=${encodeURIComponent(state.crew.id)}` : "";
    state.files = await api(`/api/files${suffix}`);
    if (state.view === "files") renderFiles();
  } catch (error) {
    toast(error.message, "err");
  }
}

function renderFiles() {
  const files = state.files || { uploads: [], outputs: [] };
  const block = (title, items, folder, extra = "") => `
    <div class="card">
      <div class="card-head"><h2>${title}</h2><span class="spacer"></span>${extra}<span class="small muted">${countLabel(items.length, FILES)}</span></div>
      ${items.length
        ? `<table class="table"><tbody>${items
            .map(
              (file) => `
          <tr>
            <td style="width:100%"><strong>${esc(file.name)}</strong><div class="tiny muted">${esc(file.path)} · ${(file.size / 1024).toFixed(1)} КБ</div></td>
            <td class="nowrap muted tiny">${fmtDate(file.modified)}</td>
            <td class="actions"><button class="btn btn-sm" data-action="preview-file" data-folder="${folder}" data-name="${esc(file.path)}">Открыть</button></td>
          </tr>`
            )
            .join("")}</tbody></table>`
        : `<div class="empty-state" style="padding:22px"><p>Пусто</p></div>`}
    </div>`;

  const ws = files.workspace;
  $("#view").innerHTML = `
    <div class="view-inner stack">
      ${
        ws
          ? `<div class="card">
               <div class="card-head">
                 <h2>Рабочая область проекта</h2>
                 <span class="spacer"></span>
                 <button class="btn btn-ghost btn-sm" data-action="copy-workspace">${icon("copy", 14)} Скопировать путь</button>
                 <button class="btn btn-ghost btn-sm" data-action="pick-workspace">${icon("folder", 14)} Изменить</button>
               </div>
               <div class="card-body" style="padding-bottom:6px">
                 <p class="mono small" style="margin:0;word-break:break-all">${esc(ws.path || "—")}</p>
                 <p class="hint-text" style="margin:6px 0 0">Сюда агенты пишут файлы и отсюда читают исходные данные.</p>
               </div>
               ${(ws.files || []).length
                 ? `<table class="table"><tbody>${ws.files
                     .slice(0, 100)
                     .map(
                       (file) => `
                   <tr>
                     <td style="width:100%"><strong>${esc(file.name)}</strong><div class="tiny muted">${esc(file.path)} · ${(file.size / 1024).toFixed(1)} КБ</div></td>
                     <td class="nowrap muted tiny">${fmtDate(file.modified)}</td>
                     <td class="actions"><button class="btn btn-sm" data-action="preview-file" data-folder="workspace" data-name="${esc(file.path)}">Открыть</button></td>
                   </tr>`
                     )
                     .join("")}</tbody></table>`
                 : `<div class="empty-state" style="padding:22px"><p>В рабочей области пока нет файлов</p></div>`}
             </div>`
          : ""
      }
      <div class="card">
        <div class="card-body row">
          <div class="grow">
            <strong style="font-size:13px">Загрузить файл для агентов</strong>
            <p class="hint-text" style="margin:2px 0 0">Инструмент «Прочитать файл» ищет файлы в рабочей области проекта.</p>
          </div>
          <input type="file" id="file-input" class="hidden">
          <button class="btn" data-action="pick-file">${icon("upload", 15)} Выбрать файл</button>
        </div>
      </div>
      ${block("Исходные файлы (data/uploads)", files.uploads, "uploads")}
      ${block("Результаты агентов (data/outputs)", files.outputs, "outputs")}
    </div>`;
}

/* ------------------------------------------------------------------- runs */
function newRun(crewName) {
  return {
    id: null,
    crewId: state.crew?.id || "",
    crewName,
    status: "queued",
    model: effectiveModel(state.crew),
    inputs: {},
    workspace: "",
    startedAt: Date.now(),
    endedAt: null,
    tasks: [],
    logs: [],
    usage: {},
    result: null,
    error: "",
    tab: "result",
    pendingPermissions: [],
    permissionOpen: null,
  };
}

async function startRun() {
  if (!state.crew) return;
  const button = $('[data-action="run-crew"]');
  if (button) button.disabled = true;
  try {
    if (state.dirty) await saveCrew(true);
    const validation = await api(`/api/crews/${state.crew.id}/validate`, { method: "POST", body: { crew: state.crew } });
    if (!validation.ok) {
      showValidation(validation);
      if (button) button.disabled = false;
      return;
    }
    state.placeholders = validation.placeholders || state.placeholders;
    const payload = {
      crew_id: state.crew.id,
      inputs: Object.fromEntries((state.crew.inputs || []).map((item) => [item.key, item.value])),
    };
    const response = await api("/api/runs", { method: "POST", body: payload });
    state.run = newRun(state.crew.name);
    state.run.id = response.run_id;
    state.view = "run";
    render();
    attachRun(response.run_id);
    toast("Команда запущена", "ok");
  } catch (error) {
    if (error.payload?.validation) showValidation(error.payload.validation);
    else toast(error.message, "err");
  } finally {
    if (button) button.disabled = false;
  }
}

function showValidation(validation) {
  const issues = [...(validation.errors || []), ...(validation.warnings || [])];
  if (!issues.length) return;
  openModal({
    title: validation.ok ? "Предупреждения" : "Проверьте проект",
    body: `<div class="stack">${issues
      .map(
        (issue) => `
      <div class="alert ${validation.errors?.includes(issue) ? "err" : "warn"}">
        <span>${esc(issue.field)}</span><span>${esc(issue.message)}</span>
      </div>`
      )
      .join("")}</div>`,
    footer: `<button class="btn btn-primary" data-action="close-modal">Понятно</button>`,
  });
}

function attachRun(runId) {
  closeStream();
  if (!state.run || state.run.id !== runId) {
    state.run = newRun(state.crew?.name || "Запуск");
    state.run.id = runId;
  }
  if (state.view !== "run") {
    state.view = "run";
    setHash(`run=${encodeURIComponent(runId)}`);
    render();
  }
  const es = new EventSource(`/api/runs/${runId}/events`);
  state.es = es;
  const handle = (type) => (message) => {
    let payload = {};
    try {
      payload = JSON.parse(message.data);
    } catch {
      return;
    }
    handleRunEvent(type, payload.data || {});
  };
  [
    "run_started", "plan", "crew_start", "crew_done", "task_start", "task_focus", "task_done",
    "task_failed", "agent_start", "agent_done", "tool_start", "tool_done", "tool_error",
    "llm_chunk", "usage", "warning", "info", "log", "error", "run_done", "run_cancelled", "stream_end",
  ].forEach((type) => es.addEventListener(type, handle(type)));
  es.addEventListener("error", () => {
    if (state.run && (state.run.status === "running" || state.run.status === "queued")) {
      /* transient network hiccup: EventSource reconnects on its own */
    }
  });
  startTimer();
}

function closeStream() {
  if (state.es) {
    state.es.close();
    state.es = null;
  }
  stopTimer();
}

function startTimer() {
  stopTimer();
  state.timer = setInterval(updateTimer, 500);
}

function stopTimer() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

function updateTimer() {
  const node = $("#run-timer");
  const run = state.run;
  if (!node || !run) return;
  const end = run.endedAt || Date.now();
  const seconds = Math.max(0, (end - run.startedAt) / 1000);
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  node.textContent = `${mins}:${String(secs).padStart(2, "0")}`;
}

function pushLog(line) {
  if (!state.run) return;
  state.run.logs.push(line);
  if (state.run.logs.length > 600) state.run.logs.shift();
  const consoleNode = $("#run-console");
  if (consoleNode) {
    consoleNode.textContent = state.run.logs.join("\n");
    consoleNode.scrollTop = consoleNode.scrollHeight;
  }
}

function handleRunEvent(type, data) {
  const run = state.run;
  if (!run) return;
  switch (type) {
    case "run_started":
      run.status = "running";
      run.model = data.model || run.model;
      run.inputs = data.inputs || {};
      run.workspace = data.workspace || run.workspace || "";
      pushLog(`▶ ${data.crew} · ${data.model || "модель по умолчанию"}`);
      if (run.workspace) pushLog(`📁 ${run.workspace}`);
      updateRunBanner();
      break;
    case "plan": {
      run.tasks = (data.tasks || []).map((task, index) => ({
        name: task.name || `Задача ${index + 1}`,
        agent: (state.crew?.agents || []).find((agent) => agent.id === task.agent)?.role || "",
        description: task.description || "",
        status: "pending",
        text: "",
        output: "",
        error: "",
        tools: [],
      }));
      if (state.view === "run") renderRun();
      break;
    }
    case "crew_start":
      run.status = "running";
      updateRunBanner();
      break;
    case "task_start": {
      const index = runTaskIndexByName(data.name || "");
      if (index === -1) break;
      const task = run.tasks[index];
      task.status = "active";
      task.name = data.name || task.name;
      task.agent = data.agent || task.agent;
      if (data.description && !task.description) task.description = data.description;
      pushLog(`→ ${task.name}${task.agent ? " · " + task.agent : ""}`);
      updateTaskCard(index);
      scrollRunToActive();
      break;
    }
    case "task_focus": {
      const index = runTaskIndexByName(data.name || "");
      if (index >= 0) scrollRunToActive();
      break;
    }
    case "llm_chunk": {
      const tasks = run.tasks;
      const byIndex = Number.isInteger(data.index) && data.index >= 0 && data.index < tasks.length ? data.index : -1;
      const index = byIndex !== -1 ? byIndex : runTaskIndexByName(data.task || "");
      if (index === -1) break;
      const task = tasks[index];
      if (task.status === "done" || task.status === "error") break; // late chunks after completion
      task.text += data.text || "";
      task.status = "active";
      const stream = $(`[data-idx="${index}"]`);
      if (stream) {
        stream.dataset.state = "active";
        stream.textContent = cleanStream(task.text);
        autoScroll(stream);
      } else {
        updateTaskCard(index);
      }
      break;
    }
    case "task_done": {
      const index = runTaskIndexByName(data.name || "");
      if (index === -1) break;
      const task = run.tasks[index];
      task.status = "done";
      task.output = cleanOutput(data.output || task.text);
      task.agent = data.agent || task.agent;
      pushLog(`✓ ${task.name} готово`);
      updateTaskCard(index);
      updateRunBanner();
      break;
    }
    case "task_failed": {
      const index = runTaskIndexByName(data.name || "");
      if (index === -1) break;
      const task = run.tasks[index];
      task.status = "error";
      task.error = data.error || "Ошибка задачи";
      pushLog(`✗ ${task.name}: ${task.error}`);
      updateTaskCard(index);
      break;
    }
    case "tool_start": {
      const index = runTaskIndexByName(data.task || "");
      const target = index >= 0 ? run.tasks[index] : null;
      if (target) {
        target.tools.push({ name: data.tool, args: data.args, output: "", done: false, failed: false });
        updateTaskCard(index);
      }
      pushLog(`⚙ ${data.tool}${data.args ? " " + String(data.args).slice(0, 160) : ""}`);
      break;
    }
    case "tool_done": {
      const index = runTaskIndexByName(data.task || "");
      if (index >= 0) {
        const tool = [...run.tasks[index].tools].reverse().find((item) => item.name === data.tool && !item.done);
        if (tool) {
          tool.done = true;
          tool.failed = Boolean(data.failed);
          tool.output = data.output || "";
          updateTaskCard(index);
        }
      }
      pushLog(`⚙ ${data.tool} → ${String(data.output || "").slice(0, 160)}`);
      break;
    }
    case "tool_error":
      pushLog(`⚙ ошибка ${data.tool}: ${data.error}`);
      break;
    case "usage":
      run.usage = data;
      updateRunBanner();
      break;
    case "warning":
      pushLog(`! ${data.message}`);
      break;
    case "info":
      pushLog(`· ${data.message}`);
      break;
    case "log":
      pushLog(String(data.text || "").trimEnd());
      break;
    case "error":
      run.error = data.message || "Ошибка";
      pushLog(`✗ ${run.error}`);
      if (data.traceback) pushLog(String(data.traceback));
      run.status = run.status === "cancelled" ? "cancelled" : "failed";
      updateRunBanner();
      break;
    case "permission_request":
      handlePermissionRequest(data);
      break;
    case "permission_resolved":
    case "permission_denied":
      resolvePendingPermission(data.id);
      break;
    case "run_done":
      run.result = data.result || null;
      run.status = "completed";
      run.endedAt = Date.now();
      stopTimer();
      finishPermissions();
      updateRunBanner();
      pushLog("■ Запуск завершён");
      if (state.view === "run") renderRun();
      else toast(`Запуск «${run.crewName}» завершён`, "ok", { label: "Открыть", onClick: () => openActiveRun() });
      refreshHistory();
      break;
    case "cancel_requested":
      run.status = "cancelling";
      pushLog("■ Останавливаю выполнение…");
      updateRunBanner();
      if (state.view === "run") renderRun();
      break;
    case "force_stopping":
      run.status = "force_stopping";
      pushLog(`! ${data.message || "Принудительная остановка"}`);
      updateRunBanner();
      if (state.view === "run") renderRun();
      break;
    case "run_cancelled":
      run.status = "cancelled";
      run.endedAt = Date.now();
      stopTimer();
      finishPermissions();
      updateRunBanner();
      pushLog("■ Остановлено пользователем");
      if (state.view === "run") renderRun();
      refreshHistory();
      break;
    case "stream_end":
      if (run.status === "running" || run.status === "queued") {
        run.status = "completed";
      }
      run.endedAt = run.endedAt || Date.now();
      stopTimer();
      finishPermissions();
      closeStream();
      updateRunBanner();
      refreshHistory();
      if (state.view === "run") renderRun();
      break;
    case "crew_done":
      pushLog(`■ Crew завершён, токенов: ${fmtNumber(data.tokens || 0)}`);
      break;
    default:
      break;
  }
}

function autoScroll(node) {
  const container = node.closest(".view") || document.scrollingElement;
  if (!container) return;
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 240;
  if (nearBottom) container.scrollTop = container.scrollHeight;
}

function scrollRunToActive() {
  const active = $(".task-run.active");
  if (active && state.view === "run") {
    const container = $("#view");
    const rect = active.getBoundingClientRect();
    if (rect.bottom > window.innerHeight - 40 || rect.top < 80) {
      active.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

/* ------------------------------------------------------------- permissions */
function handlePermissionRequest(data) {
  const run = state.run;
  if (!run) {
    // A request from a run we are not attached to: open it so the user can answer.
    if (state.info) toast("Агент запрашивает доступ — откройте запуск", "err");
    return;
  }
  run.pendingPermissions = run.pendingPermissions || [];
  if (run.pendingPermissions.some((item) => item.id === data.id)) return;
  run.pendingPermissions.push(data);
  pushLog(`🔐 ${data.agent || "Агент"} запрашивает доступ: ${data.reason || data.kind} — ${data.target}`);
  updateRunIndicator();
  // Replayed events can be resolved a moment later; give that a chance first.
  setTimeout(showNextPermission, 350);
}

function showNextPermission() {
  const run = state.run;
  if (!run || run.permissionOpen) return;
  const request = (run.pendingPermissions || [])[0];
  if (!request) return;
  run.permissionOpen = request.id;
  const minutes = Math.max(1, Math.round((request.timeout || 300) / 60));
  const grantText =
    request.grant === "folder"
      ? `«Разрешить до конца запуска» откроет папку: ${request.grant_target || request.target}`
      : `«Разрешить до конца запуска» откроет только файл: ${request.grant_target || request.target}`;
  openModal({
    title: "Агент запрашивает доступ",
    body: `
      <div class="alert warn" style="margin-bottom:14px">
        <span>${esc(request.reason || "Требуется разрешение")}</span>
      </div>
      <div class="field">
        <label>Что запрашивает</label>
        <div class="permission-target">${esc(request.target || "—")}</div>
      </div>
      <div class="field">
        <label>Агент</label>
        <div class="small">${esc(request.agent || "—")}</div>
      </div>
      <label class="toggle">
        <input type="checkbox" id="perm-scope">
        <span class="track"></span> Разрешить до конца запуска
      </label>
      <p class="hint-text" style="margin:8px 0 0">${esc(grantText)}</p>
      <p class="hint-text" style="margin:8px 0 0">Выполнение приостановлено, пока вы не ответите.
        Без ответа доступ закроется через ${minutes} мин.</p>`,
    footer: `<button class="btn btn-danger" data-action="perm-deny">Запретить</button>
             <button class="btn btn-primary" data-action="perm-allow">${icon("check", 15)} Разрешить</button>`,
  });
}

async function answerPermission(allow) {
  const run = state.run;
  if (!run || !run.permissionOpen) return;
  const requestId = run.permissionOpen;
  const scope = $("#perm-scope")?.checked ? "run" : "once";
  run.permissionOpen = null;
  closeModal();
  try {
    await api(`/api/runs/${run.id}/permissions/${requestId}`, { method: "POST", body: { allow, scope } });
  } catch (error) {
    toast(error.message, "err");
  }
  resolvePendingPermission(requestId, false);
}

function resolvePendingPermission(requestId, closeIfOpen = true) {
  const run = state.run;
  if (!run) return;
  const wasOpen = run.permissionOpen === requestId;
  run.pendingPermissions = (run.pendingPermissions || []).filter((item) => item.id !== requestId);
  if (wasOpen && closeIfOpen) {
    run.permissionOpen = null;
    closeModal();
  }
  updateRunIndicator();
  setTimeout(showNextPermission, 200);
}

function finishPermissions() {
  const run = state.run;
  if (!run) return;
  run.pendingPermissions = [];
  if (run.permissionOpen) {
    run.permissionOpen = null;
    closeModal();
  }
  updateRunIndicator();
}

function openActiveRun() {
  if (!state.run) return;
  state.view = "run";
  setHash(`run=${encodeURIComponent(state.run.id || "")}`);
  render();
  if (!state.es && state.run.id && (state.run.status === "running" || state.run.status === "queued")) {
    attachRun(state.run.id);
  }
}

function updateRunIndicator() {
  const node = $("#run-indicator");
  if (!node) return;
  const run = state.run;
  const running = Boolean(run && ["running", "queued", "cancelling", "force_stopping"].includes(run.status));
  const visible = running && state.view !== "run";
  node.classList.toggle("hidden", !visible);
  if (!visible) return;
  const pending = (run.pendingPermissions || []).length;
  $("#run-indicator-text").textContent = pending
    ? `${run.crewName || "Запуск"} — нужно подтверждение`
    : `${run.crewName || "Запуск"} — выполняется`;
}

/* ------------------------------------------------------------------ modal */
function openModal({ title, body, footer = "", wide = false }) {
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
}

/* ------------------------------------------------------------------- save */
let saveGeneration = 0;

async function saveCrew(force = false) {
  if (!state.crew) return;
  if (!state.dirty && !force) return;
  const generation = saveGeneration;
  state.saving = true;
  updateSaveState();
  try {
    const data = await api(`/api/crews/${state.crew.id}`, { method: "PUT", body: { crew: state.crew } });
    // A workspace change while this request was in flight wins: its response is newer.
    if (generation !== saveGeneration) return;
    state.crew = data.crew;
    state.dirty = false;
    if ((data.rejected || []).length) {
      toast(`Не распознаны поля: ${data.rejected.map((item) => item.field).join(", ")}`, "err");
    }
    await refreshCrews();
  } catch (error) {
    toast(`Не сохранено: ${error.message}`, "err");
  } finally {
    state.saving = false;
    updateSaveState();
  }
}

const saveDebounced = debounce(() => saveCrew(), 900);

function markDirty() {
  state.dirty = true;
  updateSaveState();
  saveDebounced();
}

function updateSaveState() {
  const node = $("#save-state");
  if (!node) return;
  if (state.saving) {
    node.className = "save-state saving";
    node.textContent = "· сохраняю…";
  } else if (state.dirty) {
    node.className = "save-state dirty";
    node.textContent = "· есть изменения";
  } else {
    node.className = "save-state saved";
    node.textContent = "· сохранено";
  }
}

/* --------------------------------------------------------------- actions */
async function createCrew(templateKey = null) {
  try {
    const body = templateKey ? { template: templateKey } : { crew: blankCrew() };
    const data = await api("/api/crews", { method: "POST", body });
    await refreshCrews();
    await openCrew(data.crew.id);
    toast(templateKey ? "Проект создан из шаблона" : "Проект создан", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function blankCrew() {
  const agentId = uid("a-");
  return {
    name: "Новый проект",
    description: "",
    process: "sequential",
    default_llm: "",
    agents: [
      {
        id: agentId,
        role: "Ассистент-исследователь",
        goal: "Собрать и структурировать информацию по задаче",
        backstory: "Вы внимательный аналитик: проверяете факты, отделяете главное и пишете коротко.",
        llm: "",
        tools: [],
        allow_delegation: false,
        max_iter: 12,
      },
    ],
    tasks: [
      {
        id: uid("t-"),
        name: "Первая задача",
        description: "Опишите, что нужно сделать. Используйте {переменные} из входных данных.",
        expected_output: "Понятный результат в Markdown.",
        agent: agentId,
        output_format: "markdown",
      },
    ],
    inputs: [{ key: "тема", value: "", description: "Что исследуем" }],
  };
}

function addAgent() {
  state.crew.agents.push({
    id: uid("a-"),
    role: "",
    goal: "",
    backstory: "",
    llm: "",
    tools: [],
    allow_delegation: false,
    max_iter: 12,
    reasoning: false,
    cache: true,
    verbose: false,
  });
  markDirty();
  renderBuilder();
  renderTopbar();
}

function addTask() {
  const agents = state.crew.agents || [];
  state.crew.tasks.push({
    id: uid("t-"),
    name: "",
    description: "",
    expected_output: "",
    agent: agents.length === 1 ? agents[0].id : "",
    context: [],
    async_execution: false,
    human_input: false,
    output_format: "markdown",
    output_file: "",
    tools: [],
  });
  markDirty();
  renderBuilder();
  renderTopbar();
}

function deleteCrewById(crewId) {
  const crew = state.crews.find((item) => item.id === crewId) || (state.crew?.id === crewId ? state.crew : null);
  if (!crew) return;
  openModal({
    title: "Удалить проект?",
    body: `<p class="muted">Проект «${esc(crew.name)}» и его настройки будут удалены. История запусков останется.</p>
           <p class="hint-text">Отменить это действие нельзя.</p>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-danger" data-action="confirm-delete-crew" data-id="${esc(crew.id)}">Удалить</button>`,
  });
}

async function confirmDeleteCrew(crewId) {
  const id = crewId || state.crew?.id;
  if (!id) return;
  try {
    await api(`/api/crews/${id}`, { method: "DELETE" });
    closeModal();
    if (state.crew?.id === id) state.crew = null;
    await refreshCrews();
    if (state.crew) {
      render();
    } else if (state.crews.length) {
      await openCrew(state.crews[0].id);
    } else {
      state.view = "welcome";
      setHash("");
      render();
    }
    toast("Проект удалён", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

/* --------------------------------------------------------- optional tools */
async function refreshTools() {
  const data = await api("/api/tools");
  state.tools = data.tools || [];
  if (state.view === "builder") renderBuilder();
}

function openInstallToolDialog(tool) {
  openModal({
    title: "Инструмент не установлен",
    body: `<p style="margin-top:0">«${esc(tool.label)}» входит в пакет <b>crewai-tools</b>, которого нет в окружении.
             Встроенные инструменты (чтение, запись, список файлов, загрузка страницы, дата) работают и так.</p>
           <p class="hint-text">Установка скачает ~200 МБ зависимостей (chromadb, эмбеддинги) и займёт несколько минут.
             Нужен интернет.</p>
           <pre class="console" id="install-log" style="display:none;max-height:220px"></pre>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Закрыть</button>
             <button class="btn btn-primary" data-action="install-tools">${icon("download", 15)} Установить пакет</button>`,
  });
}

async function installExtras() {
  const log = $("#install-log");
  const button = $('[data-action="install-tools"]');
  if (button) button.disabled = true;
  try {
    await api("/api/tools/install", { method: "POST" });
    if (log) {
      log.style.display = "block";
      log.textContent = "Установка…";
    }
    const timer = setInterval(async () => {
      let status = null;
      try {
        status = await api("/api/tools/install");
      } catch {
        return;
      }
      if (log && status.output) {
        log.textContent = status.output;
        log.scrollTop = log.scrollHeight;
      }
      if (!status.running) {
        clearInterval(timer);
        if (status.ok) {
          await refreshTools();
          closeModal();
          toast("Пакет crewai-tools установлен — инструменты доступны", "ok");
        } else {
          if (button) button.disabled = false;
          toast(status.error || "Установка не удалась — подробности в окне", "err");
        }
      }
    }, 1500);
  } catch (error) {
    if (button) button.disabled = false;
    toast(error.message, "err");
  }
}

/* --------------------------------------------------------- custom templates */
function openNewTemplateDialog() {
  const projects = state.crews || [];
  if (!projects.length) {
    toast("Сначала создайте проект — шаблон сохраняется из проекта", "err");
    return;
  }
  openModal({
    title: "Новый шаблон",
    body: `<p class="hint-text" style="margin-top:0">Шаблон — сохранённая конфигурация проекта: агенты с ролями, задачи, входные данные и параметры.
             Его можно применить к новому проекту в один клик.</p>
      <div class="field">
        <label>Из какого проекта</label>
        <select id="tpl-source">
          ${projects.map((project) => `<option value="${esc(project.id)}">${esc(project.name)}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label>Название шаблона</label>
        <input type="text" id="tpl-title" value="${esc(projects[0]?.name || "")}" placeholder="Например: Мой бриф">
      </div>
      <div class="field">
        <label>Описание</label>
        <textarea id="tpl-desc" rows="2" placeholder="Что делает этот шаблон"></textarea>
      </div>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-primary" data-action="confirm-new-template">${icon("save", 15)} Сохранить шаблон</button>`,
  });
}

async function saveNewTemplate() {
  const crewId = $("#tpl-source")?.value || "";
  const title = $("#tpl-title")?.value?.trim() || "";
  const description = $("#tpl-desc")?.value || "";
  if (!crewId || !title) {
    toast("Выберите проект и укажите название", "err");
    return;
  }
  try {
    await api("/api/templates", { method: "POST", body: { crew_id: crewId, title, description } });
    await refreshTemplates();
    closeModal();
    toast("Шаблон создан", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function openEditTemplateDialog(key, title, description) {
  openModal({
    title: "Изменить шаблон",
    body: `<div class="field"><label>Название</label><input type="text" id="tpl-edit-title" value="${esc(title)}"></div>
           <div class="field"><label>Описание</label><textarea id="tpl-edit-desc" rows="2">${esc(description || "")}</textarea></div>
           <p class="hint-text" style="margin:0">Название и описание меняются; агенты и задачи шаблона остаются прежними.</p>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-primary" data-action="confirm-edit-template" data-key="${esc(key)}">Сохранить</button>`,
  });
}

async function saveTemplateEdits(key) {
  const title = $("#tpl-edit-title")?.value?.trim() || "";
  const description = $("#tpl-edit-desc")?.value || "";
  if (!title) {
    toast("Укажите название шаблона", "err");
    return;
  }
  try {
    await api(`/api/templates/${key}`, { method: "PUT", body: { title, description } });
    await refreshTemplates();
    closeModal();
    toast("Шаблон обновлён", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function openTemplateDialog() {
  if (!state.crew) return;
  openModal({
    title: "Сохранить как шаблон",
    body: `<p class="hint-text" style="margin-top:0">В шаблон попадёт текущая структура: агенты с ролями, задачи, входные данные и параметры.</p>
      <div class="field"><label>Название шаблона</label>
        <input type="text" id="tpl-title" value="${esc(state.crew.name)}" placeholder="Например: Мой бриф">
      </div>
      <div class="field"><label>Описание</label>
        <textarea id="tpl-desc" rows="2" placeholder="Что делает этот шаблон">${esc(state.crew.description || "")}</textarea>
      </div>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-primary" data-action="confirm-save-template">${icon("save", 15)} Сохранить шаблон</button>`,
  });
}

async function saveTemplateFromCrew() {
  if (!state.crew) return;
  const title = $("#tpl-title")?.value?.trim() || "";
  const description = $("#tpl-desc")?.value || "";
  if (!title) {
    toast("Укажите название шаблона", "err");
    return;
  }
  try {
    if (state.dirty) await saveCrew(true);
    await api("/api/templates", { method: "POST", body: { crew_id: state.crew.id, title, description } });
    await refreshTemplates();
    closeModal();
    toast("Шаблон сохранён", "ok", { label: "Открыть", onClick: () => go("templates") });
  } catch (error) {
    toast(error.message, "err");
  }
}

function deleteTemplate(key, title) {
  openModal({
    title: "Удалить шаблон?",
    body: `<p class="muted">Шаблон «${esc(title || "без названия")}» будет удалён. Проекты, созданные из него, останутся.</p>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-danger" data-action="confirm-delete-template" data-key="${esc(key)}">Удалить</button>`,
  });
}

async function confirmDeleteTemplate(key) {
  try {
    await api(`/api/templates/${key}`, { method: "DELETE" });
    closeModal();
    await refreshTemplates();
    toast("Шаблон удалён", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

/* ------------------------------------------------------------------- roles */
async function saveRole(roleId) {
  const payload = {
    name: $("#role-name")?.value?.trim() || "",
    goal: $("#role-goal")?.value || "",
    experience: $("#role-experience")?.value || "",
    character: $("#role-character")?.value || "",
    tools: $$("#role-tools .tool-option.on").map((node) => node.dataset.tool),
  };
  if (!payload.name) {
    toast("Укажите название роли", "err");
    return;
  }
  try {
    if (roleId) await api(`/api/roles/${roleId}`, { method: "PUT", body: payload });
    else await api("/api/roles", { method: "POST", body: payload });
    await refreshRoles();
    closeModal();
    toast(roleId ? "Роль обновлена" : "Роль создана", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function deleteRole(roleId, name) {
  openModal({
    title: "Удалить роль?",
    body: `<p class="muted">Роль «${esc(name || "без названия")}» исчезнет из библиотеки. У уже созданных агентов тексты останутся.</p>`,
    footer: `<button class="btn btn-ghost" data-action="close-modal">Отмена</button>
             <button class="btn btn-danger" data-action="confirm-delete-role" data-id="${esc(roleId)}">Удалить</button>`,
  });
}

async function confirmDeleteRole(roleId) {
  try {
    await api(`/api/roles/${roleId}`, { method: "DELETE" });
    closeModal();
    await refreshRoles();
    toast("Роль удалена", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

async function resetRoles() {
  if (!confirm("Вернуть стандартный набор ролей? Ваши роли будут удалены.")) return;
  try {
    const data = await api("/api/roles/reset", { method: "POST" });
    state.roles = data.roles || [];
    renderRoles();
    renderTopbar();
    toast("Список ролей сброшен", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

async function showCode() {
  if (!state.crew) return;
  if (state.dirty) await saveCrew(true);
  try {
    const data = await api(`/api/crews/${state.crew.id}/code`);
    openModal({
      title: "Python-код проекта",
      wide: true,
      body: `<p class="hint-text" style="margin-top:0">Тот же запуск воспроизводится в консоли: сохраните файл рядом с проектом и выполните <code>python crew.py</code>.</p>
             <pre class="code-block" id="code-block">${esc(data.code)}</pre>`,
      footer: `<button class="btn btn-ghost" data-action="close-modal">Закрыть</button>
               <button class="btn" data-action="copy-code">${icon("copy", 15)} Скопировать</button>
               <button class="btn btn-primary" data-action="download-code">${icon("download", 15)} Скачать .py</button>`,
    });
  } catch (error) {
    toast(error.message, "err");
  }
}

async function useTemplate(key) {
  await createCrew(key);
}

async function openRunDetail(runId) {
  try {
    const data = await api(`/api/runs/${runId}`);
    const stored = data.run;
    const resultTasks = stored.result?.tasks || [];
    const streamed = stored.task_text || {};
    const startedNames = (stored.events || [])
      .filter((event) => event.type === "task_start")
      .map((event) => event.data?.name)
      .filter(Boolean);
    const tasks = resultTasks.length
      ? resultTasks.map((task, index) => ({
          name: task.name || `Задача ${index + 1}`,
          agent: task.agent || "",
          description: task.description || "",
          status: "done",
          text: "",
          output: cleanOutput(task.output || ""),
          error: "",
          tools: [],
        }))
      : startedNames.map((name, index) => ({
          name: name || `Задача ${index + 1}`,
          agent: "",
          description: "",
          status: stored.status === "cancelled" ? "error" : "pending",
          text: cleanOutput(streamed[name] || ""),
          output: "",
          error: "",
          tools: [],
        }));
    state.run = {
      id: stored.id,
      crewName: stored.crew_name,
      status: stored.status,
      model: stored.model || "",
      inputs: stored.inputs || {},
      workspace: stored.workspace || "",
      startedAt: stored.started_at ? new Date(stored.started_at).getTime() : Date.now(),
      endedAt: stored.finished_at ? new Date(stored.finished_at).getTime() : Date.now(),
      tasks,
      logs: (stored.events || []).map((event) => `${event.type}: ${JSON.stringify(event.data).slice(0, 200)}`),
      usage: stored.result?.token_usage || stored.usage || {},
      result: stored.result || null,
      error: stored.error || "",
      tab: "result",
    };
    state.view = "run";
    setHash(`run=${encodeURIComponent(runId)}`);
    render();
    if (data.live && (stored.status === "running" || stored.status === "queued")) attachRun(runId);
  } catch (error) {
    toast(error.message, "err");
  }
}

async function cancelRun() {
  if (!state.run?.id) return;
  try {
    await api(`/api/runs/${state.run.id}/cancel`, { method: "POST" });
    if (state.run.status === "running" || state.run.status === "queued") {
      state.run.status = "cancelling";
      updateRunBanner();
      if (state.view === "run") renderRun();
    }
    toast("Останавливаю…", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

async function detachRun() {
  if (!state.run?.id) return;
  try {
    await api(`/api/runs/${state.run.id}/detach`, { method: "POST" });
    state.run.status = "cancelled";
    state.run.endedAt = Date.now();
    finishPermissions();
    stopTimer();
    updateRunBanner();
    if (state.view === "run") renderRun();
    toast("Запуск отсоединён — можно запускать новый", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function exportRun(runId, format) {
  const id = runId || state.run?.id;
  if (!id) return;
  window.location.href = `/api/runs/${id}/export?format=${encodeURIComponent(format || "md")}`;
}

async function testLlm() {
  const modelInput = $('[data-setting="default_llm"]');
  const result = $("#test-result");
  if (result) result.textContent = "проверяю…";
  try {
    const data = await api("/api/llm/test", { method: "POST", body: { model: modelInput?.value || "" } });
    if (result) result.innerHTML = `<span class="chip ok">${icon("check", 12)} ${esc(data.model)} · ${data.latency} с</span>`;
  } catch (error) {
    if (result) result.innerHTML = `<span class="chip err">${esc(error.message.slice(0, 220))}</span>`;
  }
}

/* ------------------------------------------------------- settings helpers */
function collectSettings() {
  const settings = { ...(state.settings || {}) };
  delete settings.secret_flags;
  delete settings.env_flags;
  $$("[data-setting]").forEach((node) => {
    const key = node.dataset.setting;
    if (node.type === "checkbox") settings[key] = node.checked;
    else settings[key] = node.value;
  });
  const extra = {};
  const seen = new Set();  $$("#env-rows [data-env-row]").forEach((row) => {
    const key = $("[data-env-key]", row)?.value?.trim();
    const value = $("[data-env-value]", row)?.value ?? "";
    if (!key) return;
    seen.add(key);
    extra[key] = value; // empty means "keep the stored encrypted value"
  });
  // Rows the user removed must actually be deleted, not silently kept.
  Object.keys(settings.extra_env || {}).forEach((key) => {
    if (!seen.has(key)) extra[key] = "__clear__";
  });
  settings.extra_env = extra;
  // The switch is stored as an explicit list: enabling one network tool must not enable all.
  if (settings.allow_network_tools === true) {
    settings.allow_network_tools = (state.tools || [])
      .filter((tool) => tool.policy === "third-party-network")
      .map((tool) => tool.name);
  } else if (!settings.allow_network_tools) {
    settings.allow_network_tools = [];
  }
  const rootsArea = $("#fs-roots");
  if (rootsArea) {
    settings.fs_roots = rootsArea.value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
  }
  return settings;
}

async function saveSettings() {
  try {
    const data = await api("/api/settings", { method: "PUT", body: { settings: collectSettings() } });
    state.settings = data.settings;
    toast("Настройки сохранены", "ok");
    renderSidebar();
    if (state.view === "settings") renderSettings();
  } catch (error) {
    toast(error.message, "err");
  }
}

/* ---------------------------------------------------------------- events */
function bindGlobalEvents() {
  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-action], [data-crew], [data-view]");
    if (!trigger) return;

    if (trigger.dataset.crew) {
      await openCrew(trigger.dataset.crew);
      return;
    }
    if (trigger.dataset.view && !trigger.dataset.action) {
      go(trigger.dataset.view);
      return;
    }

    const action = trigger.dataset.action;
    switch (action) {
      case "toggle-sidebar":
        document.body.classList.toggle("sidebar-open");
        break;
      case "new-crew":
        await createCrew();
        break;
      case "goto":
        go(trigger.dataset.view);
        break;
      case "toggle-agent": {
        const id = trigger.dataset.id;
        if (state.collapsed.has(id)) state.collapsed.delete(id);
        else state.collapsed.add(id);
        trigger.closest(".agent-card").classList.toggle("collapsed");
        break;
      }
      case "delete-agent": {
        const index = Number(trigger.dataset.index);
        const agent = state.crew.agents[index];
        state.crew.agents.splice(index, 1);
        state.crew.tasks.forEach((task) => {
          if (task.agent === agent.id) task.agent = "";
          task.context = (task.context || []).filter((id) => id !== agent.id);
        });
        markDirty();
        renderBuilder();
        renderTopbar();
        break;
      }
      case "add-agent":
        addAgent();
        break;
      case "add-task":
        addTask();
        break;
      case "delete-task": {
        const index = Number(trigger.dataset.index);
        const [removed] = state.crew.tasks.splice(index, 1);
        state.crew.tasks.forEach((task) => {
          task.context = (task.context || []).filter((id) => id !== removed.id);
        });
        markDirty();
        renderBuilder();
        renderTopbar();
        break;
      }
      case "move-task": {
        const index = Number(trigger.dataset.index);
        const dir = Number(trigger.dataset.dir);
        const target = index + dir;
        if (target < 0 || target >= state.crew.tasks.length) break;
        const [task] = state.crew.tasks.splice(index, 1);
        state.crew.tasks.splice(target, 0, task);
        markDirty();
        renderBuilder();
        break;
      }
      case "toggle-tool": {
        const index = Number(trigger.dataset.index);
        const name = trigger.dataset.tool;
        const tool = toolByName(name);
        if (tool && !tool.available) {
          openInstallToolDialog(tool);
          break;
        }
        const agent = state.crew.agents[index];
        agent.tools = agent.tools || [];
        if (agent.tools.includes(name)) agent.tools = agent.tools.filter((item) => item !== name);
        else agent.tools.push(name);
        trigger.classList.toggle("on");
        markDirty();
        break;
      }
      case "toggle-context": {
        const index = Number(trigger.dataset.index);
        const ctx = trigger.dataset.ctx;
        const task = state.crew.tasks[index];
        task.context = task.context || [];
        if (task.context.includes(ctx)) task.context = task.context.filter((id) => id !== ctx);
        else task.context.push(ctx);
        trigger.classList.toggle("on");
        markDirty();
        break;
      }
      case "add-input": {
        state.crew.inputs = state.crew.inputs || [];
        state.crew.inputs.push({ key: "", value: "", description: "" });
        markDirty();
        renderBuilder();
        break;
      }
      case "delete-input":
        state.crew.inputs.splice(Number(trigger.dataset.index), 1);
        markDirty();
        renderBuilder();
        break;
      case "add-missing-inputs": {
        const declared = new Set((state.crew.inputs || []).map((item) => item.key));
        (state.placeholders || []).forEach((name) => {
          if (!declared.has(name)) state.crew.inputs.push({ key: name, value: "", description: "" });
        });
        markDirty();
        renderBuilder();
        break;
      }
      case "delete-crew":
        if (state.crew) deleteCrewById(state.crew.id);
        break;
      case "delete-crew-by-id":
        deleteCrewById(trigger.dataset.id);
        break;
      case "confirm-delete-crew":
        await confirmDeleteCrew(trigger.dataset.id);
        break;
      case "apply-role": {
        const index = Number(trigger.dataset.index);
        const agent = state.crew?.agents?.[index];
        const known = agent ? roleByName(agent.role) : null;
        if (known) applyRole(index, known.id);
        else openRolePicker(index);
        break;
      }
      case "pick-workspace":
        openWorkspacePicker(state.workspaceInfo?.path || "");
        break;
      case "reset-workspace":
        await setWorkspace("");
        break;
      case "fs-open":
        await loadPicker(trigger.dataset.path || "").catch(() => {});
        break;
      case "fs-go":
        await loadPicker($("#fs-path")?.value || "").catch(() => {});
        break;
      case "fs-mkdir":
        await makePickerDir();
        break;
      case "fs-choose":
        closeModal();
        await setWorkspace(pickerPath);
        break;
      case "pick-role":
        closeModal();
        applyRole(Number(trigger.dataset.index), trigger.dataset.id);
        break;
      case "save-as-template":
        openTemplateDialog();
        break;
      case "new-template":
        openNewTemplateDialog();
        break;
      case "install-tools":
        await installExtras();
        break;
      case "confirm-new-template":
        await saveNewTemplate();
        break;
      case "edit-template":
        openEditTemplateDialog(trigger.dataset.key, trigger.dataset.title, trigger.dataset.description);
        break;
      case "confirm-edit-template":
        await saveTemplateEdits(trigger.dataset.key);
        break;
      case "confirm-save-template":
        await saveTemplateFromCrew();
        break;
      case "delete-template":
        deleteTemplate(trigger.dataset.key, trigger.dataset.title);
        break;
      case "confirm-delete-template":
        await confirmDeleteTemplate(trigger.dataset.key);
        break;
      case "new-role":
        openRoleEditor();
        break;
      case "edit-role": {
        const role = (state.roles || []).find((item) => item.id === trigger.dataset.id);
        if (role) openRoleEditor(role);
        break;
      }
      case "delete-role":
        deleteRole(trigger.dataset.id, trigger.dataset.name);
        break;
      case "confirm-delete-role":
        await confirmDeleteRole(trigger.dataset.id);
        break;
      case "save-role":
        await saveRole(trigger.dataset.id);
        break;
      case "reset-roles":
        await resetRoles();
        break;
      case "toggle-role-tool":
        trigger.classList.toggle("on");
        break;
      case "show-code":
        await showCode();
        break;
      case "duplicate-crew": {
        try {
          if (state.dirty) await saveCrew(true);
          const data = await api(`/api/crews/${state.crew.id}/duplicate`, { method: "POST" });
          await refreshCrews();
          await openCrew(data.crew.id);
          toast("Создана копия проекта", "ok");
        } catch (error) {
          toast(error.message, "err");
        }
        break;
      }
      case "run-crew":
        await startRun();
        break;
      case "back-to-builder":
        state.view = "builder";
        render();
        break;
      case "open-active-run":
        openActiveRun();
        break;
      case "perm-allow":
        await answerPermission(true);
        break;
      case "perm-deny":
        await answerPermission(false);
        break;
      case "cancel-run":
        await cancelRun();
        break;
      case "detach-run":
        await detachRun();
        break;
      case "export-run":
        exportRun(trigger.dataset.run, trigger.dataset.format);
        break;
      case "rerun":
        if (state.crew) {
          state.view = "builder";
          render();
          setTimeout(() => startRun(), 50);
        }
        break;
      case "run-tab": {
        state.run.tab = trigger.dataset.tab;
        if (state.view === "run") renderRun();
        break;
      }
      case "copy-result":
        await navigator.clipboard?.writeText(state.run?.result?.raw || "");
        toast("Результат скопирован", "ok");
        break;
      case "copy-code": {
        const code = $("#code-block")?.textContent || "";
        await navigator.clipboard?.writeText(code);
        toast("Код скопирован", "ok");
        break;
      }
      case "download-code": {
        const code = $("#code-block")?.textContent || "";
        const blob = new Blob([code], { type: "text/x-python" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${(state.crew?.name || "crew").replace(/[^\wа-яА-Я-]+/g, "_")}.py`;
        link.click();
        URL.revokeObjectURL(link.href);
        break;
      }
      case "use-template":
        await useTemplate(trigger.dataset.key);
        break;
      case "open-run":
        await openRunDetail(trigger.dataset.run);
        break;
      case "delete-run": {
        if (!confirm("Удалить запись о запуске?")) break;
        try {
          await api(`/api/runs/${trigger.dataset.run}`, { method: "DELETE" });
          await refreshHistory();
          toast("Запись удалена", "ok");
        } catch (error) {
          toast(error.message, "err");
        }
        break;
      }
      case "refresh-history":
        await refreshHistory();
        break;
      case "refresh-files":
        await refreshFiles();
        break;
      case "save-settings":
        await saveSettings();
        break;
      case "clear-key": {
        const field = trigger.dataset.field;
        if (!confirm("Удалить сохранённый ключ?")) break;
        try {
          const data = await api("/api/settings", { method: "PUT", body: { settings: { [field]: "__clear__" } } });
          state.settings = data.settings;
          if (state.view === "settings") renderSettings();
          toast("Ключ удалён", "ok");
        } catch (error) {
          toast(error.message, "err");
        }
        break;
      }
      case "test-llm":
        await testLlm();
        break;
      case "set-theme": {
        const theme = trigger.dataset.theme;
        state.settings = { ...(state.settings || {}), theme };
        document.documentElement.dataset.theme = theme;
        $$("#theme-switch button").forEach((button) => button.classList.toggle("active", button.dataset.theme === theme));
        await api("/api/settings", { method: "PUT", body: { settings: { theme } } });
        break;
      }
      case "add-env": {
        const rows = $("#env-rows");
        const index = rows.children.length;
        rows.insertAdjacentHTML(
          "beforeend",
          `<div class="row" style="margin-bottom:8px" data-env-row="${index}">
            <input type="text" data-env-key placeholder="ПЕРЕМЕННАЯ" style="max-width:220px;font-family:var(--mono);font-size:12px">
            <input type="password" data-env-value placeholder="значение">
            <button class="btn btn-icon" data-action="remove-env" data-index="${index}">${icon("x", 14)}</button>
          </div>`
        );
        break;
      }
      case "remove-env":
        trigger.closest("[data-env-row]")?.remove();
        break;
      case "clear-history": {
        if (!confirm("Удалить все записи о запусках? Проекты останутся.")) break;
        try {
          await Promise.all(state.runs.map((run) => api(`/api/runs/${run.id}`, { method: "DELETE" })));
          await refreshHistory();
          toast("История очищена", "ok");
        } catch (error) {
          toast(error.message, "err");
        }
        break;
      }
      case "pick-file":
        $("#file-input")?.click();
        break;
      case "preview-file": {
        const name = trigger.dataset.name;
        const crewQuery = state.crew ? `?crew_id=${encodeURIComponent(state.crew.id)}` : "";
        try {
          const data = await api(`/api/files/output/${encodeURIComponent(name)}${crewQuery}`);
          openModal({
            title: name,
            wide: true,
            body: `<pre class="code-block">${esc(data.content || "(файл пуст)")}</pre>`,
            footer: `<button class="btn btn-primary" data-action="close-modal">Закрыть</button>`,
          });
        } catch (error) {
          toast(error.message, "err");
        }
        break;
      }
      case "copy-workspace": {
        const path =
          state.view === "run"
            ? state.run?.workspace || ""
            : state.workspaceInfo?.path || state.files?.workspace?.path || "";
        if (path) {
          await navigator.clipboard?.writeText(path);
          toast("Путь скопирован", "ok");
        }
        break;
      }
      case "close-modal":
        closeModal();
        break;
      default:
        break;
    }
  });

  document.addEventListener("input", (event) => {
    const node = event.target;
    if (node.dataset?.field && state.crew) {
      let value = node.type === "checkbox" ? node.checked : node.value;
      if (node.type === "number") value = Number(value);
      setByPath(state.crew, node.dataset.field, value);
      markDirty();
      const agentField = /^agents\.(\d+)\.(role|goal)$/.exec(node.dataset.field);
      if (agentField) {
        const agent = (state.crew.agents || [])[Number(agentField[1])];
        const card = agent ? document.querySelector(`[data-agent-card="${agent.id}"]`) : null;
        if (card) {
          if (agentField[2] === "role") {
            const title = card.querySelector(".agent-title strong");
            if (title) title.textContent = node.value || "Без роли";
            document.querySelectorAll('select[data-field^="tasks."] option').forEach((option) => {
              if (option.value === agent.id) option.textContent = node.value || "Без роли";
            });
          } else {
            const sub = card.querySelector(".agent-title span");
            if (sub) sub.textContent = node.value || "цель не задана";
          }
        }
      }
    } else if (node.dataset?.setting) {
      /* settings are collected on save */
    }
  });

  document.addEventListener("change", async (event) => {
    const node = event.target;
    if (node.id === "tpl-source") {
      const project = (state.crews || []).find((item) => item.id === node.value);
      if (project) $("#tpl-title").value = project.name;
      return;
    }
    if (node.id === "workspace-input") {
      await setWorkspace(node.value);
      return;
    }
    if (!node.dataset?.field || !state.crew) return;
    if (node.tagName === "SELECT" || node.type === "checkbox") {
      const value = node.type === "checkbox" ? node.checked : node.value;
      setByPath(state.crew, node.dataset.field, value);
      markDirty();
      if (["process", "tasks.0.output_format"].includes(node.dataset.field) || node.dataset.field.includes("output_format") || node.dataset.field === "process") {
        renderBuilder();
        renderTopbar();
      }
    }
    const roleField = /^agents\.(\d+)\.role$/.exec(node.dataset.field || "");
    if (roleField) {
      const index = Number(roleField[1]);
      const role = roleByName(node.value);
      if (role) {
        applyRole(index, role.id);
      } else {
        const agent = (state.crew.agents || [])[index];
        if (agent && agent.role_id) {
          agent.role_id = "";
          markDirty();
        }
      }
    }
  });

  document.addEventListener("change", async (event) => {
    if (event.target.id !== "file-input") return;
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const body = { name: file.name, data: String(reader.result).split(",")[1] };
        if (state.crew) body.crew_id = state.crew.id;
        const result = await api("/api/files", { method: "POST", body });
        toast(result.in_workspace ? "Файл загружен в рабочую область" : "Файл загружен", "ok");
        await refreshFiles();
      } catch (error) {
        toast(error.message, "err");
      }
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  });

  window.addEventListener("hashchange", async () => {
    const route = parseHash();
    try {
      if (route.run && state.run?.id !== route.run) {
        await openRunDetail(route.run);
      } else if (route.crew && state.crew?.id !== route.crew) {
        await openCrew(route.crew);
      } else if (route.crew && state.view !== "builder") {
        state.view = "builder";
        render();
      } else if (route.view && state.view !== route.view) {
        go(route.view);
      }
    } catch (error) {
      toast(error.message, "err");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
      document.body.classList.remove("sidebar-open");
    }
    if (event.key === "Enter" && event.target?.classList?.contains("crew-item")) {
      event.preventDefault();
      if (event.target.dataset.crew) openCrew(event.target.dataset.crew);
    }
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveCrew(true);
    }
    if (mod && event.key === "Enter" && state.view === "builder") {
      event.preventDefault();
      startRun();
    }
  });
}

/* ------------------------------------------------------------------- boot */
bindGlobalEvents();
init();
