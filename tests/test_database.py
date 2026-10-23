"""Black-box dbkit behavior using the native artifact built from integration/."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import sqlite3


PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
APP = PACKAGE / "tests" / "fixtures" / "database"
TIMEOUT = 600


def compiler_argument():
    if "--terrane" in sys.argv:
        index = sys.argv.index("--terrane")
        if index + 1 >= len(sys.argv):
            raise RuntimeError("--terrane requires a compiler path")
        path = Path(sys.argv[index + 1]).resolve()
        del sys.argv[index:index + 2]
        return path
    return Path(os.environ.get("TERRANE", ROOT / "target/release/terrane")).resolve()


COMPILER = compiler_argument()

def diagnostics(result):
    return f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


class DatabaseIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not COMPILER.is_file():
            raise RuntimeError(f"Terrane compiler not found: {COMPILER}")
        built = subprocess.run([str(COMPILER), "build", str(APP)], cwd=ROOT,
                               capture_output=True, text=True, timeout=TIMEOUT)
        if built.returncode:
            raise RuntimeError("Terrane integration build failed\n" + diagnostics(built))
        # Resolve a relative printed artifact path against the compiler's working directory.
        candidates = [(Path(line.strip()) if Path(line.strip()).is_absolute()
                       else ROOT / line.strip()).resolve()
                      for line in built.stdout.splitlines() if line.strip()]
        candidates = [path for path in candidates if path.is_file()]
        if not candidates:
            raise RuntimeError("Build did not print an existing native artifact path\n" + diagnostics(built))
        cls.executable = candidates[-1]

    def run_app(self, *args):
        result = subprocess.run([str(self.executable), *map(str, args)], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, diagnostics(result))
        return result.stdout.splitlines()

    def test_memory_database_and_public_api(self):
        output = self.run_app("memory")
        self.assertEqual(output, ["affected=1", "rebound=1", "first=safe",
                                  "second=x'); DROP TABLE items; --",
                                  "helper=2", "rollback=true"])

    def test_file_persistence_and_reopened_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db.sqlite"
            self.assertEqual(self.run_app("file", path), ["persisted=7"])
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute("SELECT value FROM persisted").fetchall(), [(7,)])

    def test_missing_bindings_and_native_failure_allow_reuse(self):
        self.assertEqual(self.run_app("errors"), [
            "missing-parameter", "unknown-parameter", "missing-parameter",
            "database:prepare", "multiple-statements", "parameter-style",
            "database:execute", "reuse=true",
        ])

    def test_values_nulls_and_column_boundaries(self):
        self.assertEqual(self.run_app("values"), [
            "-9223372036854775808", "9223372036854775807", "conversion",
            "ambiguous-column", "column-not-found", "column-not-found",
            "column-not-found", "values=true",
        ])

    def test_close_invalidation_buffering_and_transaction_errors(self):
        self.assertEqual(self.run_app("lifecycle"), [
            "database", "transaction-active", "no-transaction",
            "connection-closed", "buffered=true",
        ])

    def test_unavailable_unknown_and_invalid_configuration(self):
        self.assertEqual(self.run_app("drivers"), [
            "driver-unavailable", "driver-unavailable", "unknown-driver",
            "configuration",
        ])

    def test_abandoned_transaction_rolls_back_and_releases_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "abandoned.sqlite"
            self.assertEqual(self.run_app("abandon", path), ["abandoned=true"])
            with sqlite3.connect(path, timeout=1) as database:
                self.assertEqual(database.execute("SELECT value FROM abandoned").fetchall(), [])
                database.execute("INSERT INTO abandoned VALUES (1)")
                database.commit()
                self.assertEqual(database.execute("SELECT value FROM abandoned").fetchall(), [(1,)])


if __name__ == "__main__":
    unittest.main()
