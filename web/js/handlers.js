/* CrewAI Studio — front-end (vanilla JS, no build step) */
"use strict";

/* Global event delegation: clicks, inputs, keyboard shortcuts. */

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
      case "allow-root":
        await allowRoot(trigger.dataset.path || "");
        break;
      case "fs-mkdir":
        await makePickerDir();
        break;
      case "fs-default":
        closeModal();
        await setWorkspace("");
        break;
      case "fs-choose":
        if (!pickerAccess.writable) {
          toast("В эту папку нельзя записывать: выберите другую или разрешите доступ", "err");
          break;
        }
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
        await openTemplateEditor(trigger.dataset.key);
        break;
      case "change-password": {
        const current = $("#password-current")?.value || "";
        const next = $("#password-new")?.value || "";
        try {
          await api("/api/auth/password", { method: "POST", body: { current, new: next } });
          toast("Пароль изменён", "ok");
          if ($("#password-current")) $("#password-current").value = "";
          if ($("#password-new")) $("#password-new").value = "";
        } catch (error) {
          toast(error.message, "err");
        }
        break;
      }
      case "logout-all": {
        try {
          await api("/api/auth/logout-all", { method: "POST" });
        } catch (error) {
          /* ignore and go to the login page anyway */
        }
        window.location.replace("/login");
        break;
      }
      case "logout": {
        try {
          await api("/api/auth/logout", { method: "POST" });
        } catch (error) {
          /* ignore and go to the login page anyway */
        }
        window.location.replace("/login");
        break;
      }
      case "save-template-crew":
        await saveTemplateCrew();
        break;
      case "cancel-template-edit":
        cancelTemplateEdit();
        break;
      case "empty-template":
        await createEmptyTemplate();
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
    if (node.dataset?.setting === "ui_language") {
      const chosen = node.value === "en" ? "en" : "ru";
      state.settings = { ...(state.settings || {}), ui_language: chosen };
      StudioI18n.setLang(chosen);
      await saveSettings(chosen);
      return;
    }
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
StudioI18n.watch();
