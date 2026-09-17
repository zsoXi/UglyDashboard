"""V6: owner-token rotation and the repository secret-leak guard.

All secrets used here are synthetic and built at runtime; no real credential
value is ever written to a file that the guard would ship.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mission_control.store import Store  # noqa: E402


class RotateOwnerTokenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="v6-rotate-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def test_rotation_changes_only_owner_token(self):
        with Store(self.directory) as store:
            owner_before = store.secret("owner.token")
            mcp = store.secret("mcp.token")
            pairing = store.secret("pairing.key")
            store.set_setting("probe", "kept")
            rotated = store.rotate_secret("owner.token")
            self.assertNotEqual(rotated, owner_before)
            self.assertEqual(store.secret("owner.token"), rotated)
            self.assertEqual(store.secret("mcp.token"), mcp)
            self.assertEqual(store.secret("pairing.key"), pairing)
            self.assertEqual(store.setting("probe"), "kept")
        self.assertTrue((self.directory / "observer.sqlite").exists())
        # No backup copy may keep the previous owner token readable.
        self.assertEqual(list(self.directory.glob("owner.token.*.bak")), [])

    def test_rotation_creates_a_missing_secret(self):
        with Store(self.directory) as store:
            value = store.rotate_secret("owner.token")
            self.assertGreaterEqual(len(value), 32)
            self.assertEqual(store.secret("owner.token"), value)

    def test_rotation_rejects_path_traversal_names(self):
        with Store(self.directory) as store:
            for name in ("", ".", "..", "a/b", "a" + chr(92) + "b"):
                with self.assertRaises(ValueError):
                    store.rotate_secret(name)


class CheckSecretsTests(unittest.TestCase):
    def _run(self, root):
        script = ROOT / "scripts" / "check_secrets.py"
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(script), "--root", str(root), "--quiet"],
            capture_output=True,
            text=True,
        )

    def test_guard_flags_a_leaked_fragment_without_printing_it(self):
        with tempfile.TemporaryDirectory(prefix="v6-guard-") as tmp:
            directory = Path(tmp)
            leaked = "Z" * 40
            (directory / "leak.log").write_text(
                "open http://127.0.0.1:8780/#access=" + leaked + "\n", "utf-8"
            )
            (directory / "clean.txt").write_text("nothing to see here\n", "utf-8")
            result = self._run(directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("leak.log", result.stdout)
            self.assertNotIn(leaked, result.stdout + result.stderr)

    def test_guard_passes_on_a_clean_tree(self):
        with tempfile.TemporaryDirectory(prefix="v6-guard-") as tmp:
            (Path(tmp) / "clean.txt").write_text("hello\n", "utf-8")
            result = self._run(Path(tmp))
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
