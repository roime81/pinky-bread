(() => {
  const gate = document.querySelector("#auth-gate");
  if (!gate) return;
  const form = document.querySelector("#dev-login-form");
  const error = document.querySelector("#auth-error");
  const google = document.querySelector("#google-login-button");
  const divider = document.querySelector("#auth-divider");
  const logout = document.querySelector("#auth-logout");

  async function initialiseAuth() {
    try {
      const [configResponse, meResponse] = await Promise.all([fetch("/auth/config"), fetch("/auth/me")]);
      const config = await configResponse.json();
      const me = await meResponse.json();
      if (!config.enabled || me.authenticated) {
        gate.hidden = true;
        if (logout) logout.hidden = !config.enabled;
        return;
      }
      gate.hidden = false;
      if (form) form.hidden = !config.dev_login_enabled;
      if (google) google.hidden = !config.google_enabled;
      if (divider) divider.hidden = !(config.dev_login_enabled && config.google_enabled);
      const note = gate.querySelector(".auth-footnote");
      if (note) note.hidden = !config.dev_login_enabled;
    } catch {
      gate.hidden = true;
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (error) error.textContent = "";
    const button = document.querySelector("#auth-submit");
    if (button) { button.disabled = true; button.textContent = "Signing in…"; }
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.querySelector("#auth-username").value,
          password: document.querySelector("#auth-password").value,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Sign-in failed");
      window.location.reload();
    } catch (failure) {
      if (error) error.textContent = failure.message;
    } finally {
      if (button) { button.disabled = false; button.textContent = "Sign in"; }
    }
  });

  logout?.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST" });
    window.location.reload();
  });

  initialiseAuth();
})();
