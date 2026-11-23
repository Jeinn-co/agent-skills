import colorsys
import json
import shutil
import subprocess
import unittest
import datetime as dt
from unittest.mock import patch

import html_report


class ResetStyleTests(unittest.TestCase):
    def setUp(self):
        timezone = patch("portable.report_timezone", return_value=dt.timezone(dt.timedelta(hours=8)))
        timezone.start()
        self.addCleanup(timezone.stop)

    def test_expiry_metadata_and_invalid_dates(self):
        note = "Reset 1: expires 2026-12-01 03:22 · 23 days left"
        markup = html_report.note_html(note, 1796066520000)
        self.assertIn('data-reset-expires="1796066520000"', markup)
        self.assertIn('<span data-reset-remaining>23 days left</span>', markup)
        for value in ("Reset 1: expiry not provided", "Reset 1: expires bad · 3 hours left",
                      "Reset details: unavailable", "Unrelated · notice"):
            self.assertNotIn("data-reset-expires", html_report.note_html(value))

    def test_gemini_week_uses_the_provider_reset_instant(self):
        instant = dt.datetime.fromisoformat("2026-11-30T11:45:46+08:00")
        now = instant - dt.timedelta(days=6, hours=23, minutes=54)
        page = html_report.card_html(
            "### GEMINI\nargon 14.0% used window weekly resets 2026-11-30T11:45:46+08:00 (6d23h) bar █\n",
            now=now)
        self.assertIn('data-window-reset="%d" data-window-minutes="10080"' %
                      (instant.timestamp() * 1000), page)
        self.assertIn("6d23h54m left", page)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the timer self-check")
    def test_timer_thresholds_and_clock_advance(self):
        driver = """const vm = require('node:vm');
const fs = require('node:fs');
let now = 1000000000000, tick, interval;
const make = minutes => {
  const note = {dataset: {resetExpires: now + minutes * 60000}, expiring: false,
    style: {setProperty(key, value) {this[key] = value;}}, remaining: {textContent: ''},
    toggleAttribute(key, value) {if (key === 'data-expiring') this.expiring = value;
      if (key === 'data-urgent') this.urgent = value;},
    querySelector() {return this.remaining;}};
  return note;
};
const notes = [301, 300, 180, 60, 59, 0, -1, 0.5, 1440, 31, 30, 29].map(make);
const quota = {dataset: {windowReset: now + 10078 * 60000, windowMinutes: 10080},
  fill: {style: {}}, remaining: {}, querySelector(key) {
    return key === '.tfill' ? this.fill : this.remaining;
  }};
const context = {document: {documentElement: {dataset: {}},
  querySelectorAll: selector => selector === '[data-window-reset]' ? [quota] : notes},
  navigator: {language: 'en'}, localStorage: {getItem: () => null, setItem: () => {}}, Date: {now: () => now},
  setInterval: (fn, ms) => {tick = fn; interval = ms;}};
context.window = context;
vm.runInNewContext(fs.readFileSync(0, 'utf8'), context);
const read = () => notes.map(n => ({expiring: n.expiring, urgent: n.urgent,
  hue: n.style['--reset-hue'], text: n.remaining.textContent}));
const initial = read();
const quotaStart = {width: quota.fill.style.width, text: quota.remaining.textContent};
now += 242 * 60000;
tick();
const later = read();
const quotaLater = {width: quota.fill.style.width, text: quota.remaining.textContent};
now += 10080 * 60000;
tick();
console.log(JSON.stringify({initial, later, interval, quotaStart, quotaLater,
  quotaExpired: {width: quota.fill.style.width, text: quota.remaining.textContent}}));
"""
        result = subprocess.run([shutil.which("node"), "-e", driver],
                                input=html_report.LANG_HEAD + '\n' + html_report.EXPIRY_SCRIPT, text=True,
                                capture_output=True, check=True, timeout=5)
        data = json.loads(result.stdout)
        rows = data["initial"]
        self.assertEqual([r["expiring"] for r in rows[:7]], [False, True, True, True, True, True, True])
        self.assertEqual([r["hue"] for r in rows[1:7]], [40, 20, 0, 0, 0, 0])
        self.assertEqual(rows[3]["text"], "1 hour left")
        self.assertEqual(rows[5]["text"], "expired")
        self.assertEqual(rows[7]["text"], "less than a minute left")
        self.assertEqual(rows[8]["text"], "1 day left")
        self.assertEqual([r["urgent"] for r in rows[9:]], [False, True, True])
        self.assertFalse(rows[3]["urgent"])
        self.assertTrue(rows[5]["urgent"])
        self.assertEqual(data["interval"], 60000)
        self.assertTrue(data["later"][0]["expiring"])
        self.assertEqual(data["later"][0]["hue"], 0)
        self.assertEqual(data["later"][0]["text"], "59 minutes left")
        self.assertFalse(data["later"][0]["urgent"])
        self.assertEqual(data["quotaStart"]["text"], "6d23h58m left")
        self.assertEqual(data["quotaLater"]["text"], "6d19h56m left")
        self.assertLess(float(data["quotaLater"]["width"][:-1]), float(data["quotaStart"]["width"][:-1]))
        self.assertEqual(data["quotaExpired"], {"width": "0%", "text": "0m left"})

    def test_warning_colors_have_small_text_contrast(self):
        def luminance(rgb):
            channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
            return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))
        for lightness, background in ((.25, (1, 1, 1)), (.78, (51/255, 65/255, 85/255))):
            for hue in range(41):
                fg = luminance(colorsys.hls_to_rgb(hue / 360, lightness, .85))
                bg = luminance(background)
                self.assertGreaterEqual((max(fg, bg) + .05) / (min(fg, bg) + .05), 4.5)


if __name__ == "__main__":
    unittest.main()
