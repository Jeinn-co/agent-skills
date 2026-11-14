const button = document.getElementById("refresh");
const allButton = document.getElementById("all");
const picker = document.getElementById("theme");
addEventListener("pointerdown", () => document.documentElement.classList.add("mouse"), true);
addEventListener("keydown", () => document.documentElement.classList.remove("mouse"), true);
const THEMES = ["auto", "light", "dark"];
const t = reportT;
const langButton = document.getElementById("lang");
let refreshState = "refresh", updatedAt = __UPDATED__;
const applyLang = doc => {
  const lang = document.documentElement.dataset.lang;
  doc.documentElement.dataset.lang = lang;
  doc.documentElement.lang = lang === "zh" ? "zh-Hant" : "en";
};
const refreshLabel = () => { button.querySelector("span").textContent = refreshState === "busy" ? t("refreshing") : refreshState === "retry" ? t("retry") : t("refresh"); };
const labels = () => {
  applyLang(document);
  langButton.innerHTML = __GLOBE__ + "<span>" + t("language_target") + "</span>";
  langButton.setAttribute("aria-label", t("language_aria"));
  picker.setAttribute("aria-label", t("theme"));
  [picker.options[0].textContent, picker.options[1].textContent, picker.options[2].textContent] =
    [t("auto"), t("light"), t("dark")];
  refreshLabel();
};
window.addEventListener("reportlanguagechange", () => {
  labels(); stamp(updatedAt); syncButtons();
  document.querySelectorAll(".acv-err").forEach(el => { el.textContent = t("update_failed") + failures[el.dataset.tool]; });
});
labels();
const SKELETON = __SKELETON__;
let theme = "auto";  // Auto follows the OS; the choice is kept per browser
try { theme = localStorage.getItem("ai-cli-version-theme") || "auto"; } catch (e) {}
// The value is spliced into the report's HTML, so only a known name may pass.
if (!THEMES.includes(theme)) theme = "auto";
picker.value = theme;
const applyTheme = doc => {
  if (theme === "auto") delete doc.documentElement.dataset.theme;
  else doc.documentElement.dataset.theme = theme;
};
// Puts a freshly fetched page's content under this header, keeping the header itself.
const show = html => {
  const fresh = new DOMParser().parseFromString(html, "text/html").querySelector("main");
  fresh?.querySelector(".title-row")?.remove();
  const main = document.querySelector("main");
  [...main.children].filter(el => !el.matches(".title-row")).forEach(el => el.remove());
  if (fresh) main.append(...fresh.children);
  decorate(document);
  return Promise.resolve(document);
};
applyTheme(document);
picker.onchange = () => {
  theme = THEMES.includes(picker.value) ? picker.value : "auto";
  try { localStorage.setItem("ai-cli-version-theme", theme); } catch (e) {}
  applyTheme(document);
};
const stamp = ms => {  // when the shown report was written, in local time
  updatedAt = ms;
  const d = new Date(ms), p = n => String(n).padStart(2, "0");
  const line = document.querySelector("main > p.top");
  if (line) line.textContent = (ms ? t("updated") + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " +
    p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()) + " · " : "") + "ai-cli-version __VERSION__";
};
stamp(__UPDATED__);
// Last update error per tool, shown on its row again after the re-check.
const failures = {};
// shortcut: queued clicks live in this tab; use a server queue if they must survive reload.
const queue = [], pending = new Set();
let busy = false, updating = false, current = "";
// While updates run, the same button cancels the ones not started yet; the running one
// always finishes, since stopping an installer halfway could leave a broken install.
const syncButtons = () => {
  button.disabled = busy || updating;
  const rows = [...document.querySelectorAll("tr[data-tool]")];
  allButton.hidden = rows.length < 2 && !queue.length;
  allButton.disabled = busy || (updating && !queue.length);
  allButton.textContent = !updating ? t("update_all", {count: rows.length}) :
    queue.length ? t("cancel_queued", {count: queue.length}) : t("finishing");
  // While updates run, only a queued row's button works, and it cancels just that tool;
  // the running row and rows outside the queue stay disabled until the queue ends.
  document.querySelectorAll("button.acv-up").forEach(b => {
    const tool = b.dataset.tool, queued = pending.has(tool) && tool !== current;
    b.disabled = busy || (updating && !queued);
    if (queued) b.textContent = t("queued_cancel");
    else if (tool === current) b.textContent = t("updating");
    else b.textContent = failures[tool] ? t("retry") : t("update");
  });
};
const setBusy = on => { busy = on; syncButtons(); };
const ROW_CSS = ".acv-up{margin-left:8px;padding:2px 12px;border:0;border-radius:4px;" +
  "font:inherit;font-size:13px;font-weight:500;background:var(--accent);color:var(--card);" +
  "cursor:pointer}.acv-up:disabled{opacity:.6;cursor:default}" +
  ".acv-err{color:var(--bad);font-size:13px;margin-top:4px}" +
  ".acv-run{color:var(--muted);font-size:13px;margin-top:4px;max-width:420px;" +
  "overflow:hidden;text-overflow:ellipsis;white-space:nowrap}";
// Adds an Update button to each row with an update that has none yet, plus Update all
// when there are two or more. Only the tool name goes to the server, which looks up the
// updater itself. Runs again after a row is swapped in.
const decorate = doc => {
  if (!doc.getElementById("acv-style")) {
    const style = doc.createElement("style");
    style.id = "acv-style";
    style.textContent = ROW_CSS;
    doc.head.appendChild(style);
  }
  for (const row of doc.querySelectorAll("tr[data-row]")) {
    if (failures[row.dataset.row]) row.dataset.tool = row.dataset.row;
  }
  const rows = [...doc.querySelectorAll("tr[data-tool]")];
  for (const row of rows) {
    if (row.querySelector("button.acv-up")) continue;
    const tool = row.dataset.tool, cell = row.lastElementChild;
    const up = doc.createElement("button");
    up.className = "acv-up";
    up.dataset.tool = tool;
    up.textContent = pending.has(tool) && tool !== current ? t("queued_cancel") :
      failures[tool] ? t("retry") : t("update");
    up.onclick = () => pending.has(tool) && tool !== current ? cancelQueued([tool]) :
      enqueueTools([tool]);
    (cell.querySelector("code") || cell.firstElementChild || cell).after(up);
    if (failures[tool]) {
      const err = doc.createElement("div");
      err.className = "acv-err";
      err.dataset.tool = tool;
      err.textContent = t("update_failed") + failures[tool];
      cell.appendChild(err);
    }
  }
  syncButtons();
};
// Puts the summary above the table and the notes below it from a freshly saved page.
const swapSummary = (doc, fresh) => {
  for (const sel of [".summary", "#foot"]) {
    const old = doc.querySelector(sel), now = fresh.querySelector(sel);
    if (old && now) old.replaceWith(doc.importNode(now, true));
  }
};
// Puts one re-checked row, and the summary above the table, in place without reloading.
const swapRow = (tool, html) => {
  const doc = document, fresh = new DOMParser().parseFromString(html, "text/html");
  const pick = d => d.querySelector('tr[data-row="' + CSS.escape(tool) + '"]');
  const oldRow = pick(doc), newRow = pick(fresh);
  if (!oldRow || !newRow) return null;
  const row = doc.importNode(newRow, true);
  oldRow.replaceWith(row);
  swapSummary(doc, fresh);
  decorate(doc);
  return row;
};
// Replaces the report after a failure, so old versions never look current.
const notice = text => '<main><p class="note">' + text.replace(/&/g, "&amp;").replace(/</g, "&lt;") + '</p></main>';
const ok = r => r.ok ? r : Promise.reject(r.status + " " + r.statusText);
const get = path => fetch(path + "?" + Date.now()).then(ok).then(r => r.text());
const post = (path, body) => fetch(path, {method: "POST", body: JSON.stringify(body || {}),
  headers: {"X-AI-CLI-Version": "1", "Content-Type": "application/json"}}).then(ok).then(r => r.json());
// One request per tool, none waiting for another: each row is swapped in as soon as its
// tool answers. A failed request says so on its row; once all have answered, the merged
// report is saved and its summary shown.
const check = (doc, tools) => {
  const lines = [];
  return Promise.all(tools.map(tool => post("/row", {tool}).then(r => {
    lines.push(...r.lines);
    const holder = doc.createElement("tbody");
    holder.innerHTML = r.html;
    doc.querySelector('tr[data-row="' + CSS.escape(tool) + '"]')?.replaceWith(holder.firstElementChild);
    decorate(doc);
  }, e => {
    lines.push(tool + "\tcheck failed (" + e + ")");
    const cell = doc.querySelector('tr[data-row="' + CSS.escape(tool) + '"] .skel')?.parentElement;
    if (cell) {
      cell.className = "bad";
      cell.textContent = t("check_error", {error: e});
    }
  }))).then(() => post("/finish", {lines})).then(r => {
    swapSummary(doc, new DOMParser().parseFromString(r.page, "text/html"));
    decorate(doc);
    stamp(Number(r.written));
  });
};
// Runs after this script, so refresh() below is defined; with no report on disk yet it
// checks every tool at once.
Promise.resolve().then(() => {
  decorate(document);
  return document.documentElement.dataset.empty ? refresh().then(() => document) : document;
})
  .then(doc => {
    // A row whose check ran out of the chat report's 20 s is checked again here, with
    // the page's longer budget.
    const late = [...doc.querySelectorAll("tr[data-timeout]")];
    if (!late.length) return;
    for (const row of late) {
      row.removeAttribute("data-timeout");
      while (row.children.length > 1) row.lastElementChild.remove();
      row.insertAdjacentHTML("beforeend", SKELETON);
    }
    setBusy(true);
    refreshState = "busy"; refreshLabel();
    stamp(0);
    check(doc, late.map(row => row.dataset.row))
      .then(() => { refreshState = "refresh"; refreshLabel(); })
      .catch(e => {
        show(notice(t("check_retry", {error: e})));
        refreshState = "retry"; refreshLabel();
      })
      .finally(() => { setBusy(false); });
  });
// Update or Update all starts the queue; the server also serializes other tabs' requests.
const enqueueTools = tools => {
  if (busy || updating) return;  // nothing joins a queue that is already running
  for (const tool of tools) {
    if (pending.has(tool)) continue;
    pending.add(tool);
    queue.push(tool);
  }
  syncButtons();
  if (!updating && queue.length) void updateTools();
};
// Drops queued tools that have not started (all of them by default); the running one
// carries on.
const cancelQueued = (tools = [...queue]) => {
  for (const tool of tools) {
    const at = queue.indexOf(tool);
    if (at < 0) continue;
    queue.splice(at, 1);
    pending.delete(tool);
  }
  syncButtons();
};
allButton.onclick = () => {
  if (updating) cancelQueued();
  else enqueueTools([...document.querySelectorAll("tr[data-tool]")]
    .map(row => row.dataset.tool));
};
const updateTools = async () => {
  updating = true;
  syncButtons();
  let reloadAll = false;
  while (queue.length) {
    const tool = queue.shift();
    current = tool;
    syncButtons();  // the running row's button off, the queue count without it
    const doc = document;
    const row = doc.querySelector('tr[data-tool="' + CSS.escape(tool) + '"]');
    if (!row) {
      pending.delete(tool);
      current = "";
      syncButtons();
      continue;
    }
    const cell = row.lastElementChild, up = row.querySelector("button.acv-up");
    cell.querySelector(".acv-err")?.remove();
    const status = doc.createElement("div");
    status.className = "acv-run";
    status.textContent = t("updating");
    cell.appendChild(status);
    if (up) up.textContent = t("updating");
    const start = Date.now();
    let line = "";
    const tick = setInterval(() => {
      fetch("/progress").then(r => r.json()).then(p => {
        line = p.tool === tool ? p.line || "" : "";
      }).catch(() => {});
      status.textContent = Math.round((Date.now() - start) / 1000) + "s" + (line ? " \u00b7 " + line : "");
      status.title = line;
    }, 500);
    let result;
    try {
      const r = await fetch("/update?tool=" + encodeURIComponent(tool),
                            {method: "POST", headers: {"X-AI-CLI-Version": "1"}});
      result = await r.json().catch(() => ({ok: false, error: r.status + " " + r.statusText}));
    } catch (e) {
      result = {ok: false, error: String(e)};
    }
    clearInterval(tick);
    if (result.ok) delete failures[tool];
    else failures[tool] = result.error || "unknown error";
    pending.delete(tool);
    current = "";
    const swapped = result.page ? swapRow(tool, result.page) : null;
    if (result.written) stamp(Number(result.written));
    if (swapped && !failures[tool]) {
      const note = doc.createElement("div");
      note.className = "acv-run";
      note.textContent = t("updated_just_now");
      swapped.lastElementChild.appendChild(note);
    } else if (!swapped) {
      reloadAll = true;  // no saved lines: fall back to a full check
      status.textContent = failures[tool] ? t("failed") + failures[tool] : t("done");
      status.title = status.textContent;
      if (up) up.textContent = failures[tool] ? t("retry") : t("updated_message");
    }
    syncButtons();
  }
  updating = false;
  decorate(document);
  if (reloadAll) await refresh();
  else setBusy(false);
};
const refresh = () => {
  setBusy(true);
  refreshState = "busy"; refreshLabel();
  stamp(0);
  return get("/skeleton").then(show)
    .then(doc => check(doc, [...doc.querySelectorAll("tr[data-row]")].map(row => row.dataset.row)))
    .then(() => { refreshState = "refresh"; refreshLabel(); })
    .catch(e => {
      show(notice(t("check_retry", {error: e})));
      refreshState = "retry"; refreshLabel();
    })
    .finally(() => { setBusy(false); });
};
button.onclick = () => refresh();
