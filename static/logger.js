(function () {
  const form = document.querySelector("#observation-form");
  const output = document.querySelector("#logger-output");
  const exportButton = document.querySelector("#export-observations");
  const storageKey = "harbor-signal-observation-drafts";

  function drafts() {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "[]");
    } catch (_error) {
      return [];
    }
  }

  function render(message) {
    if (!output) return;
    const count = drafts().length;
    output.textContent = message || `${count} draft${count === 1 ? "" : "s"} saved locally.`;
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      const next = drafts().concat({
        ...data,
        tags: String(data.tags || "")
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        saved_at: new Date().toISOString(),
      });
      localStorage.setItem(storageKey, JSON.stringify(next, null, 2));
      form.reset();
      render("Draft saved locally. Export JSON when ready to publish.");
    });
  }

  if (exportButton) {
    exportButton.addEventListener("click", function () {
      render(JSON.stringify(drafts(), null, 2));
    });
  }

  render();
})();
