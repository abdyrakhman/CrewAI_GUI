(function () {
  const TEXT = {
    ru: {
      title: "CrewAI Studio — вход",
      "brand.sub": "локальный интерфейс",
      "login.title": "Вход",
      "login.hint": "Введите логин и пароль, чтобы открыть рабочее пространство.",
      "login.user": "Логин",
      "login.pass": "Пароль",
      "login.submit": "Войти",
      "login.noAccount": "Нет аккаунта?",
      "login.register": "Зарегистрироваться",
      "register.title": "Регистрация",
      "register.hint": "Создайте аккаунт: логин 3–32 символа, пароль не короче 8.",
      "register.firstTitle": "Первый запуск",
      "register.firstHint": "Аккаунтов ещё нет. Создайте администратора: логин 3–32 символа, пароль не короче 8.",
      "register.user": "Логин",
      "register.pass": "Пароль",
      "register.submit": "Создать аккаунт",
      "register.hasAccount": "Уже есть аккаунт?",
      "register.login": "Войти",
      "error.fill": "Введите логин и пароль",
      "error.short": "Пароль должен быть не короче 8 символов",
      "error.offline": "Сервер недоступен. Обновите страницу.",
      "error.request": "Не удалось выполнить запрос",
      "bootstrap.title": "Первый запуск",
      "bootstrap.hint": "Введите эти данные для входа. Пароль будет показан, пока вы его не смените.",
      "bootstrap.copy": "Скопировать",
      "bootstrap.copied": "Скопировано",
    },
    en: {
      title: "CrewAI Studio — sign in",
      "brand.sub": "local interface",
      "login.title": "Sign in",
      "login.hint": "Enter your login and password to open the workspace.",
      "login.user": "Login",
      "login.pass": "Password",
      "login.submit": "Sign in",
      "login.noAccount": "No account?",
      "login.register": "Register",
      "register.title": "Registration",
      "register.hint": "Create an account: login 3–32 characters, password at least 8.",
      "register.firstTitle": "First launch",
      "register.firstHint": "No accounts yet. Create the administrator: login 3–32 characters, password at least 8.",
      "register.user": "Login",
      "register.pass": "Password",
      "register.submit": "Create account",
      "register.hasAccount": "Already have an account?",
      "register.login": "Sign in",
      "error.fill": "Enter the login and password",
      "error.short": "The password must be at least 8 characters",
      "error.offline": "Server is unavailable. Reload the page.",
      "error.request": "The request failed",
      "bootstrap.title": "First launch",
      "bootstrap.hint": "Use these credentials to sign in. The password is shown until you change it.",
      "bootstrap.copy": "Copy",
      "bootstrap.copied": "Copied",
    },
  };

  const state = { hasUsers: true, mode: "login", lang: "ru" };
  const dict = () => TEXT[state.lang] || TEXT.ru;
  const t = (key) => dict()[key] || TEXT.ru[key] || key;

  const bootstrapBlock = document.getElementById("bootstrap-block");
  const bootstrapUser = document.getElementById("bootstrap-user");
  const bootstrapPass = document.getElementById("bootstrap-pass");
  const bootstrapCopy = document.getElementById("bootstrap-copy");
  let bootstrapCreds = null;

  function applyBootstrap(creds) {
    bootstrapCreds = creds && creds.password ? creds : null;
    if (!bootstrapBlock) return;
    bootstrapBlock.classList.toggle("hidden", !bootstrapCreds);
    if (!bootstrapCreds) return;
    bootstrapUser.textContent = bootstrapCreds.username;
    bootstrapPass.textContent = bootstrapCreds.password;
    if (!loginUser.value) loginUser.value = bootstrapCreds.username;
  }

  if (bootstrapCopy) {
    bootstrapCopy.addEventListener("click", async () => {
      if (!bootstrapCreds) return;
      try {
        await navigator.clipboard.writeText(`${bootstrapCreds.username} / ${bootstrapCreds.password}`);
        bootstrapCopy.textContent = t("bootstrap.copied");
        setTimeout(() => { bootstrapCopy.textContent = t("bootstrap.copy"); }, 1600);
      } catch (error) {
        bootstrapCopy.textContent = t("bootstrap.copy");
      }
    });
  }

  const loginBlock = document.getElementById("login-block");
  const registerBlock = document.getElementById("register-block");
  const errorBox = document.getElementById("auth-error");
  const registerTitle = document.getElementById("register-title");
  const registerHint = document.getElementById("register-hint");
  const loginUser = document.getElementById("login-user");
  const loginPass = document.getElementById("login-pass");
  const regUser = document.getElementById("reg-user");
  const regPass = document.getElementById("reg-pass");

  function applyLanguage(lang) {
    state.lang = lang === "en" ? "en" : "ru";
    document.documentElement.lang = state.lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-ph]").forEach((node) => {
      node.placeholder = t(node.dataset.i18nPh);
    });
    if (bootstrapCopy) bootstrapCopy.textContent = t("bootstrap.copy");
    if (state.mode === "register") {
      registerTitle.textContent = state.hasUsers ? t("register.title") : t("register.firstTitle");
      registerHint.textContent = state.hasUsers ? t("register.hint") : t("register.firstHint");
    }
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  function clearError() {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }

  function setMode(mode) {
    state.mode = mode;
    const register = mode === "register";
    loginBlock.classList.toggle("hidden", register);
    registerBlock.classList.toggle("hidden", !register);
    clearError();
    if (register) {
      registerTitle.textContent = state.hasUsers ? t("register.title") : t("register.firstTitle");
      registerHint.textContent = state.hasUsers ? t("register.hint") : t("register.firstHint");
      document.getElementById("register-switch").classList.toggle("hidden", !state.hasUsers);
      regUser.focus();
    } else {
      loginUser.focus();
    }
  }

  async function post(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = {};
    try { data = await response.json(); } catch (e) { /* empty body */ }
    if (!response.ok) throw new Error(data.error || t("error.request"));
    return data;
  }

  async function submit() {
    clearError();
    const button = state.mode === "login" ? document.getElementById("login-submit") : document.getElementById("register-submit");
    button.disabled = true;
    try {
      if (state.mode === "login") {
        const username = loginUser.value.trim();
        const password = loginPass.value;
        if (!username || !password) throw new Error(t("error.fill"));
        const result = await post("/api/auth/login", { username, password });
        if (result.must_change) {
          location.replace("/change-password.html");
          return;
        }
      } else {
        const username = regUser.value.trim();
        const password = regPass.value;
        if (!username || !password) throw new Error(t("error.fill"));
        if (password.length < 8) throw new Error(t("error.short"));
        await post("/api/auth/register", { username, password });
      }
      location.replace("/");
    } catch (error) {
      showError(error.message);
      button.disabled = false;
    }
  }

  document.getElementById("auth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });
  document.getElementById("to-register").addEventListener("click", () => setMode("register"));
  document.getElementById("to-login").addEventListener("click", () => setMode("login"));

  fetch("/api/auth/state")
    .then((response) => response.json())
    .then((data) => {
      state.hasUsers = Boolean(data.has_users);
      const fallback = (navigator.language || "").toLowerCase().startsWith("ru") ? "ru" : "en";
      applyLanguage(data.language === "en" ? "en" : data.language === "ru" ? "ru" : fallback);
      applyBootstrap(data.bootstrap);
      if (data.user) {
        location.replace("/");
        return;
      }
      setMode(state.hasUsers ? "login" : "register");
    })
    .catch(() => {
      const fallback = (navigator.language || "").toLowerCase().startsWith("ru") ? "ru" : "en";
      applyLanguage(fallback);
      showError(t("error.offline"));
    });
})();
