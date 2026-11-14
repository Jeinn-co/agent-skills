// Canonical browser localization; distributed by scripts/sync_shared.py.
(function () {
  const config = window.reportLocale, root = document.documentElement;
  let language;
  try { language = localStorage.getItem(config.storageKey); } catch (error) {}
  if (language !== 'en' && language !== 'zh') {
    language = /^zh/i.test(navigator.language || '') ? 'zh' : 'en';
  }
  const translations = i18next.createInstance();
  translations.init({resources: config.resources, lng: language, fallbackLng: 'en',
    supportedLngs: ['en', 'zh'], initAsync: false, interpolation: {escapeValue: false}});
  window.reportT = (key, values = {}) => translations.t(key, {...values, lng: root.dataset.lang});
  window.setReportLanguage = function (language, persist = true) {
    if (language !== 'en' && language !== 'zh') return;
    root.dataset.lang = language;
    root.lang = language === 'zh' ? 'zh-Hant' : 'en';
    if (persist) {
      try { localStorage.setItem(config.storageKey, language); } catch (error) {}
      window.dispatchEvent(new Event('reportlanguagechange'));
    }
  };
  setReportLanguage(language, false);
})();
