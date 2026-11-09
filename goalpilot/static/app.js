"use strict";
const $ = (s) => document.querySelector(s);
const state = {
  projects: [],
  current: null,
  page: "workspace",
  status: { paused: false },
  token: sessionStorage.getItem("goalpilot-token") || "",
};
function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith("on"))
      node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "class") node.className = value;
    else if (key === "checked") node.checked = value;
    else node.setAttribute(key, value);
  }
  if (text !== undefined) node.textContent = text;
  return node;
}
function add(parent, ...children) {
  for (const child of children.flat()) if (child) parent.append(child);
  return parent;
}
function toast(message) {
  $("#notice").textContent = message;
  $("#notice").className = "show";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#notice").className = ""), 6000);
}
async function api(path, method = "GET", body) {
  const response = await fetch("/api/" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: "Bearer " + state.token } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !$("#tokenDialog").open)
      $("#tokenDialog").showModal();
    throw Error(data.error || "Request failed");
  }
  return data;
}
function action(fn) {
  return async (event) => {
    try {
      await fn(event);
    } catch (error) {
      toast(error.message);
    }
  };
}
function button(text, fn, primary = false) {
  return el(
    "button",
    {
      class: primary ? "primary" : "secondary",
      type: "button",
      onclick: action(fn),
    },
    text,
  );
}
function badge(text, warning = false) {
  return el("span", { class: "badge" + (warning ? " warning" : "") }, text);
}
function panel(title) {
  const box = el("section", { class: "panel" });
  box.append(el("h2", {}, title));
  return box;
}
function newGoal(kind = "auto", goal = "") {
  $("#newKind").value = kind;
  $("#newGoal").value = goal;
  $("#newDialog").showModal();
  $("#newGoal").focus();
}
function sidebar() {
  const list = $("#projectList");
  list.replaceChildren();
  for (const p of state.projects)
    list.append(
      el(
        "button",
        {
          class: "project-link" + (state.current === p.id ? " selected" : ""),
          onclick: action(() => select(p.id)),
        },
        "◌  " + p.title,
      ),
    );
  $("#workspaceNav").classList.toggle("active", state.page === "workspace");
  $("#integrationsNav").classList.toggle(
    "active",
    state.page === "integrations",
  );
}
async function load() {
  [state.status, state.projects] = await Promise.all([
    api("status"),
    api("projects"),
  ]);
  $("#pauseBadge").textContent = state.status.paused
    ? "PAUSE active"
    : "Local workspace";
  $("#pauseBadge").className =
    "badge" + (state.status.paused ? " warning" : "");
  render();
}
async function select(id) {
  state.current = id;
  state.page = "workspace";
  await load();
}
function heading(kicker, title, description) {
  return add(
    el("div"),
    el("span", { class: "eyebrow" }, kicker),
    el("h1", {}, title),
    el("p", { class: "lead" }, description),
  );
}
function overview(screen) {
  $("#crumb").textContent = "Overview";
  const hero = el("div", { class: "hero" });
  add(
    hero,
    heading(
      "A LITTLE INTENT. A LOT OF FORWARD.",
      "What should we move forward?",
      "A home for your next idea. Set a goal, work through the plan, and review what gets made.",
    ),
    button("＋  New goal", () => newGoal(), true),
  );
  screen.append(hero);
  const allArtifacts = state.projects.flatMap((p) => p.artifacts);
  const metrics = el("div", { class: "metrics" });
  for (const [name, value, note] of [
    ["Projects", state.projects.length, "in your workspace"],
    [
      "Drafts ready",
      allArtifacts.filter((a) => !a.approval).length,
      "waiting for a look",
    ],
    ["Publishing", "Off", "you stay in control"],
  ])
    add(
      metrics,
      add(
        el("div", { class: "metric" }),
        el("div", { class: "metric-label" }, name),
        add(
          el("div", { class: "metric-value" }, String(value)),
          el("span", {}, note),
        ),
      ),
    );
  screen.append(metrics);
  add(
    screen,
    add(
      el("div", { class: "section-heading" }),
      el("h2", {}, "Choose a starting point"),
      el("small", {}, "Small steps. Reviewable results."),
    ),
  );
  const starters = el("div", { class: "starter-grid" });
  for (const [icon, title, copy, kind, prompt] of [
    [
      "⌕",
      "Understand my website",
      "Inspect public pages and get an evidence-based SEO audit.",
      "seo",
      "Audit my website and prioritise the SEO improvements.",
    ],
    [
      "▷",
      "Shape my next video",
      "Turn source notes into a script, shot list and creative handoff.",
      "video",
      "Create a short video script package for my channel.",
    ],
    [
      "↗",
      "Make a plan",
      "Organise a custom goal into a clear brief and next steps.",
      "custom",
      "Help me plan a project and define a concrete deliverable.",
    ],
  ]) {
    const card = el("button", {
      class: "starter",
      onclick: () => newGoal(kind, prompt),
    });
    add(
      card,
      el("span", { class: "arrow" }, "↗"),
      el("span", { class: "icon" }, icon),
      el("h3", {}, title),
      el("p", {}, copy),
    );
    starters.append(card);
  }
  screen.append(starters);
  add(
    screen,
    add(
      el("div", { class: "principle" }),
      el("span", { class: "icon" }, "✧"),
      add(
        el("div"),
        el("strong", {}, "Useful automation, with room for your judgment."),
        el(
          "p",
          {},
          "Drafts first. Clear sources. Explicit approval. No secret uploads, automatic publishing or promised rankings.",
        ),
      ),
    ),
  );
  if (state.projects.length) {
    add(
      screen,
      add(
        el("div", { class: "section-heading" }),
        el("h2", {}, "Your projects"),
        el("small", {}, "Pick up where you left off"),
      ),
    );
    for (const p of state.projects) {
      const row = el("button", {
        class: "row-card",
        onclick: action(() => select(p.id)),
      });
      add(
        row,
        add(
          el("div"),
          el("strong", {}, p.title),
          el(
            "small",
            {},
            p.kind.toUpperCase() + " · " + p.artifacts.length + " drafts",
          ),
        ),
        el(
          "span",
          { class: "status-text" },
          p.questions.length ? "Needs your input →" : "Open workspace →",
        ),
      );
      screen.append(row);
    }
  }
  add(
    screen,
    el(
      "p",
      { class: "footer-note" },
      "GOALPILOT v0.1  ·  PRIVATE DATA STAYS LOCAL  ·  PUBLIC SOURCE, PERSONAL WORKSPACE",
    ),
  );
}
function integrationCard(item) {
  const row = el("div", { class: "integration" });
  add(
    row,
    add(
      el("div", { class: "integration-head" }),
      el("strong", {}, item.name),
      badge(
        item.status.replaceAll("_", " "),
        item.status === "needs_configuration",
      ),
    ),
    el("p", {}, item.purpose),
    el("small", {}, item.setup || "Available without additional credentials."),
  );
  return row;
}
function projectView(screen, p) {
  $("#crumb").textContent =
    p.kind === "seo"
      ? "SEO workspace"
      : p.kind === "video"
        ? "Video workspace"
        : "Project brief";
  const hero = el("div", { class: "hero" });
  add(
    hero,
    heading(
      p.kind.toUpperCase() + " WORKFLOW",
      p.title,
      "Clarify the details, run a bounded task, then review the output.",
    ),
    button("← All projects", () => {
      state.current = null;
      render();
    }),
  );
  screen.append(hero);
  const grid = el("div", { class: "project-grid" }),
    left = el("div"),
    right = el("div");
  add(grid, left, right);
  screen.append(grid);
  const intake = panel("01  ·  Tell GoalPilot what matters");
  if (p.questions.length)
    add(
      intake,
      el(
        "p",
        { class: "workflow-note" },
        p.questions.length +
          " required details are missing. You can save partial answers.",
      ),
    );
  const fields =
    p.kind === "seo"
      ? [
          ["website", "Website URL", "https://example.com/"],
          ["audience", "Audience and market", "Who are you trying to reach?"],
        ]
      : p.kind === "video"
        ? [
            ["topic", "Topic or niche", "What should the video explain?"],
            ["audience", "Audience and market", "Who should watch this?"],
            ["language", "Language", "English"],
            [
              "facts",
              "Supported facts and source notes",
              "Paste facts you can support. Include source URLs as references; v0.1 does not fetch them.",
            ],
            [
              "reference",
              "Reference transcript or shot notes (optional)",
              "Describe the structure and pacing you want to learn from. v0.1 does not watch video files.",
            ],
          ]
        : [
            [
              "outcome",
              "Concrete deliverable",
              "What would a successful result look like?",
            ],
          ];
  const controls = {};
  for (const [key, label, placeholder] of fields) {
    const input = el(
      ["facts", "reference", "outcome"].includes(key) ? "textarea" : "input",
      { placeholder, rows: 4, maxlength: 12000 },
    );
    input.value = p.inputs[key] || "";
    controls[key] = input;
    add(intake, add(el("label", {}, label), input));
  }
  if (p.kind === "seo") {
    const speed = el("select");
    add(
      speed,
      el("option", { value: "no" }, "No — local crawler only"),
      el(
        "option",
        { value: "yes" },
        "Yes — send the website URL to Google PageSpeed",
      ),
    );
    speed.value = p.inputs.pagespeed || "no";
    controls.pagespeed = speed;
    add(
      intake,
      add(el("label", {}, "Optional page-speed measurement"), speed),
      el(
        "p",
        { class: "workflow-note" },
        "Requires PAGESPEED_API_KEY on the server. Two requests: mobile and desktop. This choice also applies to any draft schedule you approve.",
      ),
    );
  }
  const plan = el("textarea", { rows: 5, maxlength: 3600 });
  plan.value = p.plan.join("\n");
  add(intake, add(el("label", {}, "Task plan — one step per line"), plan));
  add(
    intake,
    add(
      el("div", { class: "actions" }),
      button(
        "Save details & plan",
        async () => {
          const inputs = {};
          for (const [key, input] of Object.entries(controls))
            inputs[key] = input.value;
          await api("projects/" + p.id, "PATCH", {
            inputs,
            plan: plan.value.split("\n").filter((s) => s.trim()),
          });
          toast("Details saved. New inputs apply to future runs.");
          await load();
        },
        true,
      ),
    ),
  );
  left.append(intake);
  const execute = panel("02  ·  Make a reviewable draft");
  add(
    execute,
    el(
      "p",
      { class: "workflow-note" },
      p.kind === "video"
        ? "Live generation sends your supplied notes to the configured model provider. Research, video analysis and rendering are not implemented yet."
        : "Live runs inspect permitted public pages only. They include bounded sitemap/link/canonical/schema checks and optional PageSpeed. They do not change websites, measure rankings or run analytics.",
    ),
  );
  const consent = el("input", { type: "checkbox" });
  add(
    execute,
    add(
      el("label", { class: "check" }),
      consent,
      el(
        "span",
        {},
        "For a live video run, I approve sending these saved notes to " +
          (state.status.provider_host || "the configured model provider") +
          " and accept the provider’s API charges. Maximum 1,600 output tokens; one request.",
      ),
    ),
  );
  const run = async (demo) => {
    await api("projects/" + p.id + "/runs", "POST", {
      demo,
      allow_model: !demo && consent.checked,
    });
    toast(
      demo ? "Offline demo queued. No network requests." : "Live task queued.",
    );
    await load();
  };
  const actions = el("div", { class: "actions" });
  const active = p.jobs.some((j) => ["queued", "running"].includes(j.status));
  for (const [text, demo] of [
    ["Try offline demo", true],
    ["Run live task", false],
  ]) {
    const b = button(text, () => run(demo), !demo);
    b.disabled = !!p.questions.length || active || state.status.paused;
    actions.append(b);
  }
  add(execute, actions);
  if (active)
    add(
      execute,
      el(
        "p",
        { class: "status-text" },
        "◌  Task is queued or running. This page updates when the result is ready.",
      ),
    );
  for (const job of p.jobs.slice(0, 3))
    add(
      execute,
      el(
        "p",
        { class: job.error ? "error" : "workflow-note" },
        (job.demo ? "Demo" : "Live") +
          " · " +
          job.status +
          (job.error ? " — " + job.error : ""),
      ),
    );
  left.append(execute);
  const outputs = panel("03  ·  Your drafts");
  if (!p.artifacts.length)
    add(
      outputs,
      el(
        "div",
        { class: "empty" },
        "Your first draft will appear here. You can inspect and export it before connecting any publishing accounts.",
      ),
    );
  for (const artifact of p.artifacts) {
    const wrap = el("article", { class: "artifact" });
    add(
      wrap,
      badge(
        artifact.demo
          ? "Synthetic demo"
          : artifact.approval
            ? "Reviewed · export only"
            : "Needs your review",
        !artifact.demo && !artifact.approval,
      ),
      el("pre", {}, artifact.text),
    );
    const acts = el("div", { class: "actions" });
    add(
      acts,
      button("Download Markdown", async () => {
        const blob = new Blob([artifact.text], { type: "text/markdown" });
        const a = el("a", {
          href: URL.createObjectURL(blob),
          download: "goalpilot-" + artifact.id.slice(0, 8) + ".md",
        });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 500);
      }),
    );
    if (artifact.report)
      add(
        acts,
        button("Download audit JSON", async () => {
          const data = await api("artifacts/" + artifact.id + "/report");
          const a = el("a", {
            href: URL.createObjectURL(
              new Blob([JSON.stringify(data, null, 2)], {
                type: "application/json",
              }),
            ),
            download: "goalpilot-audit-" + artifact.id.slice(0, 8) + ".json",
          });
          document.body.append(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 500);
        }),
      );
    if (!artifact.demo && !artifact.approval)
      add(
        acts,
        button(
          "Mark reviewed",
          async () => {
            await api("artifacts/" + artifact.id + "/approve", "POST", {
              sha256: artifact.sha256,
            });
            toast("Marked reviewed. Nothing was published.");
            await load();
          },
          true,
        ),
      );
    add(wrap, acts);
    outputs.append(wrap);
  }
  right.append(outputs);
  const connections = panel("Integrations for this goal");
  p.integrations.forEach((item) => connections.append(integrationCard(item)));
  right.append(connections);
  const schedule = panel("Repeat a bounded task");
  add(
    schedule,
    el(
      "p",
      { class: "workflow-note" },
      "Generate drafts only. Stops after seven runs or seven days, and invalidates when project inputs or plan change. Paid model schedules are disabled in v0.1. The local server must stay running.",
    ),
  );
  const interval = el("select");
  for (const [v, t] of [
    [24, "Every day"],
    [1, "Every hour"],
    [168, "Every week"],
  ])
    interval.append(el("option", { value: v }, t));
  const mode = el("select");
  add(mode, el("option", { value: "demo" }, "Offline demo"));
  if (p.kind === "seo")
    add(mode, el("option", { value: "live" }, "Live read-only audit"));
  const approved = el("input", { type: "checkbox" });
  add(
    schedule,
    add(el("label", {}, "Frequency"), interval),
    add(el("label", {}, "Mode"), mode),
    add(
      el("label", { class: "check" }),
      approved,
      el(
        "span",
        {},
        "I approve these saved inputs and this schedule for draft generation only.",
      ),
    ),
  );
  const scheduleButton = button("Enable schedule", async () => {
    if (!approved.checked) throw Error("Approve the schedule first");
    await api("projects/" + p.id + "/schedules", "POST", {
      APPROVED: true,
      interval_hours: Number(interval.value),
      demo: mode.value === "demo",
    });
    toast("Draft schedule enabled. No publishing.");
    await load();
  });
  scheduleButton.disabled =
    !!p.questions.length || p.kind === "custom" || state.status.paused;
  add(schedule, add(el("div", { class: "actions" }), scheduleButton));
  for (const s of p.schedules.filter((s) => s.enabled)) {
    add(
      schedule,
      el(
        "p",
        {},
        "Next: " +
          new Date(s.next_run * 1000).toLocaleString() +
          " · " +
          s.runs +
          "/7 runs",
      ),
      button("Disable schedule", async () => {
        await api("schedules/" + s.id + "/disable", "POST", {});
        await load();
      }),
    );
  }
  right.append(schedule);
  const activity = panel("Activity trail");
  if (!p.events.length) add(activity, el("p", {}, "No activity yet."));
  for (const event of p.events.slice(0, 12))
    add(
      activity,
      add(
        el("div", { class: "activity" }),
        add(
          el("div"),
          el("div", {}, event.action),
          el("small", {}, event.status),
        ),
        el("small", {}, new Date(event.at * 1000).toLocaleTimeString()),
      ),
    );
  left.append(activity);
}
function integrationsView(screen) {
  $("#crumb").textContent = "Integrations";
  screen.append(
    heading(
      "CONNECT ONLY WHAT YOU NEED",
      "Your tools. Your permissions.",
      "Credentials stay in your server environment. The public repository contains source code only.",
    ),
  );
  const box = panel("Available in v0.1");
  box.append(
    integrationCard({
      name: "Public HTTPS crawler",
      status: "available",
      purpose:
        "Nested-sitemap discovery, links, canonicals and schema checks; no crawler credentials needed",
      setup:
        "Respects robots.txt, validates public addresses, blocks off-site redirects and limits HTML audits to ten pages, sitemap fetches to six and link checks to forty.",
    }),
  );
  box.append(
    integrationCard({
      name: "OpenAI-compatible model",
      status: state.status.model_configured
        ? "configured"
        : "needs_configuration",
      purpose: "Video drafts from your supplied notes",
      setup: state.status.model_configured
        ? "Destination: " +
          state.status.provider_host +
          " · model: " +
          state.status.model
        : "Set LLM_BASE_URL, LLM_MODEL, LLM_API_KEY in the server environment. No provider calls occur until a live video run is explicitly approved.",
    }),
  );
  box.append(
    integrationCard({
      name: "Google PageSpeed Insights",
      status: state.status.pagespeed_configured
        ? "configured"
        : "needs_configuration",
      purpose: "Optional mobile and desktop lab measurements for SEO projects",
      setup:
        "Set PAGESPEED_API_KEY on the server, then opt in in each project's saved details. Sends the public URL to Google; demo runs make no requests.",
    }),
  );
  screen.append(box);
  const later = panel("Not connected or implemented yet");
  for (const name of [
    "GSC / GA4 analytics",
    "Web search and keyword research",
    "Reference-video transcription and visual analysis",
    "Video rendering and TTS",
    "YouTube / Instagram publishing",
    "GitHub PR creation",
  ])
    later.append(
      integrationCard({
        name,
        status: "planned",
        purpose: "Future workflow adapter",
        setup:
          "No credentials needed now. GoalPilot will ask for the required scope when this adapter is available.",
      }),
    );
  screen.append(later);
}
function render() {
  sidebar();
  const screen = $("#screen");
  screen.replaceChildren();
  if (state.page === "integrations") integrationsView(screen);
  else {
    const project = state.projects.find((p) => p.id === state.current);
    if (project) projectView(screen, project);
    else overview(screen);
  }
}
$("#workspaceNav").onclick = () => {
  state.page = "workspace";
  state.current = null;
  render();
};
$("#integrationsNav").onclick = () => {
  state.page = "integrations";
  render();
};
$("#newSmall").onclick = () => newGoal();
$("#closeDialog").onclick = () => $("#newDialog").close();
$("#authButton").onclick = () => $("#tokenDialog").showModal();
$("#closeToken").onclick = () => $("#tokenDialog").close();
$("#newForm").onsubmit = action(async (event) => {
  event.preventDefault();
  const p = await api("projects", "POST", {
    goal: $("#newGoal").value,
    kind: $("#newKind").value,
  });
  $("#newDialog").close();
  state.current = p.id;
  state.page = "workspace";
  await load();
});
$("#tokenForm").onsubmit = action(async (event) => {
  event.preventDefault();
  state.token = $("#token").value;
  sessionStorage.setItem("goalpilot-token", state.token);
  $("#token").value = "";
  $("#tokenDialog").close();
  await load();
});
load().catch((error) => {
  toast(error.message);
  if (!$("#screen").children.length)
    $("#screen").append(
      heading(
        "LOCAL WORKSPACE",
        "Connect to your GoalPilot server",
        "Start python -m goalpilot, or enter the optional local access token.",
      ),
    );
});
setInterval(async () => {
  if (
    !state.projects.some((p) =>
      p.jobs.some((j) => ["queued", "running"].includes(j.status)),
    )
  )
    return;
  if (
    document.activeElement?.matches("input,textarea,select") ||
    $("dialog[open]")
  )
    return;
  try {
    await load();
  } catch {}
}, 3000);
