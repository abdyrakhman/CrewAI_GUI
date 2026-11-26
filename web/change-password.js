(function () {
  const TEXT = {
    ru: {
      title: "CrewAI Studio — смена пароля",
      "brand.sub": "безопасность аккаунта",
      title2: "Смените пароль",
      hint: "Первый вход с паролем по умолчанию требует нового пароля. Минимум 8 символов.",
      current: "Текущий пароль",
      next: "Новый пароль",
      repeat: "Повторите новый пароль",
      submit: "Сохранить и продолжить",
      "error.current": "Введите текущий пароль",
      "error.short": "Новый пароль должен быть не короче 8 символов",
      "error.match": "Пароли не совпадают",
      "error.same": "Новый пароль должен отличаться от текущего",
      "error.request": "Не удалось сменить пароль",
    },
    en: {
      title: "CrewAI Studio — change password",
      "brand.sub": "account security",
      title2: "Change the password",
      hint: "The first sign-in with the default password requires a new one. At least 8 characters.",
      current: "Current password",
      next: "New password",
      repeat: "Repeat the new password",
      submit: "Save and continue",
      "error.current": "Enter the current password",
      "error.short": "The new password must be at least 8 characters",
      "error.match": "The passwords do not match",
      "error.same": "The new password must differ from the current one",
      "error.request": "Could not change the password",
    },
  };

  let lang = "ru";
  const dict = () => TEXT[lang] || TEXT.ru;
  const t = (key) => dict()[key] || TEXT.ru[key] || key;

  function applyLanguage(code) {
    lang = code === "en" ? "en" : "ru";
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-ph]").forEach((node) => {
      node.placeholder = t(node.dataset.i18nPh);
    });
  }

  const current = document.getElementById("current");
  const next = document.getElementById("next");
  const repeat = document.getElementById("repeat");
  const errorBox = document.getElementById("error");
  const submit = document.getElementById("submit");

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  async function save() {
    errorBox.classList.add("hidden");
    const currentValue = current.value;
    const nextValue = next.value;
    if (!currentValue) return showError(t("error.current"));
    if (nextValue.length < 8) return showError(t("error.short"));
    if (nextValue !== repeat.value) return showError(t("error.match"));
    if (nextValue === currentValue) return showError(t("error.same"));

    submit.disabled = true;
    try {
      const response = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current: currentValue, new: nextValue }),
      });
      let data = {};
      try { data = await response.json(); } catch (e) { /* empty */ }
      if (response.status === 401) {
        location.replace("/login");
        return;
      }
      if (!response.ok) throw new Error(data.error || t("error.request"));
      location.replace("/");
    } catch (error) {
      showError(error.message);
      submit.disabled = false;
    }
  }

  document.getElementById("password-form").addEventListener("submit", (event) => {
    event.preventDefault();
    save();
  });

  fetch("/api/auth/state")
    .then((response) => response.json())
    .then((data) => {
      const fallback = (navigator.language || "").toLowerCase().startsWith("ru") ? "ru" : "en";
      applyLanguage(data.language === "en" ? "en" : data.language === "ru" ? "ru" : fallback);
    })
    .catch(() => {
      const fallback = (navigator.language || "").toLowerCase().startsWith("ru") ? "ru" : "en";
      applyLanguage(fallback);
    });
})();
