/* UI localisation: Russian source strings -> English, applied to the rendered DOM.
 *
 * The app renders Russian text directly, so instead of rewriting every template
 * this module keeps a phrase book and translates text nodes and attributes after
 * render. Originals are remembered, so switching back to Russian restores exactly
 * what the code produced. User data (project names, prompts) is never in the
 * phrase book, so it stays untouched.
 */
(function () {
  "use strict";

  const EN = {
    "(файл пуст)": "(file is empty)",
    "0 — без ограничения. Агент будет остановлен по времени.": "0 — no limit. The agent will be stopped by time.",
    "CrewAI не установлен": "CrewAI is not installed",
    "D:\\Проекты": "D:\\Projects",
    "Python-код проекта": "Project Python code",
    "· КБ": "· KB",
    "· есть изменения": "· unsaved changes",
    "· сохранено": "· saved",
    "· сохраняю…": "· saving…",
    "Агент": "Agent",
    "Агент запрашивает доступ": "The agent requests access",
    "Агент запрашивает доступ — откройте запуск": "The agent requests access — open the run",
    "Ассистент-исследователь": "Research assistant",
    "Базовый URL (необязательно, для прокси и совместимых API)": "Base URL (optional, for proxies and compatible APIs)",
    "Без описания": "No description",
    "Без роли": "No role",
    "Без цели": "No goal",
    "Библиотека ролей пуста — создайте роль в разделе «Роли»": "The role library is empty — create a role in the Roles section",
    "Библиотека ролей: цель, опыт и характер подставляются агенту": "Role library: goal, experience and character are applied to an agent",
    "Вернуть папку по умолчанию": "Reset to the default folder",
    "Вернуть стандартный набор ролей? Ваши роли будут удалены.": "Restore the default roles? Your roles will be deleted.",
    "Вернуться к выполнению": "Back to the run",
    "Возобновляю просмотр активного запуска": "Resuming the active run view",
    "Все выполненные и остановленные прогоны": "All finished and stopped runs",
    "Вставьте ключ API (OpenAI, OpenRouter, DeepSeek, Ollama — любой).": "Paste an API key (OpenAI, OpenRouter, DeepSeek, Ollama — any).",
    "Вы внимательный аналитик: проверяете факты, отделяете главное и пишете коротко.": "You are a careful analyst: check facts, separate what matters, write briefly.",
    "Выберите проект и укажите название": "Choose a project and enter a title",
    "Выше": "Up",
    "Готовлю команду агентов…": "Preparing the agent team…",
    "Готовые команды агентов — создайте проект в один клик": "Ready-made agent teams — create a project in one click",
    "Данные для агентов и результаты их работы": "Agent inputs and the results they produce",
    "Добавить их": "Add them",
    "Ещё запуск": "Run again",
    "Журнал пуст.": "The log is empty.",
    "Задайте шаги": "Describe the steps",
    "Задача": "Task",
    "Задачи выполняются по порядку, результат предыдущей виден следующей.": "Tasks run in order; each one sees the previous result.",
    "Запись удалена": "Record deleted",
    "Запуск": "Run",
    "Запуск отсоединён — можно запускать новый": "Run detached — you can start a new one",
    "Запустите start.bat один раз — он создаст окружение и поставит зависимости.": "Run start.bat once — it creates the environment and installs dependencies.",
    "Изменить": "Edit",
    "Изменить шаблон": "Edit template",
    "Или возьмите готовый шаблон из раздела «Шаблоны».": "Or pick a ready template in the Templates section.",
    "Имя новой папки": "New folder name",
    "Имя файла результата": "Result file name",
    "Инструмент не установлен": "Tool is not installed",
    "Инструменты": "Tools",
    "История запусков": "Run history",
    "История очищена": "History cleared",
    "Исходные файлы (data/uploads)": "Source files (data/uploads)",
    "К проектам": "To projects",
    "К проектам Новый шаблон": "To projects New template",
    "К редактору": "To editor",
    "Как агент думает и пишет": "How the agent thinks and writes",
    "Ключ удалён": "Key deleted",
    "Ключи API, модели и поведение интерфейса": "API keys, models and interface behaviour",
    "Код скопирован": "Code copied",
    "Команда запущена": "Team started",
    "Контекст результаты этих задач попадут в промпт": "Context results of these tasks go into the prompt",
    "Меню": "Menu",
    "Модель менеджера": "Manager model",
    "Нажмите «Запустить»": "Press Run",
    "Название задачи": "Task name",
    "Например: Исследование рынка": "For example: Market research",
    "Например: Исследователь": "For example: Researcher",
    "Например: Мой бриф": "For example: My brief",
    "Настройки": "Settings",
    "Настройки сохранены": "Settings saved",
    "Нет агентов Добавьте первого агента: роль, цель и предыстория.": "No agents Add the first agent: role, goal and backstory.",
    "Нет задач Опишите шаги, которые должна выполнить команда.": "No tasks Describe the steps the team must perform.",
    "Ниже": "Down",
    "Новая роль": "New role",
    "Новый проект": "New project",
    "Новый шаблон": "New template",
    "Обновить": "Refresh",
    "Опишите команду": "Describe the team",
    "Опишите опыт, подход и характер агента": "Describe the agent's experience, approach and character",
    "Опыт": "Experience",
    "Опыт и профессиональный бэкграунд": "Experience and professional background",
    "Останавливаю…": "Stopping…",
    "Остановить": "Stop",
    "Ответы моделей печатаются в реальном времени, итог сохраняется в историю.": "Model answers stream in real time; the result is saved to history.",
    "Откройте любой проект и нажмите «В шаблон» в верхней панели — он появится здесь.": "Open any project and press Save as template in the top bar — it will appear here.",
    "Откройте настройки": "Open settings",
    "Открыть": "Open",
    "Отменить": "Cancel",
    "Отсоединить": "Detach",
    "Отчёт .md": "Report .md",
    "Ошибка": "Error",
    "Ошибка задачи": "Task error",
    "ПЕРЕМЕННАЯ": "VARIABLE",
    "Пакет crewai-tools установлен — инструменты доступны": "crewai-tools is installed — tools are available",
    "Первая задача": "First task",
    "Перед каждым изменением файла спрашивать подтверждение": "Ask for confirmation before every file change",
    "Пока нет запусков История появится после первого запуска команды.": "No runs yet History appears after the first run.",
    "Понятный результат в Markdown.": "A clear result in Markdown.",
    "Предупреждения": "Warnings",
    "Итог": "Summary",
    "По задачам": "Per task",
    "Журнал": "Log",
    "Результат": "Result",
    "Применить роль из библиотеки": "Apply a role from the library",
    "Принудительная остановка": "Forced stop",
    "Проверьте проект": "Check the project",
    "Проект Статус Начало Длительность Токены": "Project Status Started Duration Tokens",
    "Проект создан": "Project created",
    "Проект создан из шаблона": "Project created from a template",
    "Проект удалён": "Project deleted",
    "Проекты": "Projects",
    "Пусто": "Empty",
    "Путь скопирован": "Path copied",
    "Рабочая область проекта": "Project workspace",
    "Рабочая область сохранена": "Workspace saved",
    "Рабочая область:": "Workspace:",
    "Рабочая область: папка по умолчанию": "Workspace: default folder",
    "Редактировать": "Edit",
    "Результат скопирован": "Result copied",
    "Результаты агентов (data/outputs)": "Agent results (data/outputs)",
    "Роли": "Roles",
    "Роль обновлена": "Role updated",
    "Роль создана": "Role created",
    "Роль удалена": "Role deleted",
    "Роль, цель и предыстория для каждого агента — от этого зависит качество.": "Role, goal and backstory for each agent — quality depends on them.",
    "Сбросить к стандартным Новая роль": "Reset to defaults New role",
    "Своих шаблонов нет": "No custom templates",
    "Сессия устарела или запрос отклонён защитой. Обновите страницу (Ctrl+F5).": "The session expired or the request was rejected. Reload the page (Ctrl+F5).",
    "Скачать отчёт": "Download report",
    "Скопировать путь": "Copy path",
    "Сначала создайте проект — шаблон сохраняется из проекта": "Create a project first — templates are saved from a project",
    "Соберите команду": "Build the team",
    "Собрать и структурировать информацию по задаче": "Collect and structure information for the task",
    "Создана копия проекта": "Project copy created",
    "Сохранить как шаблон": "Save as template",
    "Список ролей сброшен": "Role list reset",
    "Сюда агенты пишут файлы и отсюда читают исходные данные.": "Agents write files here and read inputs from here.",
    "Такой роли нет в библиотеке. Откройте раздел «Роли», чтобы создать её.": "No such role in the library. Open Roles to create it.",
    "Требуется разрешение": "Permission required",
    "Удалить": "Delete",
    "Удалить агента": "Delete agent",
    "Удалить все записи о запусках? Проекты останутся.": "Delete all run records? Projects will stay.",
    "Удалить задачу": "Delete task",
    "Удалить запись о запуске?": "Delete this run record?",
    "Удалить ключ": "Delete key",
    "Удалить проект": "Delete project",
    "Удалить проект?": "Delete the project?",
    "Удалить роль": "Delete role",
    "Удалить роль?": "Delete the role?",
    "Удалить сохранённый ключ?": "Delete the saved key?",
    "Удалить шаблон": "Delete template",
    "Удалить шаблон?": "Delete the template?",
    "Укажите имя папки": "Enter a folder name",
    "Укажите название роли": "Enter a role name",
    "Укажите название шаблона": "Enter a template title",
    "Установка не удалась — подробности в окне": "Installation failed — see details in the window",
    "Установка…": "Installing…",
    "Файл загружен": "File uploaded",
    "Файл загружен в рабочую область": "File uploaded to the workspace",
    "Файлы проекта": "Project files",
    "Формат и критерии готового результата": "Format and criteria for the final result",
    "Характер": "Character",
    "Цель не задана": "No goal set",
    "Что агент должен сделать": "What the agent should do",
    "Что делает эта команда": "What this team does",
    "Что делает этот шаблон": "What this template does",
    "Что исследуем": "What to research",
    "Что нужно сделать, шаг за шагом": "What to do, step by step",
    "Что этот агент должен делать": "What this agent should do",
    "Шаблон обновлён": "Template updated",
    "Шаблон создан": "Template created",
    "Шаблон сохранён": "Template saved",
    "Шаблон удалён": "Template deleted",
    "Шаблоны": "Templates",
    "агент": "agent",
    "агента": "agents",
    "агентов": "agents",
    "без названия": "untitled",
    "без роли": "no role",
    "будет создана": "will be created",
    "в очереди": "queued",
    "вызов": "call",
    "выполняется": "running",
    "готово": "done",
    "доступны": "available",
    "завершено": "finished",
    "задач": "tasks",
    "задача": "task",
    "задачи": "tasks",
    "записей": "records",
    "записи": "records",
    "запись": "record",
    "значение": "value",
    "иерархия": "hierarchical",
    "имя": "name",
    "ключ сохранён и зашифрован": "key saved and encrypted",
    "локальный интерфейс": "local interface",
    "мин с": "min s",
    "модель по умолчанию": "default model",
    "не установлен": "not installed",
    "Сбросить к стандартным": "Reset to defaults",
    "Специалист поддержки": "Support specialist",
    "Менеджер проекта": "Project manager",
    "Проектирует системы под нагрузку: границы модулей, состояние, ошибки, наблюдаемость.": "Designs systems for load: module boundaries, state, errors, observability.",
    "Прагматичный, не любит преждевременных абстракций, думает о сопровождении.": "Pragmatic, dislikes premature abstractions, thinks about maintenance.",
    "название, цель, опыт, характер": "name, goal, experience, character",
    "Мои шаблоны": "My templates",
    "Стандартные": "Built-in",
    "Популярное": "Popular",
    "серые — из пакета crewai-tools, нажмите, чтобы установить": "grey ones come from crewai-tools — click to install",
    "D:Проекты": "D:\\Projects",
    "не установлен, нажмите, чтобы поставить пакет": "not installed, click to install the package",
    "нет": "no",
    "нет прав на запись": "no write permission",
    "ожидает": "pending",
    "останавливается…": "stopping…",
    "остановлено": "stopped",
    "ошибка": "error",
    "папка доступна для записи": "folder is writable",
    "папка есть": "folder exists",
    "пока пусто": "empty for now",
    "последовательно": "sequential",
    "принудительно останавливается": "force stopping",
    "проверка окружения…": "checking environment…",
    "проверяю…": "checking…",
    "работает": "working",
    "роль из библиотеки": "role from the library",
    "с": "s",
    "сбой": "failure",
    "тема": "theme",
    "файл": "file",
    "файла": "files",
    "файлов": "files",
    "цель не задана": "no goal set",
    "шаблон": "template",
    "шаблона": "templates",
    "шаблонов": "templates",
    "■ Запуск завершён": "■ Run finished",
    "■ Останавливаю выполнение…": "■ Stopping the run…",
    "■ Остановлено пользователем": "■ Stopped by the user",
    "Пока нет проектов": "No projects yet",
    "Разделы": "Sections",
    "Интерфейс": "Interface",
    "Язык интерфейса": "Interface language",
    "Интерфейс перерисуется сразу после выбора. Ключи, проекты и история не меняются.": "The interface updates immediately. Keys, projects and history stay the same.",
    "Модели по умолчанию": "Default models",
    "Модель": "Model",
    "Формат: провайдер/модель, например": "Format: provider/model, for example",
    "Потоковая передача ответов": "Stream model responses",
    "Сетевые инструменты третьих сторон": "Third-party network tools",
    "Сторонние инструменты («crewai-tools») работают вне песочницы приложения: их запросы и чтение файлов не проходят проверку доступа. Включайте, только если доверяете инструменту.": "Third-party tools (crewai-tools) run outside the app sandbox: their requests and file reads bypass access checks. Enable only if you trust the tool.",
    "Проверить подключение": "Test connection",
    "Ключи API": "API keys",
    "хранятся локально в data/settings.json": "stored locally in data/settings.json",
    "Ollama (локально)": "Ollama (local)",
    "локальный сервер": "local server",
    "не требует ключа": "no key required",
    "LM Studio / vLLM (OpenAI-совместимый)": "LM Studio / vLLM (OpenAI-compatible)",
    "Дополнительные переменные окружения": "Extra environment variables",
    "Например": "For example",
    "для веб-поиска или": "for web search or",
    "для локальной модели.": "for a local model.",
    "Добавить переменную": "Add variable",
    "Оформление": "Appearance",
    "Тема": "Theme",
    "Тёмная": "Dark",
    "Светлая": "Light",
    "Сохранить настройки": "Save settings",
    "Доступ к папкам": "Folder access",
    "Проводник рабочей области видит домашнюю папку и папку проекта. Добавьте нужные корни — по одному в строке.": "The workspace browser sees the home folder and the project folder. Add extra roots, one per line.",
    "Разрешить эту папку": "Allow this folder",
    "Папка разрешена: ": "Folder allowed: ",
    "Проводник видит домашнюю папку и папку проекта. Другой корень можно разрешить одной кнопкой — он сохранится в настройках и будет доступен и дальше.": "The browser sees the home folder and the project folder. Any other root can be allowed with one button — it is saved in settings and stays available.",
    "Домашняя папка": "Home folder",
    "Папка вне разрешённых каталогов. Добавьте нужный корень в настройках.": "The folder is outside the allowed roots. Allow it below or add a root in settings.",
    "Окружение": "Environment",
    "Потоковые события": "Streaming events",
    "Данные": "Data",
    "Проекты, история и ключи лежат в папке": "Projects, history and keys live in the folder",
    "рядом с приложением.": "next to the application.",
    "Очистить историю запусков": "Clear run history",
    "Выполняется": "Running",
    "Ключ API": "API key",
    "В шаблон": "Save as template",
    "Код": "Code",
    "Дублировать": "Duplicate",
    "Запустить": "Run",
    "Проект": "Project",
    "Название": "Name",
    "Описание": "Description",
    "Рабочая область": "Workspace",
    "папка, в которой агенты читают и пишут файлы": "folder where agents read and write files",
    "Выбрать": "Choose",
    "по умолчанию": "default",
    "Команда": "Team",
    "Роль": "Role",
    "или выберите готовую кнопкой справа": "or pick one with the button on the right",
    "пусто — модель проекта": "empty — project model",
    "Цель": "Goal",
    "Предыстория": "Backstory",
    "характер и опыт — влияет на стиль": "character and experience — affects style",
    "Прочитать файл": "Read file",
    "Записать файл": "Write file",
    "Список файлов": "List files",
    "Загрузить страницу": "Fetch page",
    "Дата и время": "Date and time",
    "Дополнительные · пакет crewai-tools": "Extra · crewai-tools package",
    "Делегирование": "Delegation",
    "Рассуждения": "Reasoning",
    "Подтверждение изменений": "Confirm changes",
    "Макс. итераций": "Max iterations",
    "Лимит времени, с": "Time limit, s",
    "Задачи": "Tasks",
    "Ожидаемый результат": "Expected output",
    "Исполнитель": "Assignee",
    "— не выбран —": "— none —",
    "Формат результата": "Output format",
    "Текст": "Text",
    "Файл в data/outputs": "File in data/outputs",
    "Дополнительно: контекст и флаги": "Advanced: context and flags",
    "Асинхронно": "Asynchronous",
    "Запрос подтверждения у человека": "Ask a human for confirmation",
    "Параметры": "Parameters",
    "Процесс": "Process",
    "Последовательный": "Sequential",
    "Иерархический (с менеджером)": "Hierarchical (with manager)",
    "Модель проекта": "Project model",
    "используется по умолчанию": "used by default",
    "Память": "Memory",
    "Планирование": "Planning",
    "Подробный лог": "Verbose log",
    "Входные данные": "Inputs",
    "Запустить команду": "Start the team",
    "можно вставлять {переменные} из входных данных": "you can insert {variables} from the inputs",
    "Опишите, что нужно сделать. Используйте {переменные} из входных данных.": "Describe what to do. Use {variables} from the inputs.",
    "Не удалось загрузить приложение": "Failed to load the application",
    "Повреждённые файлы проектов": "Damaged project files",
    "Настройки интерфейса": "Interface settings",
  };

  // Words that appear inside short composed labels ("1 агент · 1 задача").
  const EN_WORDS = {
    "агент": "agent",
    "агента": "agents",
    "агентов": "agents",
    "задача": "task",
    "задачи": "tasks",
    "задач": "tasks",
    "файл": "file",
    "файла": "files",
    "файлов": "files",
    "запись": "record",
    "записи": "records",
    "записей": "records",
    "шаблон": "template",
    "шаблона": "templates",
    "шаблонов": "templates",
    "роль": "role",
    "цель": "goal",
    "опыт": "experience",
    "характер": "character",
    "инструменты": "tools",
    "последовательно": "sequential",
    "иерархический": "hierarchical",
    "вызовов": "calls",
    "токенов": "tokens",
    "время": "time",
    "статус": "status",
    "итог": "result",
    "журнал": "log",
    "входные": "input",
    "данные": "data",
    "контекст": "context",
    "формат": "format",
    "модель": "model",
    "порядок": "order",
    "шаг": "step",
    "минут": "minutes",
    "секунд": "seconds",
  };

  const PATTERNS = [
    [/^(\d+)\/(\d+) задач$/, "$1/$2 tasks"],
    [/^(\d+)\/(\d+) задачи$/, "$1/$2 tasks"],
    [/^(\d+)\s+агент$/, "$1 agent"],
    [/^(\d+)\s+задача$/, "$1 task"],
    [/^(\d+)\s+файл$/, "$1 file"],
    [/^(\d+)\s+запись$/, "$1 record"],
    [/^(\d+)\s+шаблон$/, "$1 template"],
    [/^(\d+)\s+агент(а|ов)$/, "$1 agents"],
    [/^(\d+)\s+задач(а|и)?$/, "$1 tasks"],
    [/^(\d+)\s+файл(а|ов)$/, "$1 files"],
    [/^(\d+)\s+запис(ь|и|ей)$/, "$1 records"],
    [/^(\d+)\s+шаблон(а|ов)$/, "$1 templates"],
    [/^(\d+)\s+мин$/, "$1 min"],
    [/^Готово за (.+) с · токенов: (.+)$/, "Done in $1 s · tokens: $2"],
    [/^Рабочая область: (.+)$/, "Workspace: $1"],
    [/^Запуск «(.+)» (.+)$/, "Run \"$1\" $2"],
    [/^Задача «(.+)»$/, "Task \"$1\""],
    [/^Агент «(.+)»$/, "Agent \"$1\""],
    [/^(\d+)\s+агент\(ов\)$/, "$1 agent(s)"],
    [/^(\d+)\s+шаг\(ов\)$/, "$1 step(s)"],
    [/^(\d+)\s+step\(ов\)$/, "$1 step(s)"],
    [/^модели: (.+)$/, "models: $1"],
    [/^Проект «(.+)»$/, "Project \"$1\""],
    [/^(.+) агентов$/, "$1 agents"],
    [/^таймаут (.+)$/, "timeout $1"],
  ];

  Object.assign(EN, window.__EN_CONTENT__ || {});

  const origin = new WeakMap();
  const attrOrigin = new WeakMap();
  let lang = "ru";

  function translateText(text) {
    if (!text || !/[А-Яа-яЁё]/.test(text)) return text;
    const lead = (text.match(/^\s*/) || [""])[0];
    const trail = (text.match(/\s*$/) || [""])[0];
    const collapsed = text.replace(/\s+/g, " ").trim();
    if (!collapsed) return text;

    const finish = (value) => lead + value + trail;

    const suffix = " — не установлен, нажмите, чтобы поставить пакет";
    if (collapsed.endsWith(suffix)) {
      const base = translateText(collapsed.slice(0, -suffix.length));
      return finish(base + " — not installed, click to install the package");
    }
    if (collapsed.endsWith(" ↓")) {
      const base = translateText(collapsed.slice(0, -2));
      return finish(base + " ↓");
    }

    for (const [re, replacement] of PATTERNS) {
      if (re.test(collapsed)) return finish(collapsed.replace(re, replacement));
    }
    if (EN[collapsed]) return finish(EN[collapsed]);
    if (EN_WORDS[collapsed]) return finish(EN_WORDS[collapsed]);
    if (collapsed.length <= 70 && /\d/.test(collapsed)) {
      let changed = collapsed;
      for (const [ru, en] of Object.entries(EN_WORDS)) {
        changed = changed.replace(new RegExp(`(^|[^А-Яа-яЁё])${ru}(?=$|[^А-Яа-яЁё])`, "g"), `$1${en}`);
      }
      if (changed !== collapsed) return finish(changed);
    }
    return text;
  }

  function translateNode(node) {
    if (!node) return;
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      if (!parent || parent.closest("[data-no-i18n]")) return;
      if (!origin.has(node)) origin.set(node, node.nodeValue);
      const base = origin.get(node);
      const next = lang === "en" ? translateText(base) : base;
      if (node.nodeValue !== next) node.nodeValue = next;
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.closest && node.closest("[data-no-i18n]")) return;
    for (const attr of ["placeholder", "title", "aria-label"]) {
      const value = node.getAttribute(attr);
      if (!value || !/[А-Яа-яЁё]/.test(value)) continue;
      let store = attrOrigin.get(node);
      if (!store) {
        store = {};
        attrOrigin.set(node, store);
      }
      if (!(attr in store)) store[attr] = value;
      const base = store[attr];
      const next = lang === "en" ? translateText(base) : base;
      if (node.getAttribute(attr) !== next) node.setAttribute(attr, next);
    }
    for (const child of node.childNodes) translateNode(child);
  }

  function apply(root) {
    translateNode(root || document.body);
  }

  function setLang(next) {
    lang = next === "en" ? "en" : "ru";
    document.documentElement.lang = lang;
    apply(document.body);
  }

  function watch() {
    const observer = new MutationObserver((mutations) => {
      if (lang !== "en") {
        for (const mutation of mutations) {
          if (mutation.type === "childList") {
            for (const node of mutation.addedNodes) if (node.nodeType) lazy(node);
          }
        }
        return;
      }
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) if (node.nodeType) translateNode(node);
        if (mutation.type === "characterData" && mutation.target.parentElement) {
          translateNode(mutation.target);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  // When Russian is active, originals are still recorded so a later switch to
  // English translates nodes that already exist.
  function lazy(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (!origin.has(node)) origin.set(node, node.nodeValue);
    }
  }

  window.StudioI18n = {
    get lang() {
      return lang;
    },
    setLang,
    apply,
    watch,
    translateText,
  };
})();
