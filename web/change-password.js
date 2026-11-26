(function () {
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
    if (!currentValue) return showError("Введите текущий пароль");
    if (nextValue.length < 8) return showError("Новый пароль должен быть не короче 8 символов");
    if (nextValue !== repeat.value) return showError("Пароли не совпадают");
    if (nextValue === currentValue) return showError("Новый пароль должен отличаться от текущего");

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
      if (!response.ok) throw new Error(data.error || "Не удалось сменить пароль");
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
})();
