const SKELETON = __SKELETON__;
const root = document.documentElement;
const button = document.getElementById("refresh"), picker = document.getElementById("theme");
let state = "refresh";
const word = key => reportT(key === "busy" ? "refreshing" : key);
const GLOBE = __GLOBE__;
// The report's own switch rewrites the language button as plain text, so its icon is put back here.
const relabel = () => {
  const lang = document.getElementById("lang");
  lang.innerHTML = GLOBE + "<span>" + reportT("language_target") + "</span>";
  picker.setAttribute("aria-label", reportT("theme"));
  button.querySelector("span").textContent = word(state);
  for (const option of picker.options) option.textContent = word(option.value);
  document.querySelectorAll('[data-provider-login]').forEach(signIn => {
    if (!signIn.disabled) signIn.textContent = reportT('sign_in', {name: signIn.dataset.providerName});
  });
};
window.addEventListener("reportlanguagechange", relabel);
const THEMES = ["auto", "light", "dark"];
let theme = "auto";  // Auto follows the OS; the choice is kept per browser
try { theme = localStorage.getItem("aiu-theme") || "auto"; } catch (e) {}
if (!THEMES.includes(theme)) theme = "auto";
picker.value = theme;
const applyTheme = () => {
  if (theme === "auto") delete root.dataset.theme;
  else root.dataset.theme = theme;
};
applyTheme();
relabel();
picker.onchange = () => {
  theme = THEMES.includes(picker.value) ? picker.value : "auto";
  try { localStorage.setItem("aiu-theme", theme); } catch (e) {}
  applyTheme();
};
// Chrome treats a mouse-focused <select> as :focus-visible, so the ring is keyed to the last input.
addEventListener("pointerdown", () => root.classList.add("mouse"), true);
addEventListener("keydown", () => root.classList.remove("mouse"), true);
const ok = r => r.ok ? r : Promise.reject(r.status + " " + r.statusText);
const get = path => fetch(path + "?" + Date.now()).then(ok).then(r => r.text());
const post = (path, body) => fetch(path, {method: "POST", body: JSON.stringify(body || {}),
  headers: {"X-AI-Usage": "1", "Content-Type": "application/json"}}).then(ok).then(r => r.json());
function bindProviderLogin(doc) {
  doc.querySelectorAll('[data-provider-login]').forEach(signIn => {
    const provider = signIn.dataset.providerLogin, name = signIn.dataset.providerName;
    const command = provider === 'CLAUDE' ? 'claude auth login' : 'codex login';
    signIn.hidden = false;
    signIn.onclick = async () => {
      const status = doc.getElementById(provider.toLowerCase() + '-login-status');
      signIn.disabled = true;
      signIn.textContent = reportT('signing_in');
      status.hidden = false;
      status.textContent = reportT('authorize', {name});
      try {
        const result = await post('/login', {id: provider});
        status.textContent = result.message;
        if (result.ok) button.click();
      } catch (error) {
        status.textContent = reportT('login_failed', {command});
      } finally {
        signIn.disabled = false;
        signIn.textContent = reportT('sign_in', {name});
      }
    };
  });
}
// Everything in <main> under the header.
const below = () => [...document.querySelector("main").children].filter(el => !el.matches(".top"));
// Puts a freshly fetched page's content under this header, keeping the header itself.
const swap = html => {
  const fresh = new DOMParser().parseFromString(html, "text/html").querySelector("main");
  fresh.querySelector(".top")?.remove();
  below().forEach(el => el.remove());
  document.querySelector("main").append(...fresh.children);
};
// Replaces the report after a failure, so old numbers never look current.
const notice = text => {
  below().forEach(el => el.remove());
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = text;
  document.querySelector("main").append(note);
};
// One request per provider (and one for the benchmark), none waiting for another. A
// failed card says so in place; once all have answered the merged report is saved.
const update = (ids, bench) => {
  const sections = [];
  const jobs = ids.map(id => post("/card", {id}).then(r => {
    sections.push(r.raw);
    document.querySelector('.card[data-id="' + id + '"]').outerHTML = r.html;
    window.updateResetExpiry?.();
    bindProviderLogin(document);
  }, e => {
    sections.push("### " + id + "\nusage call failed (" + e + ")\n");
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = reportT('fetch_failed', {error: e, action: word('refresh')});
    document.querySelector('.card[data-id="' + id + '"] .skel-body')?.replaceWith(note);
  }));
  if (bench) jobs.push(post("/bench").then(r => {
    sections.push(r.raw);
    document.getElementById("bench").innerHTML = r.html;
  }, e => {
    sections.push("### CURSORBENCH\nbench failed (" + e + ")\n");
    document.getElementById("bench").innerHTML = "";
  }));
  return Promise.all(jobs).then(() => post("/finish", {sections}));
};
const busy = work => {
  button.disabled = true;
  state = "busy";
  relabel();
  return work()
    .then(() => { state = "refresh"; })
    .catch(e => {
      notice(reportT('fetch_failed', {error: e, action: word('retry')}));
      state = "retry";
    })
    .finally(() => { button.disabled = false; relabel(); });
};
bindProviderLogin(document);
button.onclick = () => busy(() => get("/skeleton").then(html => {
  swap(html);
  return update([...document.querySelectorAll(".card[data-id]")].map(card => card.dataset.id), true);
}));
if (root.dataset.empty) {
  button.click();  // no report on disk yet
} else {
  // A card whose lookup ran out of the chat report's 20 s is fetched again here,
  // with the page's longer budget.
  const late = [...document.querySelectorAll(".card[data-timeout]")];
  if (late.length) {
    late.forEach(card => {
      card.querySelectorAll(".row, .note").forEach(el => el.remove());
      card.querySelector(".now").insertAdjacentHTML("beforebegin", SKELETON);
    });
    busy(() => update(late.map(card => card.dataset.id), false));
  }
}
