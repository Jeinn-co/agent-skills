import importlib.util
import io
import contextlib
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "ai-cli-version" / "run.py"


def load():
    spec = importlib.util.spec_from_file_location("ai_cli_version_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParallelCheckTests(unittest.TestCase):
    def test_all_tools_start_together_and_output_stays_in_tool_order(self):
        run = load()
        barrier = threading.Barrier(5, timeout=3)

        def check(name):
            barrier.wait()
            return name + "\tchecked\n"

        out = io.StringIO()
        with mock.patch.object(run, "check_tool", side_effect=check), \
                mock.patch.object(sys, "argv", [str(SCRIPT)]), \
                mock.patch.object(run, "output_format", return_value="md"), \
                mock.patch.object(run, "selected_tools", return_value=list(run.CHECKS)), \
                contextlib.redirect_stdout(out):
            run.main()
        lines = out.getvalue().splitlines()
        rows = lines[1:lines.index("### SUMMARY")]
        self.assertEqual(rows, [name + "\tchecked" for name in run.CHECKS])


class SavedReportTests(unittest.TestCase):
    def test_reload_uses_saved_lines_instead_of_stale_html_without_checking_tools(self):
        run = load()
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / 'report.html'
            lines = Path(folder) / 'report.lines'
            page.write_text('obsolete presentation')
            lines.write_text('["### ai-cli-version old", "codex\\tinstalled=1\\tlatest=1\\tstatus=up to date"]')
            with mock.patch.object(run, 'PAGE', str(page)), mock.patch.object(run, 'LINES', str(lines)), \
                    mock.patch.object(run, 'check_tool', side_effect=AssertionError('reload must not check tools')):
                rendered = run.saved_page()
            self.assertNotIn('obsolete presentation', rendered)
            self.assertIn('Codex', rendered)
            self.assertIn('ai-cli-version ' + run.VERSION, rendered)


class SummaryTests(unittest.TestCase):
    def summary(self, text):
        spec = importlib.util.spec_from_file_location("ai_cli_version_html", SCRIPT.parent / "html_report.py")
        html_report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(html_report)
        return html_report.summary(text.splitlines())

    def test_outdated_tools_get_summary_and_prompt(self):
        self.assertEqual(self.summary(
            "### skipped grok\n"
            "claude\tinstalled=1\tstatus=up to date\n"
            "codex\tinstalled=1\tstatus=update available\n"
            "muse\tinstalled=1\tstatus=update available\n"), [
            "> **→ 2 updates available:** Codex, Muse Code.",
            "_Not checked (setup): Grok Build_",
            "",
            "**Update the 2 outdated CLIs now?**",
            "`[y]` Update all · `[Esc]` Skip"])

    def test_all_current_has_no_prompt(self):
        self.assertEqual(self.summary("claude\tinstalled=1\tstatus=up to date\nagy\tnot installed\n"),
                         ["> **All up to date.**"])

    def test_served_page_decides_so_chat_has_no_prompt(self):
        spec = importlib.util.spec_from_file_location("ai_cli_version_html", SCRIPT.parent / "html_report.py")
        html_report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(html_report)
        self.assertEqual(html_report.summary(["codex\tinstalled=1\tstatus=update available"], prompt=False),
                         ["> **→ 1 update available:** Codex."])


class CodexDaemonTests(unittest.TestCase):
    def check(self, installed, latest, daemon):
        run = load()
        out = io.StringIO()
        with mock.patch.object(run, "argv", return_value=["codex", "--version"]), \
                mock.patch.object(run, "run", return_value="codex-cli " + installed), \
                mock.patch.object(run, "npm_package", return_value=({"latest": latest}, {})), \
                mock.patch.object(run, "codex_daemon", return_value=run.parse_version(daemon)), \
                contextlib.redirect_stdout(out):
            run.check_codex()
        return out.getvalue().strip()

    def test_stale_daemon_alone_is_an_update(self):
        line = self.check("0.170.0", "0.170.0", "0.160.1")
        self.assertIn("status=update available", line)
        self.assertIn("update_cmd=codex app-server daemon update", line)
        self.assertIn("daemon=0.160.1", line)

    def test_outdated_cli_updates_cli_then_daemon(self):
        line = self.check("0.160.1", "0.170.0", "0.160.1")
        self.assertIn("update_cmd=codex update; codex app-server daemon update", line)

    def test_current_daemon_changes_nothing(self):
        line = self.check("0.170.0", "0.170.0", "0.170.0")
        self.assertIn("status=up to date", line)
        self.assertIn("update_cmd=codex update", line)

    def test_rows_render_with_and_without_a_lagging_daemon(self):
        spec = importlib.util.spec_from_file_location("ai_cli_version_html", SCRIPT.parent / "html_report.py")
        html_report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(html_report)
        page = html_report.render([
            "claude\tinstalled=1.0.0\tlatest=1.0.0\tstatus=up to date",
            "codex\tinstalled=0.170.0\tlatest=0.170.0\tstatus=update available\tdaemon=0.160.1"])
        self.assertIn("daemon 0.160.1", page)

    def test_update_plan_runs_only_known_codex_steps_in_order(self):
        run = load()
        with mock.patch.object(run, "argv", side_effect=lambda *a: list(a)):
            plan = run.update_plan("codex", "codex update; codex app-server daemon update; rm -rf x")
        self.assertEqual([args for args, _ in plan],
                         [["codex", "update"], ["codex", "app-server", "daemon", "update"]])


@unittest.skipIf(os.name == "nt", "POSIX fake executables are used")
class AntigravityCheckTests(unittest.TestCase):
    PAGE = "Antigravity CLI auto updater is running! Stable Version: 1.2.15. Rolled out to 40%"

    def check(self, agy_source=None, page=PAGE):
        run = load()
        with tempfile.TemporaryDirectory() as home:
            if agy_source is not None:
                cli = Path(home) / ".gemini" / "bin" / "agy"
                cli.parent.mkdir(parents=True)
                cli.write_text("#!%s\n%s" % (sys.executable, agy_source), encoding="utf-8")
                cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
            fetch = (mock.patch.object(run, "get_text", side_effect=page) if isinstance(page, Exception)
                     else mock.patch.object(run, "get_text", return_value=page))
            release = mock.patch.object(run, "get_json", side_effect=OSError("release unavailable"))
            out = io.StringIO()
            with mock.patch.object(run, "HOME", home), fetch, release, contextlib.redirect_stdout(out):
                run.check_agy()
            return out.getvalue().strip()

    def test_not_installed_when_only_the_ide_launcher_exists(self):
        self.assertEqual(self.check(None), "agy\tnot installed")

    def test_update_available_uses_the_full_path(self):
        line = self.check('import os\nassert os.environ.get("AGY_CLI_DISABLE_AUTO_UPDATE") == "1"\nprint("1.2.14")\n')
        self.assertIn("installed=1.2.14", line)
        self.assertIn("latest=1.2.15", line)
        self.assertIn("status=update available", line)
        self.assertIn("released=?", line)
        self.assertIn("rolled out to 40%", line)
        self.assertRegex(line, r"update_cmd=/\S+/\.gemini/bin/agy update")

    def test_updater_down_is_a_failed_row(self):
        line = self.check('print("1.2.14")\n', page=OSError("network down"))
        self.assertTrue(line.startswith("agy\tcheck failed ("), line)

    def test_unrecognised_version_is_a_failed_row(self):
        line = self.check('print("garbage")\n')
        self.assertTrue(line.startswith("agy\tcheck failed ("), line)


if __name__ == "__main__":
    unittest.main()
