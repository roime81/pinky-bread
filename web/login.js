(() => {
  const form = document.querySelector("#login-form");
  const error = document.querySelector("#login-error");
  const google = document.querySelector("#login-google");
  const divider = document.querySelector("#login-divider");
  const devNote = document.querySelector("#login-dev-note");
  const unavailable = document.querySelector("#login-unavailable");
  const submit = document.querySelector("#login-submit");

  async function initialise() {
    try {
      const [configResponse, meResponse] = await Promise.all([
        fetch("/auth/config", { headers: { Accept: "application/json" } }),
        fetch("/auth/me", { headers: { Accept: "application/json" } }),
      ]);
      if (!configResponse.ok || !meResponse.ok) throw new Error("Unable to check sign-in configuration.");
      const config = await configResponse.json();
      const me = await meResponse.json();
      if (!config.enabled || me.authenticated) {
        window.location.replace("/");
        return;
      }
      const showDev = Boolean(config.dev_login_enabled);
      const showGoogle = Boolean(config.google_enabled);
      if (form) form.hidden = !showDev;
      if (google) google.hidden = !showGoogle;
      if (divider) divider.hidden = !(showDev && showGoogle);
      if (devNote) devNote.hidden = !showDev;
      if (unavailable) unavailable.hidden = showDev || showGoogle;
    } catch (failure) {
      if (error) error.textContent = failure.message || "Sign-in service is unavailable.";
      if (submit) submit.disabled = true;
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (error) error.textContent = "";
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Signing in…";
    }
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          username: document.querySelector("#login-username").value,
          password: document.querySelector("#login-password").value,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Sign-in failed.");
      window.location.replace("/");
    } catch (failure) {
      if (error) error.textContent = failure.message;
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.innerHTML = 'Sign in to workspace <span>↗</span>';
      }
    }
  });

  initialise();
})();
