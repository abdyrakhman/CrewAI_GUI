/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* Run screen: start, SSE events, task cards, permissions. */

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
    <div id="stream-banner" class="alert err hidden" style="margin-bottom:12px">
      <div class="row" style="gap:12px;align-items:center">
        <span class="grow" id="stream-banner-text">Связь с запуском потеряна — переподключаюсь…</span>
        <button class="btn btn-sm" data-action="reconnect-stream">Переподключиться</button>
      </div>
    </div>
    <div id="perm-banner" class="alert warn hidden" style="margin-bottom:12px">
      <div class="row" style="gap:12px;align-items:center">
        <span class="grow" id="perm-banner-text">Запуск ждёт подтверждения доступа</span>
        <button class="btn btn-sm" data-action="show-permission">Открыть запрос</button>
      </div>
    </div>
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
  es.addEventListener("open", () => {
    if (state.run) state.run.streamLost = false;
    updateStreamBanner();
  });
  es.addEventListener("error", () => {
    if (state.run && (state.run.status === "running" || state.run.status === "queued")) {
      state.run.streamLost = true;
      updateStreamBanner();
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
  const text = String(line);
  state.run.logs.push(text.length > 400 ? `${text.slice(0, 400)}…` : text);
  if (state.run.logs.length > 400) state.run.logs.shift();
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
        target.tools.push({ name: data.tool, args: String(data.args || "").slice(0, 300), output: "", done: false, failed: false });
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

function updateStreamBanner() {
  const banner = $("#stream-banner");
  if (!banner) return;
  const lost = Boolean(state.run && state.run.streamLost);
  banner.classList.toggle("hidden", !lost);
}

function updatePermissionBanner() {
  const banner = $("#perm-banner");
  if (!banner) return;
  const pending = state.run?.pendingPermissions || [];
  if (!pending.length) {
    banner.classList.add("hidden");
    return;
  }
  const first = pending[0];
  const text = $("#perm-banner-text");
  if (text) text.textContent = `Запуск ждёт подтверждения доступа: ${first.target || first.kind || "запрос"} (${pending.length})`;
  banner.classList.remove("hidden");
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
    onClose: () => {
      if (run.permissionOpen === request.id) {
        run.permissionOpen = null;
        toast("Запуск ждёт подтверждения доступа — вернитесь к запросу", "err");
      }
      updateRunIndicator();
      updatePermissionBanner();
    },
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
  updatePermissionBanner();
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
  updatePermissionBanner();
}

function reconnectStream() {
  if (!state.run?.id) return;
  state.run.streamLost = false;
  attachRun(state.run.id);
  updateStreamBanner();
}

function reopenPermission() {
  if (!state.run) return;
  state.run.permissionOpen = null;
  showNextPermission();
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

async function openRunDetail(runId) {
  try {
    state.templateEdit = null;
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
