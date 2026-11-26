/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* Pages: history, templates, roles, files, settings, workspace picker. */

function renderWelcome() {
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="card" style="overflow:hidden">
        <div style="padding:44px 40px;background:radial-gradient(900px 220px at 10% -10%, rgba(139,92,246,.18), transparent)">
          <div class="row" style="gap:10px"><span class="chip accent">${icon("spark", 13)} CrewAI Studio</span></div>
          <h1 style="margin:14px 0 8px;font-size:26px;letter-spacing:-.6px">Команда ИИ-агентов — в графическом интерфейсе</h1>
          <p class="muted" style="max-width:620px;margin:0 0 22px;font-size:14px">
            Соберите агентов и задачи, задайте модель и нажмите «Запустить». Всё, что раньше требовало консоли,
            доступно здесь: настройки, шаги агентов и инструментов, история запусков и готовый Python-код.
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

let historyPage = { limit: 50, offset: 0, status: "", total: 0 };
let logText = "";

async function refreshHistory(offset = 0, status = null) {
  if (status !== null) {
    historyPage.status = status;
    historyPage.offset = 0;
  } else {
    historyPage.offset = Math.max(0, Number(offset) || 0);
  }
  try {
    const params = new URLSearchParams({
      limit: String(historyPage.limit),
      offset: String(historyPage.offset),
    });
    if (historyPage.status) params.set("status", historyPage.status);
    const data = await api(`/api/runs?${params.toString()}`);
    state.runs = data.runs || [];
    historyPage.total = Number(data.total || 0);
    historyPage.offset = Number(data.offset || 0);
    historyPage.limit = Number(data.limit || 50);
    if (state.view === "history") renderHistory();
  } catch (error) {
    toast(error.message, "err");
  }
}

function renderHistory() {
  const total = historyPage.total || 0;
  const from = total ? historyPage.offset + 1 : 0;
  const to = Math.min(historyPage.offset + state.runs.length, total);
  const statuses = [["", "Все статусы"], ["completed", "Завершён"], ["failed", "Ошибка"], ["cancelled", "Остановлен"]];
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="card">
        <div class="card-head">
          <h2>Запуски</h2>
          <span class="spacer"></span>
          <span class="small muted">${countLabel(total, RECORDS)}</span>
        </div>
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
        ${
          total
            ? `<div class="card-body row" style="gap:10px;align-items:center;border-top:1px solid #232838">
                 <span class="small muted">Показано ${from}–${to} из ${total}</span>
                 <span class="spacer grow"></span>
                 <select id="history-status" style="max-width:170px">
                   ${statuses.map(([value, label]) => `<option value="${value}"${historyPage.status === value ? " selected" : ""}>${label}</option>`).join("")}
                 </select>
                 <button class="btn btn-sm" data-action="history-prev" ${historyPage.offset <= 0 ? "disabled" : ""}>← Назад</button>
                 <button class="btn btn-sm" data-action="history-next" ${to >= total ? "disabled" : ""}>Вперёд →</button>
               </div>`
            : ""
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

let pickerAccess = { readable: true, writable: true };

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
    pickerAccess = { readable: data.readable !== false, writable: data.writable !== false };
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
        <span class="hint-text">${data.readable
          ? data.writable
            ? "чтение и запись доступны"
            : "только для чтения: Windows не разрешает запись. Выберите папку, куда можно писать (например, внутри E:\\CrewAI), или вернитесь к папке по умолчанию."
          : "нет доступа к папке"}</span>
        ${data.writable ? "" : `<button class="btn btn-sm" data-action="fs-default">Папка по умолчанию</button>`}
      </div>`;
    const chooseButton = $('[data-action="fs-choose"]');
    if (chooseButton) {
      chooseButton.disabled = !data.writable;
      chooseButton.title = data.writable ? "" : "Нужны права на запись в папку";
    }
  } catch (error) {
    container.innerHTML = pickerErrorPanel(path, error.message);
    throw error;
  }
}

function pickerErrorPanel(path, message) {
  return `<div class="alert err">${esc(message)}</div>
    <p class="hint-text">Проводник видит домашнюю папку и папку проекта. Другой корень можно разрешить
      одной кнопкой — он сохранится в настройках и будет доступен и дальше.</p>
    <div class="row" style="gap:8px;margin-top:10px">
      <button class="btn btn-primary" data-action="allow-root" data-path="${esc(path || "")}" ${path ? "" : "disabled"}>
        ${icon("check", 15)} Разрешить эту папку
      </button>
      <button class="btn btn-ghost" data-action="fs-open" data-path="">Домашняя папка</button>
    </div>`;
}

async function allowRoot(path) {
  const raw = String(path || "").trim();
  if (!raw) return;
  const current = Array.isArray(state.settings?.fs_roots) ? state.settings.fs_roots : [];
  if (!current.some((item) => String(item).toLowerCase() === raw.toLowerCase())) {
    try {
      const data = await api("/api/settings", {
        method: "PUT",
        body: { settings: { fs_roots: [...current, raw] } },
      });
      state.settings = data.settings;
    } catch (error) {
      toast(error.message, "err");
      return;
    }
  }
  toast(`Папка разрешена: ${raw}`, "ok");
  try {
    await loadPicker(raw);
  } catch {
    /* the panel already explains what happened */
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

async function showLog(errorsOnly) {
  try {
    const data = await api(`/api/logs/recent?limit=150${errorsOnly ? "&errors=1" : ""}`);
    logText = (data.lines || []).join("\n") || "Записей нет";
    openModal({
      title: errorsOnly ? "Последние ошибки" : "Последние записи журнала",
      wide: true,
      body: `<p class="hint-text">Файл: <span class="mono">${esc(data.file || "")}</span></p>
             <pre style="max-height:52vh;overflow:auto;background:#0f1220;border:1px solid #232838;border-radius:10px;padding:12px;font-size:12px;white-space:pre-wrap;word-break:break-all">${esc(logText)}</pre>`,
      footer: `<button class="btn btn-ghost" data-action="copy-log">${icon("copy", 15)} Копировать</button>
               <button class="btn btn-primary" data-action="close-modal">Закрыть</button>`,
    });
  } catch (error) {
    toast(error.message, "err");
  }
}

function renderSettings() {
  const settings = state.settings || {};
  $("#view").innerHTML = `
    <div class="view-inner">
      <div class="settings-grid">
        <div class="stack">
          <div class="card">
            <div class="card-head"><h2>Аккаунт</h2></div>
            <div class="card-body">
              <div class="row" style="gap:10px;align-items:center">
                <div class="grow">
                  <strong>${esc(state.user || "—")}</strong>
                  <p class="hint-text" style="margin:2px 0 0">Вход в интерфейс защищён паролем</p>
                </div>
                <button class="btn btn-ghost btn-sm" data-action="logout">${icon("back", 14)} Выйти</button>
                <button class="btn btn-ghost btn-sm" data-action="logout-all">Выйти везде</button>
              </div>
              <div class="row" style="gap:8px;margin-top:12px">
                <input type="password" id="password-current" placeholder="Текущий пароль" autocomplete="current-password" style="flex:1">
                <input type="password" id="password-new" placeholder="Новый пароль (от 8 символов)" autocomplete="new-password" style="flex:1">
                <button class="btn btn-sm" data-action="change-password">Сменить</button>
              </div>
              <div class="field" style="margin-top:14px">
                <label>Время жизни сессии <span class="hint">сколько действует вход без повторного пароля</span></label>
                <select data-setting="session_ttl_hours">
                  ${[1, 8, 12, 24, 72, 168].map((hours) => `<option value="${hours}"${
                    Number(settings.session_ttl_hours || 12) === hours ? " selected" : ""
                  }>${hours === 1 ? "1 час" : hours < 24 ? `${hours} часов` : hours === 24 ? "1 день" : `${hours / 24} дн.`}</option>`).join("")}
                </select>
                <span class="hint-text">Применяется к новым входам. Смена времени не завершает текущую сессию.</span>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Интерфейс</h2></div>
            <div class="card-body">
              <div class="field">
                <label>Язык интерфейса</label>
                <select data-setting="ui_language">
                  <option value="ru"${settings.ui_language !== "en" ? " selected" : ""}>Русский</option>
                  <option value="en"${settings.ui_language === "en" ? " selected" : ""}>English</option>
                </select>
                <span class="hint-text">Интерфейс перерисуется сразу после выбора. Ключи, проекты и история не меняются.</span>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card">
            <div class="card-head"><h2>Резервная копия</h2></div>
            <div class="card-body">
              <p class="hint-text" style="margin:0 0 10px">Архив с проектами, ролями, шаблонами, настройками и аккаунтами.
                Логи и сессии не входят. Ключи API остаются зашифрованными и привязаны к этой машине.</p>
              <div class="row-wrap" style="gap:8px">
                <button class="btn" data-action="backup">${icon("download", 15)} Скачать .zip</button>
                <button class="btn btn-ghost btn-sm" data-action="backup" data-runs="1">с историей запусков</button>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>История запусков</h2></div>
            <div class="card-body">
              <div class="field">
                <label>Хранить запуски</label>
                <select data-setting="runs_retention_days">
                  ${[[30, "30 дней"], [90, "90 дней"], [180, "180 дней"], [365, "1 год"], [0, "Хранить всегда"]]
                    .map(([days, label]) => `<option value="${days}"${Number(settings.runs_retention_days ?? 180) === days ? " selected" : ""}>${label}</option>`)
                    .join("")}
                </select>
                <span class="hint-text">Старые запуски удаляются при следующем старте приложения. Всего хранится не больше 5000 записей.</span>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Диагностика</h2></div>
            <div class="card-body">
              <p class="hint-text" style="margin:0 0 10px">
                Журнал приложения: <span class="mono">data/logs/app-YYYYMMDD.jsonl</span>. Внутренние ошибки
                содержат <code>error_id</code> — код можно скопировать из уведомления или из журнала.
              </p>
              <div class="row-wrap" style="gap:8px">
                <button class="btn" data-action="show-errors"> Последние ошибки</button>
                <button class="btn btn-ghost btn-sm" data-action="show-log">Последние записи</button>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h2>Модели по умолчанию</h2></div>
            <div class="card-body">
              <div class="field">
                <label>Модель</label>
                <input type="text" data-setting="default_llm" value="${esc(settings.default_llm || "")}" list="settings-models" placeholder="openai/gpt-4o-mini">
                <span class="hint-text">Формат: провайдер/модель, например <code>openai/gpt-4o-mini</code>, <code>ollama/llama3.1</code>.</span>
              </div>
              <div class="row-wrap" style="gap:18px;margin-top:4px">
                
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

async function useTemplate(key) {
  await createCrew(key);
}

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

async function saveSettings(preferredLanguage) {
  try {
    const data = await api("/api/settings", { method: "PUT", body: { settings: collectSettings() } });
    // Older or foreign backends may not know ui_language yet: keep the choice the
    // user just made instead of silently reverting to Russian.
    state.settings = {
      ...data.settings,
      ui_language: data.settings?.ui_language || preferredLanguage || state.settings?.ui_language || "ru",
    };
    toast("Настройки сохранены", "ok");
    renderSidebar();
    if (state.view === "settings") renderSettings();
    StudioI18n.setLang(state.settings?.ui_language === "en" ? "en" : "ru");
  } catch (error) {
    toast(error.message, "err");
  }
}

/* ---------------------------------------------------------------- events */
