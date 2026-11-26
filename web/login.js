(function () {
  const state = { hasUsers: true, mode: "login" };
  const loginBlock = document.getElementById("login-block");
  const registerBlock = document.getElementById("register-block");
  const errorBox = document.getElementById("auth-error");
  const registerTitle = document.getElementById("register-title");
  const registerHint = document.getElementById("register-hint");
  const loginUser = document.getElementById("login-user");
  const loginPass = document.getElementById("login-pass");
  const regUser = document.getElementById("reg-user");
  const regPass = document.getElementById("reg-pass");

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
      registerTitle.textContent = state.hasUsers ? "Регистрация" : "Первый запуск";
      registerHint.textContent = state.hasUsers
        ? "Создайте аккаунт: логин 3–32 символа, пароль не короче 8."
        : "Аккаунтов ещё нет. Создайте администратора: логин 3–32 символа, пароль не короче 8.";
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
    if (!response.ok) throw new Error(data.error || "Не удалось выполнить запрос");
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
        if (!username || !password) throw new Error("Введите логин и пароль");
        const result = await post("/api/auth/login", { username, password });
        if (result.must_change) {
          location.replace("/change-password.html");
          return;
        }
      } else {
        const username = regUser.value.trim();
        const password = regPass.value;
        if (!username || !password) throw new Error("Введите логин и пароль");
        if (password.length < 8) throw new Error("Пароль должен быть не короче 8 символов");
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
      if (data.user) {
        location.replace("/");
        return;
      }
      setMode(state.hasUsers ? "login" : "register");
    })
    .catch(() => showError("Сервер недоступен. Обновите страницу."));
})();
