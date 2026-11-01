/**
 * Light / dark theme toggle.
 *
 * Loaded as a blocking classic script in <head> so the stored choice is
 * applied before the first paint (no flash of the wrong theme). Without a
 * stored choice the OS preference (`prefers-color-scheme`) applies.
 */

(() => {
  const STORAGE_KEY = "filnews-theme";
  const root = document.documentElement;
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function stored() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch {
      return null; // Storage blocked (private mode, cookies disabled…).
    }
  }

  function current() {
    return root.dataset.theme || (darkQuery.matches ? "dark" : "light");
  }

  function sync(button) {
    const dark = current() === "dark";
    button.setAttribute("aria-pressed", String(dark));
    button.title = dark ? "Passer en thème clair" : "Passer en thème sombre";
  }

  const initial = stored();
  if (initial) root.dataset.theme = initial;

  document.addEventListener("DOMContentLoaded", () => {
    const button = document.querySelector(".theme-toggle");
    if (!button) return;
    button.hidden = false;
    sync(button);
    darkQuery.addEventListener("change", () => sync(button));
    button.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // The choice just won't survive a reload.
      }
      sync(button);
    });
  });
})();
