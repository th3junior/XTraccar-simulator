/** @typedef {'en'|'es'|'pt'} Lang */

const I18N_STORAGE_KEY = "xtraccar-lang";

function detectLang() {
  const saved = localStorage.getItem(I18N_STORAGE_KEY);
  if (saved === "en" || saved === "es" || saved === "pt") return saved;
  const nav = (navigator.language || "en").toLowerCase();
  if (nav.startsWith("pt")) return "pt";
  if (nav.startsWith("es")) return "es";
  return "en";
}

function getNested(obj, path) {
  return path.split(".").reduce((o, k) => (o && o[k] != null ? o[k] : undefined), obj);
}

function interpolate(str, params) {
  if (!params) return str;
  return str.replace(/\{(\w+)\}/g, (_, k) => (params[k] != null ? String(params[k]) : `{${k}}`));
}

/** @type {Lang} */
let currentLang = detectLang();

/** @type {Record<Lang, object>} */
const catalogs = { en: {}, es: {}, pt: {} };

function registerLocales(en, es, pt) {
  catalogs.en = en;
  catalogs.es = es;
  catalogs.pt = pt;
}

function t(key, params) {
  let str = getNested(catalogs[currentLang], key);
  if (str == null) str = getNested(catalogs.en, key);
  if (str == null) return key;
  return interpolate(String(str), params);
}

function localeTag() {
  if (currentLang === "es") return "es-ES";
  if (currentLang === "pt") return "pt-BR";
  return "en-US";
}

function htmlLang() {
  if (currentLang === "es") return "es";
  if (currentLang === "pt") return "pt-BR";
  return "en";
}

function setLang(lang) {
  if (lang !== "en" && lang !== "es" && lang !== "pt") return;
  currentLang = lang;
  localStorage.setItem(I18N_STORAGE_KEY, lang);
  document.documentElement.lang = htmlLang();
  applyDomI18n();
  syncLangDropdownUI(lang);
  window.dispatchEvent(new CustomEvent("xtraccar:lang", { detail: { lang } }));
}

function syncLangDropdownUI(lang) {
  document.querySelectorAll(".lang-option").forEach((btn) => {
    const on = btn.dataset.lang === lang;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const active = document.querySelector(`.lang-option[data-lang="${lang}"]`);
  const triggerFlag = document.getElementById("langTriggerFlag");
  const triggerLabel = document.getElementById("langTriggerLabel");
  if (active && triggerFlag) {
    const flag = active.querySelector(".lang-flag");
    if (flag) triggerFlag.innerHTML = flag.innerHTML;
  }
  if (triggerLabel) {
    const nameEl = active?.querySelector(".lang-option-name");
    triggerLabel.textContent = nameEl?.textContent?.trim() || lang.toUpperCase();
  }
}

function setLangMenuOpen(open) {
  const root = document.getElementById("langDropdown");
  const menu = document.getElementById("langMenu");
  const trigger = document.getElementById("langTrigger");
  if (!root || !menu || !trigger) return;
  root.classList.toggle("is-open", open);
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) menu.removeAttribute("hidden");
  else menu.setAttribute("hidden", "");
}

function applyDomI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    if (key) el.innerHTML = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.placeholder = t(key);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.title = t(key);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    const key = el.getAttribute("data-i18n-aria");
    if (key) el.setAttribute("aria-label", t(key));
  });
  document.querySelectorAll("select[data-i18n-options]").forEach((sel) => {
    const prefix = sel.getAttribute("data-i18n-options");
    sel.querySelectorAll("option[data-i18n-opt]").forEach((opt) => {
      opt.textContent = t(`${prefix}.${opt.getAttribute("data-i18n-opt")}`);
    });
  });
  const meta = document.querySelector('meta[name="description"]');
  if (meta) meta.content = t("meta.description");
  document.title = t("meta.title");
}

function initLangSwitcher() {
  const root = document.getElementById("langDropdown");
  const menu = document.getElementById("langMenu");
  const trigger = document.getElementById("langTrigger");

  document.querySelectorAll(".lang-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      setLang(/** @type {Lang} */ (btn.dataset.lang));
      setLangMenuOpen(false);
    });
  });

  trigger?.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = root?.classList.contains("is-open");
    setLangMenuOpen(!open);
  });

  document.addEventListener("click", (e) => {
    if (!root?.contains(/** @type {Node} */ (e.target))) setLangMenuOpen(false);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setLangMenuOpen(false);
  });

  setLang(currentLang);
  setLangMenuOpen(false);
}

window.i18n = {
  t,
  setLang,
  get lang() { return currentLang; },
  localeTag,
  registerLocales,
  applyDomI18n,
  initLangSwitcher,
};
