(function () {
  const button = document.getElementById('lang');
  function label() {
    button.textContent = reportT('language_target');
    button.setAttribute('aria-label', reportT('language_aria'));
  }
  button.addEventListener('click', function () {
    setReportLanguage(document.documentElement.dataset.lang === 'zh' ? 'en' : 'zh');
  });
  window.addEventListener('reportlanguagechange', function () {
    label();
    if (typeof updateResetExpiry === 'function') updateResetExpiry();
  });
  label();
})();
