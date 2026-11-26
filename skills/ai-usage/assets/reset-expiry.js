function updateResetExpiry() {
  const now = Date.now();
  document.querySelectorAll('[data-window-reset]').forEach(row => {
    const left = Math.max(0, (Number(row.dataset.windowReset) - now) / 60000);
    const total = Number(row.dataset.windowMinutes);
    if (!Number.isFinite(left) || !(total > 0)) return;
    const share = Math.min(100, left * 100 / total), fill = row.querySelector('.tfill');
    fill.style.width = share + '%';
    // Time left: full = red, almost reset = green (html_report.hue). Usage bar above: html_report.pace_hue.
    fill.style.setProperty('--th', Math.round(share <= 50 ? 142 - 104 * share / 50 : 38 - 38 * (share - 50) / 50));
    const pct = Number(row.dataset.windowPct), bar = row.previousElementSibling;
    const d = pct - (100 - share), ramp = x => Math.min(Math.max(x, 0), 1);
    if (bar && Number.isFinite(pct))
      bar.style.setProperty('--h', Math.round(142 - 104 * ramp((d + 12) / 4) - 38 * ramp(d / 4)));
    const minutes = Math.floor(left);
    const days = Math.floor(minutes / 1440), hours = Math.floor(minutes % 1440 / 60);
    const mins = String(minutes % 60).padStart(days || hours ? 2 : 1, '0');
    const duration = (days ? days + 'd' : '') + (days || hours ? hours + 'h' : '') + mins + 'm';
    row.querySelector('[data-window-remaining]').textContent = reportT('remaining', {duration});
  });
  document.querySelectorAll('[data-reset-expires]').forEach(note => {
    const left = (Number(note.dataset.resetExpires) - now) / 60000;
    if (!Number.isFinite(left)) return;
    note.toggleAttribute('data-expiring', left <= 300);
    note.toggleAttribute('data-urgent', left <= 30);
    note.style.setProperty('--reset-hue', Math.max(0, Math.min(40, (left - 60) / 6)));
    const minutes = Math.max(0, Math.floor(left));
    const units = [[Math.floor(minutes / 1440), 'day'],
      [Math.floor(minutes % 1440 / 60), 'hour'], [minutes % 60, 'minute']];
    const duration = (minutes >= 1440 ? units.slice(0, 2) : units)
      .filter(([n]) => n).map(([count, unit]) => reportT(unit, {count})).join(' ');
    note.querySelector('[data-reset-remaining]').textContent = left <= 0 ? reportT('expired') :
      reportT('remaining', {duration: duration || reportT('less_than_minute')});
  });
}
updateResetExpiry();
setInterval(updateResetExpiry, 60000);
