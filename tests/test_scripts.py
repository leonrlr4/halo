"""The shell entry points: trusted interpreter, fixed PATH, key validation."""

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = [ROOT / "bin/halo", ROOT / "scripts/setup", ROOT / "scripts/uninstall"]


class InterpreterTest(unittest.TestCase):
    def test_shebang_names_bash_by_absolute_path(self):
        # `#!/usr/bin/env bash` would find bash through the caller's PATH,
        # before the script could set its own.
        for s in SCRIPTS:
            self.assertEqual(s.read_text().splitlines()[0], "#!/usr/bin/bash", s.name)

    def test_path_is_fixed_before_any_command(self):
        for s in SCRIPTS:
            lines = [l for l in s.read_text().splitlines()
                     if l.strip() and not l.lstrip().startswith("#")]
            first = next(l for l in lines if not l.startswith("set "))
            self.assertTrue(first.startswith('export PATH="/usr/local/bin:/usr/bin:/bin'), s.name)

    def test_qml_runs_programs_by_absolute_path(self):
        qml = (ROOT / "Overlay.qml").read_text()
        for cmd in re.findall(r"command:\s*\[([^\]]*)\]", qml, re.S):
            first = re.findall(r'"([^"]*)"', cmd)[0]
            self.assertTrue(first.startswith("/"), first)

    def test_python_calls_programs_by_absolute_path(self):
        for f in (ROOT / "halo").rglob("*.py"):
            for m in re.finditer(r'subprocess\.(?:run|Popen)\(\s*\[\s*("?)([^",\]]+)', f.read_text()):
                quoted, prog = m.groups()
                if quoted:
                    self.assertTrue(prog.startswith("/"), f"{f.name}: {prog}")


class KeyValidationTest(unittest.TestCase):
    def run_setup(self, key):
        return subprocess.run([str(ROOT / "scripts/setup"), "--check", "--no-enable", "--key", key],
                              capture_output=True, text=True, timeout=30)

    def test_rejects_anything_that_could_leave_the_lua_string(self):
        for key in ['L")\nos.execute("x', 'SUPER + L"', "SUPER +\nL", "SUPER + L\\", "SUPER + L\r"]:
            r = self.run_setup(key)
            self.assertEqual(r.returncode, 2, repr(key))
            self.assertIn("not a valid key", r.stderr)

    def test_accepts_real_bindings(self):
        for key in ["SUPER + SHIFT + L", "CTRL + ALT + comma", "F9", "SUPER+L"]:
            r = self.run_setup(key)
            self.assertNotEqual(r.returncode, 2, f"{key!r}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
