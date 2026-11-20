(() => {
  const form = document.querySelector("#login-form");
  const error = document.querySelector("#login-error");
  const google = document.querySelector("#login-google");
  const divider = document.querySelector("#login-divider");
  const devNote = document.querySelector("#login-dev-note");
  const unavailable = document.querySelector("#login-unavailable");
  const submit = document.querySelector("#login-submit");

  function destinationAfterLogin() {
    // Always enter through the canonical application root. The React workspace
    // selects Overview as its default view; carrying stale deep links from older
    // releases was sending users to routes that are not real server pages.
    return "/";
  }

  async function initialise() {
    try {
      const [configResponse, meResponse] = await Promise.all([
        fetch("/auth/config", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } }),
        fetch("/auth/me", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } }),
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
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          username: document.querySelector("#login-username").value,
          password: document.querySelector("#login-password").value,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Sign-in failed.");
      if (!payload.authenticated) throw new Error("The sign-in service did not confirm the session.");

      // Confirm that the browser accepted the HttpOnly session cookie before navigating.
      const sessionResponse = await fetch("/auth/me", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const session = await sessionResponse.json().catch(() => ({}));
      if (!sessionResponse.ok || !session.authenticated) {
        throw new Error("Sign-in succeeded, but the browser session was not saved. Refresh the page and try again; check HTTPS forwarding when using Codespaces.");
      }
      window.location.replace(destinationAfterLogin());
    } catch (failure) {
      if (error) error.textContent = failure.message || "Sign-in failed.";
      if (submit) {
        submit.disabled = false;
        submit.innerHTML = 'Sign in to workspace <span>↗</span>';
      }
    }
  });

  initialise();
})();
