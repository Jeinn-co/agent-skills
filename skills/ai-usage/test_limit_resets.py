import io
import json
import urllib.error
import datetime as dt
import unittest
from unittest.mock import patch, MagicMock

import html_report
import limit_resets as resets

NOW = dt.datetime(2026, 11, 6, 22, 0, tzinfo=dt.timezone.utc)


class ResetTests(unittest.TestCase):
    def setUp(self):
        timezone = patch("portable.report_timezone", return_value=dt.timezone(dt.timedelta(hours=8)))
        timezone.start()
        self.addCleanup(timezone.stop)

    def test_codex_count_and_expiry(self):
        rows = resets.codex_lines({"availableCount": 3, "credits": [
            {"status": "available", "title": "Full reset", "expiresAt": NOW.timestamp() + 3900},
            {"status": "consumed", "title": "Used", "expiresAt": None}]}, NOW)
        self.assertIn("3 available", rows[0])
        self.assertIn("1 hour 5 minutes left", rows[1])
        self.assertIn("1 of 3 returned", rows[2])
        self.assertNotIn("Used", "\n".join(rows))

    def test_count_only_is_not_zero(self):
        for details in (None, []):
            lines = resets.codex_lines({"availableCount": 2, "credits": details}, NOW)
            self.assertIn("2 available", lines[0])
            self.assertEqual(len(lines), 2)

    def test_zero_and_missing_are_distinct(self):
        self.assertEqual(resets.codex_lines({"availableCount": 0, "credits": []}),
                         ["Usage limit resets: 0 available"])
        for data in (None, {}, {"availableCount": True}, {"availableCount": -1}):
            self.assertIn("unavailable", resets.codex_lines(data)[0])

    def test_unknown_expiry_is_not_no_expiry(self):
        self.assertEqual(resets.expiry(None, NOW), "expiry not provided")
        for value in (True, "garbage", "2026-12-01T00:00:00", float("inf")):
            self.assertIn("unavailable", resets.expiry(value, NOW))

    def test_expired_and_iso_expiry(self):
        self.assertIn("expired", resets.expiry(NOW.timestamp() - 60, NOW))
        self.assertIn("1 day left", resets.expiry("2026-11-07T22:00:00Z", NOW))
        self.assertIn("expires 2026-11-07 06:01", resets.expiry(NOW.timestamp() + 60, NOW))

    def test_short_waits_and_exact_expiry(self):
        for seconds, expected in ((30, "less than a minute left"), (60, "1 minute left"),
                                  (3600, "1 hour left"), (0, "expired")):
            self.assertIn(expected, resets.expiry(NOW.timestamp() + seconds, NOW))

    def test_numeric_date_and_cross_year(self):
        # Both UTC and offset-bearing inputs must display Taipei time.
        stamp = dt.datetime(2026, 12, 1, 3, 22, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        result = resets.expiry(stamp.isoformat(), NOW)
        self.assertIn("2026-12-01 03:22", result)
        self.assertEqual(result, resets.expiry("2026-11-30T19:22:00Z", NOW))
        self.assertNotIn("Taipei time", result)
        self.assertNotIn("UTC", result)
        self.assertNotIn("+08", result)
        self.assertIn("2027-", resets.expiry("2027-02-01T00:00:00Z", NOW))
        self.assertNotIn("0 minutes", result)


    def test_claude_verified_zero(self):
        self.assertEqual(resets.claude_lines({"eligible": False, "ineligible_reason": "no_grant",
                                             "grants": []}, NOW), ["Limit resets: 0 available"])

    def test_claude_unknown_is_not_zero(self):
        for data in (None, {}, {"eligible": False, "ineligible_reason": "surface", "grants": []},
                     {"eligible": True, "grants": [{"resets_left": True}]},
                     {"eligible": True, "grants": [{"resets_left": 1, "ends_at": "bad"}]}):
            self.assertIn("unavailable", resets.claude_lines(data, NOW)[0])

    def test_claude_grants_sum_excludes_expired_and_future(self):
        data = {"eligible": True, "grants": [
            {"resets_left": 2, "label": "Full reset", "ends_at": "2026-11-07T22:00:00Z"},
            {"resets_left": 9, "ends_at": "2026-11-05T22:00:00Z"},
            {"resets_left": 7, "starts_at": "2026-12-01T00:00:00Z"},
            {"resets_left": 0}]}
        rows = resets.claude_lines(data, NOW)
        self.assertIn("2 available", rows[0])
        self.assertEqual(len(rows), 2)
        self.assertIn("1 day left", rows[1])

    def test_auth_request_is_get_to_vendor_only(self):
        response = MagicMock()
        response.__enter__.return_value = io.StringIO(json.dumps({
            "cedar_ember": {"eligible": False, "ineligible_reason": "no_grant", "grants": []}}))
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict("os.environ", {"CLAUDE_CODE_OAUTH_TOKEN": "fake-secret"}), \
                patch.object(resets.urllib.request, "build_opener", return_value=opener):
            lines = resets.claude_report("2.1.318")
        request = opener.open.call_args[0][0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.host, "api.anthropic.com")
        self.assertIn("cedar_ember=1&skip_spend=1", request.full_url)
        self.assertEqual(request.get_header("X-app"), "cli")
        self.assertIn("claude-cli/2.1.318", request.get_header("User-agent"))
        self.assertNotIn("fake-secret", str(lines))
        self.assertIn("0 available", lines[0])

    def test_failures_do_not_leak_secrets_or_become_zero(self):
        for error in (ValueError("fake-secret"), urllib.error.HTTPError(
                "https://api.anthropic.com/", 401, "fake-secret", {}, None)):
            with patch.object(resets, "read_claude", side_effect=error):
                lines = resets.claude_report("2.1.318")
            self.assertIn("unavailable", lines[0])
            self.assertNotIn("fake-secret", str(lines))

    def test_redirects_are_blocked(self):
        self.assertIsNone(resets.NoRedirect().redirect_request(None, None, 302, "", {},
                                                              "https://other.example/"))

    @patch.dict("os.environ", {"AI_USAGE_METADATA": "1"})
    def test_html_shows_compact_expiry_and_escapes_notes(self):
        raw = "### CHATGPT\nplan: plus\n" + "\n".join(resets.codex_lines({
            "availableCount": 1, "credits": [{"status": "available", "title": "<script>bad</script>",
                                              "expiresAt": NOW.timestamp() + 60}]}, NOW))
        page = html_report.render(raw + '\n<script>bad note</script>')
        self.assertIn("1 available", page)
        self.assertIn("expires 2026-", page)
        self.assertNotIn("&lt;script&gt;bad&lt;/script&gt;", page)
        self.assertIn("&lt;script&gt;bad note&lt;/script&gt;", page)
        self.assertIn('data-reset-expires="', page)
        self.assertNotIn("Taipei time", page)
        self.assertNotIn("Full reset", page)

    def test_html_groups_reset_notes_with_a_legend(self):
        raw = ("### CHATGPT\nplan: plus\nUsage limit resets: 2 available\n"
               "Reset 1: expiry not provided\nReset details: 1 of 2 returned\nOther notice")
        page = html_report.render(raw)
        self.assertIn('<fieldset class="reset-credits"><legend>Usage limit resets: 2 available</legend>', page)
        group = page.split('<fieldset class="reset-credits">', 1)[1].split('</fieldset>', 1)[0]
        self.assertIn("Reset 1: expiry not provided", group)
        self.assertIn("Reset details: 1 of 2 returned", group)
        self.assertNotIn("Other notice", group)
        self.assertIn('.lbl,.reset-credits{font-size:13px}', page)

    def test_html_count_only_and_unavailable_groups(self):
        for value in ("0 available", "2 available", "unavailable (<error>)"):
            page = html_report.render("### CHATGPT\nplan: plus\nUsage limit resets: " + value)
            self.assertEqual(page.count('<fieldset class="reset-credits">'), 1)
            self.assertEqual(page.count('</fieldset>'), 1)
            self.assertNotIn("<error>", page)
        self.assertNotIn('<fieldset', html_report.render("### CLAUDE\nplan: pro"))
        self.assertNotIn('<fieldset', html_report.render("### CHATGPT\nUsage limit resets: 2 available", loading=True))

    @patch.dict("os.environ", {"AI_USAGE_METADATA": "1"})
    def test_claude_grants_share_fieldset_and_expiry_timer(self):
        lines = resets.claude_lines({"eligible": True, "grants": [
            {"resets_left": 2, "ends_at": "2026-12-01T03:22:00+08:00"},
            {"resets_left": 1, "ends_at": "2026-12-02T06:09:00+08:00"}]}, NOW)
        page = html_report.render("### CLAUDE\nplan: pro\n" + "\n".join(lines) + "\nSource: CLI")
        group = page.split('<fieldset class="reset-credits">', 1)[1].split('</fieldset>', 1)[0]
        self.assertIn('<legend>Limit resets: 3 available</legend>', group)
        self.assertEqual(group.count('data-reset-expires='), 2)
        self.assertNotIn('Source: CLI', group)
        for data in ({"eligible": False, "ineligible_reason": "no_grant", "grants": []}, None):
            page = html_report.render("### CLAUDE\n" + "\n".join(resets.claude_lines(data, NOW)))
            self.assertIn('<fieldset class="reset-credits">', page)


if __name__ == "__main__":
    unittest.main()
