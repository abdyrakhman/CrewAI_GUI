/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* Bootstrap: load data, open the requested view, start the app. */

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
    try {
      const me = await api("/api/auth/me");
      state.user = me.user || null;
    } catch (error) {
      state.user = null;
    }
    StudioI18n.setLang(state.settings?.ui_language === "en" ? "en" : "ru");
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
  state.templateEdit = null;
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

init();
