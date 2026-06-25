const tabs = document.querySelectorAll("[data-auth-tab]");
tabs.forEach(btn => btn.addEventListener("click", () => {
  tabs.forEach(item => item.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("loginForm").classList.toggle("hidden", btn.dataset.authTab !== "login");
  document.getElementById("registerForm").classList.toggle("hidden", btn.dataset.authTab !== "register");
  refreshVisibleCaptcha();
}));

function refreshCaptcha(img) {
  img.src = `/api/auth/captcha?_=${Date.now()}_${Math.random()}`;
}

function isVisible(el) {
  return !el.closest(".hidden");
}

function refreshVisibleCaptcha() {
  document.querySelectorAll("[data-captcha]").forEach(img => {
    if (isVisible(img)) refreshCaptcha(img);
  });
}

document.querySelectorAll("[data-captcha]").forEach(img => img.addEventListener("click", () => refreshCaptcha(img)));
refreshVisibleCaptcha();

async function postJson(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "请求失败");
  return data;
}

function show(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 1800);
}

document.getElementById("sendCode").addEventListener("click", async () => {
  const form = document.getElementById("registerForm");
  try {
    const data = Object.fromEntries(new FormData(form));
    data.purpose = "register";
    await postJson("/api/auth/send-code", data);
    show("邮箱验证码已发送");
    refreshVisibleCaptcha();
  } catch (err) {
    show(err.message);
    refreshVisibleCaptcha();
  }
});

document.getElementById("loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const ret = await postJson("/api/auth/login", Object.fromEntries(new FormData(event.target)));
    location.href = ret.user.role === "admin" ? "/admin" : "/app";
  } catch (err) {
    show(err.message);
    refreshVisibleCaptcha();
  }
});

document.getElementById("registerForm").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await postJson("/api/auth/register", Object.fromEntries(new FormData(event.target)));
    location.href = "/app";
  } catch (err) {
    show(err.message);
    refreshVisibleCaptcha();
  }
});

document.getElementById("forgotBtn").addEventListener("click", () => {
  document.getElementById("forgotModal").classList.remove("hidden");
  refreshVisibleCaptcha();
});

document.getElementById("closeForgot").addEventListener("click", () => {
  document.getElementById("forgotModal").classList.add("hidden");
  refreshVisibleCaptcha();
});

document.getElementById("sendResetCode").addEventListener("click", async () => {
  const form = document.getElementById("forgotForm");
  try {
    const data = Object.fromEntries(new FormData(form));
    data.purpose = "reset";
    await postJson("/api/auth/send-code", data);
    show("重置验证码已发送");
    refreshVisibleCaptcha();
  } catch (err) {
    show(err.message);
    refreshVisibleCaptcha();
  }
});

document.getElementById("forgotForm").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await postJson("/api/auth/reset-password", Object.fromEntries(new FormData(event.target)));
    document.getElementById("forgotModal").classList.add("hidden");
    show("密码已重置，请重新登录");
  } catch (err) {
    show(err.message);
    refreshVisibleCaptcha();
  }
});
