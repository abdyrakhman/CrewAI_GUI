/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* Project/template builder: agents, tasks, parameters, saving. */

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
            <label class="toggle" title="CrewAI запрашивает подтверждение только в консоли — в графическом интерфейсе недоступно">
              <input type="checkbox" data-field="tasks.${index}.human_input" ${task.human_input ? "checked" : ""} disabled>
              <span class="track"></span> Запрос подтверждения у человека <span class="hint">— только в консоли</span>
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
  const isTemplate = Boolean(state.templateEdit);
  const knownPlaceholders = state.placeholders || [];
  const declared = new Set((crew.inputs || []).map((item) => item.key));
  const missing = knownPlaceholders.filter((name) => !declared.has(name));

  $("#view").innerHTML = `
  <div class="view-inner">
    <div class="builder-grid">
      <div class="stack">
        <div class="card">
          <div class="card-head">
            <h2>${isTemplate ? "Шаблон" : "Проект"}</h2>
            <span class="spacer"></span>
            ${isTemplate ? "" : `<button class="btn btn-ghost btn-sm" data-action="delete-crew">${icon("trash", 14)} Удалить</button>`}
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
            ${isTemplate ? `<p class="hint-text" style="margin:0">Рабочая область выбирается в проекте — в шаблон она не входит.</p>` : `            <div class="field">
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
            </div>`}
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
            ${isTemplate
              ? `<button class="btn btn-primary btn-block" data-action="save-template-crew" style="padding:11px">${icon("save", 15)} Сохранить шаблон</button>
                 <p class="hint-text" style="margin:9px 0 0;text-align:center">Агенты и задачи сохранятся в шаблоне</p>`
              : `<button class="btn btn-primary btn-block" data-action="run-crew" style="padding:11px">${icon("play", 15)} Запустить команду</button>
                 <p class="hint-text" style="margin:9px 0 0;text-align:center">${icon("info", 12)} Ctrl + Enter</p>`}
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

let saveGeneration = 0;

async function openTemplateEditor(key) {
  try {
    const data = await api(`/api/templates/${key}`);
    const entry = data.template || {};
    const crew = entry.crew || {};
    state.templateEdit = { key, title: entry.title || "", description: entry.description || "" };
    state.crew = {
      ...crew,
      id: "__template__",
      name: entry.title || crew.name || "Шаблон",
      workspace: "",
    };
    state.workspaceInfo = null;
    state.placeholders = [];
    state.validation = null;
    state.dirty = false;
    state.view = "builder";
    setHash("");
    render();
    renderTopbar();
    toast("Редактирование шаблона: добавьте агентов и задачи", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

async function saveTemplateCrew() {
  const edit = state.templateEdit;
  if (!edit || !state.crew) return;
  const spec = JSON.parse(JSON.stringify(state.crew));
  delete spec.id;
  delete spec.created_at;
  delete spec.updated_at;
  spec.workspace = "";
  try {
    await api(`/api/templates/${edit.key}`, {
      method: "PUT",
      body: {
        title: state.crew.name || edit.title || "Шаблон",
        description: state.crew.description || "",
        crew: spec,
      },
    });
    state.dirty = false;
    updateSaveState();
    await refreshTemplates();
    toast("Шаблон сохранён", "ok");
  } catch (error) {
    toast(error.message, "err");
  }
}

function cancelTemplateEdit() {
  state.templateEdit = null;
  state.crew = null;
  state.dirty = false;
  go("templates");
}

async function createEmptyTemplate() {
  try {
    const data = await api("/api/templates", {
      method: "POST",
      body: { title: "Новый шаблон", crew: { name: "Новый шаблон", agents: [], tasks: [] } },
    });
    await refreshTemplates();
    await openTemplateEditor(data.template.key);
  } catch (error) {
    toast(error.message, "err");
  }
}

async function saveCrew(force = false) {
  if (!state.crew) return;
  if (state.templateEdit) return; // templates are saved explicitly
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
