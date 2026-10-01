import importlib.util
import io
import contextlib
import os
import stat
import sys
import tempfile
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
            out = io.StringIO()
            with mock.patch.object(run, "HOME", home), fetch, contextlib.redirect_stdout(out):
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
