(() => {
  const logout = document.querySelector("#auth-logout");
  logout?.addEventListener("click", async () => {
    logout.disabled = true;
    try {
      await fetch("/auth/logout", { method: "POST" });
    } finally {
      window.location.replace("/login");
    }
  });
})();
