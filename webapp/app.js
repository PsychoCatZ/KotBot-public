(() => {
  "use strict";

  const loginScreen = document.getElementById("login-screen");
  const chatScreen = document.getElementById("chat-screen");
  const loginForm = document.getElementById("login-form");
  const loginPassword = document.getElementById("login-password");
  const loginError = document.getElementById("login-error");

  const messagesEl = document.getElementById("messages");
  const chatForm = document.getElementById("chat-form");
  const textInput = document.getElementById("text-input");
  const sendBtn = document.getElementById("send-btn");
  const clearBtn = document.getElementById("clear-btn");
  const imageInput = document.getElementById("image-input");
  const imagePreviewWrap = document.getElementById("image-preview-wrap");
  const imagePreview = document.getElementById("image-preview");
  const imageRemove = document.getElementById("image-remove");
  const themeToggle = document.getElementById("theme-toggle");
  const homeScreenBtn = document.getElementById("home-screen-btn");

  let selectedImage = null;

  function getTelegramWebApp() {
    return window.Telegram && window.Telegram.WebApp;
  }

  function homeScreenApiAvailable() {
    const tg = getTelegramWebApp();

    return !!(
      tg &&
      typeof tg.isVersionAtLeast === "function" &&
      tg.isVersionAtLeast("8.0") &&
      typeof tg.addToHomeScreen === "function" &&
      typeof tg.checkHomeScreenStatus === "function"
    );
  }

  function refreshHomeScreenStatus() {
    if (!homeScreenApiAvailable()) {
      homeScreenBtn.classList.add("hidden");
      return;
    }

    homeScreenBtn.classList.remove("hidden");

    getTelegramWebApp().checkHomeScreenStatus((status) => {
      if (status === "unsupported") {
        homeScreenBtn.disabled = true;
        homeScreenBtn.title = "Этот клиент Telegram не поддерживает создание ярлыка";
      } else if (status === "added") {
        homeScreenBtn.disabled = true;
        homeScreenBtn.title = "Ярлык уже на главном экране";
      } else {
        homeScreenBtn.disabled = false;
        homeScreenBtn.title = "Добавить ярлык на главный экран";
      }
    });
  }

  function initHomeScreenButton() {
    if (!homeScreenApiAvailable()) {
      return;
    }

    const tg = getTelegramWebApp();

    refreshHomeScreenStatus();

    tg.onEvent("homeScreenAdded", () => {
      homeScreenBtn.disabled = true;
      homeScreenBtn.title = "Ярлык добавлен";
    });

    homeScreenBtn.addEventListener("click", () => {
      if (homeScreenBtn.disabled) {
        return;
      }

      tg.addToHomeScreen();
      // Часть устройств не сообщает Telegram результат установки —
      // homeScreenAdded в этом случае просто не придёт, это не ошибка.
      homeScreenBtn.title = "Подтверди в диалоге Telegram — некоторые устройства не сообщают результат";
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        refreshHomeScreenStatus();
      }
    });
  }

  function showScreen(screen) {
    loginScreen.classList.toggle("hidden", screen !== "login");
    chatScreen.classList.toggle("hidden", screen !== "chat");
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeToggle.textContent = theme === "light" ? "🌙" : "☀️";
  }

  function initTheme() {
    let theme = "dark";

    try {
      theme = localStorage.getItem("kater-theme") || "dark";
    } catch (e) {
      // приватный режим / заблокировано — остаёмся на тёмной теме
    }

    applyTheme(theme);
  }

  themeToggle.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    applyTheme(next);

    try {
      localStorage.setItem("kater-theme", next);
    } catch (e) {
      // ок, просто не запомнится между визитами
    }
  });

  initTheme();

  function setSelectedImage(file) {
    selectedImage = file;
    imagePreview.src = URL.createObjectURL(file);
    imagePreviewWrap.classList.remove("hidden");
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addBubble(role, text, imageUrl, extraClass) {
    const div = document.createElement("div");
    div.className = `msg ${role}${extraClass ? " " + extraClass : ""}`;
    div.textContent = text || "";

    if (imageUrl) {
      const img = document.createElement("img");
      img.src = imageUrl;
      // Картинка догружается уже после того, как мы прокрутили вниз по
      // тексту — без этого контейнер подрастает и вид "застревает" выше
      // настоящего конца истории, особенно при загрузке сразу 20 сообщений
      // с вложениями.
      img.addEventListener("load", scrollToBottom);
      div.appendChild(img);
    }

    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  // Теги [Отправитель: ...] добавляет бэкенд — в UI их не показываем.
  function stripSenderTag(text) {
    return text.replace(/^\[Отправитель:[^\]]*\]\n?/, "");
  }

  async function loadHistory() {
    const res = await fetch("/api/history");

    if (res.status === 401) {
      showScreen("login");
      return false;
    }

    const data = await res.json();
    messagesEl.innerHTML = "";

    for (const m of data.messages) {
      if (m.role === "user") {
        addBubble("user", stripSenderTag(m.content), m.image_data_url);
      } else if (m.role === "assistant") {
        addBubble("bot", m.content);
      }
    }

    return true;
  }

  async function tryTelegramAutoLogin() {
    const tg = window.Telegram && window.Telegram.WebApp;

    if (!tg || !tg.initData) {
      return false;
    }

    try {
      const res = await fetch("/api/telegram-auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData: tg.initData })
      });

      return res.ok;
    } catch (e) {
      return false;
    }
  }

  async function login(password) {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password })
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Не удалось войти");
    }
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.textContent = "";

    try {
      await login(loginPassword.value);
      loginPassword.value = "";
      showScreen("chat");
      await loadHistory();
    } catch (err) {
      loginError.textContent = err.message;
    }
  });

  clearBtn.addEventListener("click", async () => {
    if (!confirm("Очистить память Kater в этом чате?")) {
      return;
    }

    await fetch("/api/clear", { method: "POST" });
    messagesEl.innerHTML = "";
  });

  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];

    if (!file) {
      selectedImage = null;
      imagePreviewWrap.classList.add("hidden");
      return;
    }

    setSelectedImage(file);
  });

  imageRemove.addEventListener("click", () => {
    selectedImage = null;
    imageInput.value = "";
    imagePreviewWrap.classList.add("hidden");
  });

  // Вставка картинки из буфера обмена (Ctrl+V) — работает в любом месте чата,
  // не только в текстовом поле.
  document.addEventListener("paste", (e) => {
    if (chatScreen.classList.contains("hidden")) {
      return;
    }

    const items = e.clipboardData && e.clipboardData.items;

    if (!items) {
      return;
    }

    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();

        if (file) {
          e.preventDefault();
          setSelectedImage(file);
        }

        break;
      }
    }
  });

  textInput.addEventListener("input", () => {
    textInput.style.height = "auto";
    textInput.style.height = Math.min(textInput.scrollHeight, 120) + "px";
  });

  textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const text = textInput.value.trim();

    if (!text && !selectedImage) {
      return;
    }

    const imagePreviewUrl = selectedImage ? imagePreview.src : null;
    addBubble("user", text, imagePreviewUrl);

    const pending = addBubble("bot", "печатает...", null, "pending");

    const formData = new FormData();
    formData.append("text", text);
    if (selectedImage) {
      formData.append("image", selectedImage);
    }

    textInput.value = "";
    textInput.style.height = "auto";
    imageInput.value = "";
    selectedImage = null;
    imagePreviewWrap.classList.add("hidden");
    sendBtn.disabled = true;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        body: formData
      });

      if (res.status === 401) {
        showScreen("login");
        pending.remove();
        return;
      }

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Ошибка");
      }

      pending.remove();
      addBubble("bot", data.answer);
    } catch (err) {
      pending.classList.remove("pending");
      pending.classList.add("error");
      pending.textContent = "Связь с Kater потеряна: " + err.message;
    } finally {
      sendBtn.disabled = false;
    }
  });

  async function init() {
    const tg = window.Telegram && window.Telegram.WebApp;

    if (tg) {
      tg.ready();
      tg.expand();
    }

    initHomeScreenButton();

    let ok = await loadHistory();

    if (!ok && (await tryTelegramAutoLogin())) {
      ok = await loadHistory();
    }

    if (ok) {
      showScreen("chat");
    }
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  init();
})();
