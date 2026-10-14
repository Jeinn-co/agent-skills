import importlib.util
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "skills" / "ai-usage"
spec = importlib.util.spec_from_file_location("ai_usage_portable", SKILL / "portable.py")
portable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portable)


class LookupTimeoutTests(unittest.TestCase):
    def test_completed_lookup_keeps_output_and_exit_code(self):
        result = portable.run_bounded(
            [sys.executable, "-c", "print('live usage'); raise SystemExit(2)"],
            timeout=3, stdout=subprocess.PIPE, **portable.text_kwargs())
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "live usage")

    def test_timeout_stops_the_cli_child_as_well_as_the_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "heartbeat"
            child = (
                "import sys,time; from pathlib import Path; "
                "path=Path(sys.argv[1]);\n"
                "while True:\n"
                " path.write_text(str(time.monotonic())); time.sleep(0.05)\n"
            )
            probe = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); "
                "time.sleep(60)"
            )
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                portable.run_bounded(
                    [sys.executable, "-c", probe, child, str(heartbeat)], timeout=1)
            self.assertLess(time.monotonic() - started, 5)
            self.assertTrue(heartbeat.exists())
            before = heartbeat.read_text()
            time.sleep(0.2)
            self.assertEqual(heartbeat.read_text(), before)

    def run_launcher(self, slow_provider=False, slow_bench=False):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in ("run.py", "portable.py"):
                shutil.copyfile(SKILL / name, target / name)
            for name in ("claude_usage.py", "codex_usage.py", "grok_usage.py",
                         "muse_usage.py", "agy_usage.py"):
                body = "print('live ' + __file__, flush=True)\n"
                if slow_provider and name == "muse_usage.py":
                    body += "import time; time.sleep(60)\n"
                (target / name).write_text(body, encoding="utf-8")
            (target / "session_info.py").write_text(
                "print('no local session')\n", encoding="utf-8")
            bench = "print('benchmark complete', flush=True)\n"
            if slow_bench:
                bench = "print('partial benchmark', flush=True)\nimport time; time.sleep(60)\n"
            (target / "cursorbench.py").write_text(bench, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-c",
                 "import portable,runpy; portable.CALL_TIMEOUT=0.5; runpy.run_path('run.py')"],
                cwd=target, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=8, **portable.text_kwargs())

    def test_timed_out_provider_does_not_prevent_later_provider_or_benchmark(self):
        result = self.run_launcher(slow_provider=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage call timed out after 0.5s; skipped", result.stdout)
        self.assertIn("agy_usage.py", result.stdout)
        self.assertIn("benchmark complete", result.stdout)

    def test_timed_out_benchmark_keeps_usage_without_a_partial_table(self):
        result = self.run_launcher(slow_bench=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agy_usage.py", result.stdout)
        self.assertIn("bench failed (lookup timed out after 0.5s; skipped)", result.stdout)
        self.assertNotIn("partial benchmark", result.stdout)


if __name__ == "__main__":
    unittest.main()
