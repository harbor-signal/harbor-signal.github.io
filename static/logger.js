(function () {
  const form = document.querySelector("#observation-form");
  const output = document.querySelector("#logger-output");
  const exportButton = document.querySelector("#export-observations");
  const publishButton = document.querySelector("#publish-github");
  const tokenInput = document.querySelector("#github-token");
  const branchInput = document.querySelector("#github-branch");
  const storageKey = "harbor-signal-observation-drafts";
  const repoContentsUrl =
    "https://api.github.com/repos/harbor-signal/harbor-signal.github.io/contents/content/observations/";

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

  function slugify(value) {
    return String(value || "harbor-observation")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 80);
  }

  function yamlList(values) {
    return `[${values.map((value) => JSON.stringify(value)).join(", ")}]`;
  }

  function markdownForObservation(draft) {
    const timestamp = draft.timestamp || new Date().toISOString();
    const date = timestamp.slice(0, 10);
    const title = draft.title || `${draft.vessel || "Harbor"} observation`;
    const tags = Array.isArray(draft.tags) ? draft.tags : [];
    const vessel = draft.vessel ? [draft.vessel] : [];
    return [
      "---",
      `title: ${JSON.stringify(title)}`,
      `date: ${date}`,
      `time: ${JSON.stringify(timestamp.slice(11, 16))}`,
      `location: ${JSON.stringify(draft.location || "")}`,
      `weather: ${JSON.stringify(draft.weather || "")}`,
      `vessels_referenced: ${yamlList(vessel)}`,
      `tags: ${yamlList(tags)}`,
      "observation_type: field-log",
      "---",
      "",
      draft.note || "",
      "",
    ].join("\n");
  }

  function toBase64(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary);
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

  if (publishButton) {
    publishButton.addEventListener("click", async function () {
      const latest = drafts().at(-1);
      if (!latest) {
        render("No local draft to publish yet.");
        return;
      }
      const token = tokenInput && tokenInput.value;
      if (!token) {
        render("Add a GitHub token with contents write access before publishing.");
        return;
      }
      const branch = (branchInput && branchInput.value) || "main";
      const markdown = markdownForObservation(latest);
      const date = (latest.timestamp || new Date().toISOString()).slice(0, 10);
      const slug = slugify(`${latest.timestamp || new Date().toISOString()}-${latest.vessel || latest.location || "harbor-observation"}`);
      const response = await fetch(`${repoContentsUrl}${slug}.md`, {
        method: "PUT",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({
          branch,
          message: `Add observation: ${latest.vessel || latest.location || date}`,
          content: toBase64(markdown),
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        render(`GitHub publish failed: ${response.status} ${text}`);
        return;
      }
      render(`Published content/observations/${slug}.md to ${branch}.`);
    });
  }

  render();
})();
