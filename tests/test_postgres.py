"""Real PostgreSQL black-box scenarios for the compiled dbkit fixture.

Requires DBKIT_POSTGRES_DSN for an already-running dedicated test database. This
harness never resets or removes data; tests use unique table names and the
Compose-backed tests/run_tests.sh owns bind-directory reset and service cleanup.
"""
from pathlib import Path
import os
import subprocess
import sys
import unittest

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


def diagnostics(result):
    return f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


COMPILER = compiler_argument()
DSN = os.environ.get("DBKIT_POSTGRES_DSN")


class PostgresIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DSN:
            raise RuntimeError("DBKIT_POSTGRES_DSN is required; this harness does not reset PostgreSQL data")
        if not COMPILER.is_file():
            raise RuntimeError(f"Terrane compiler not found: {COMPILER}")
        built = subprocess.run([str(COMPILER), "build", str(APP)], cwd=ROOT,
                               capture_output=True, text=True, timeout=TIMEOUT)
        if built.returncode:
            raise RuntimeError("Terrane integration build failed\n" + diagnostics(built))
        candidates = [(Path(line.strip()) if Path(line.strip()).is_absolute()
                       else ROOT / line.strip()).resolve()
                      for line in built.stdout.splitlines() if line.strip()]
        candidates = [path for path in candidates if path.is_file()]
        if not candidates:
            raise RuntimeError("Build did not print an existing native artifact path\n" + diagnostics(built))
        cls.executable = candidates[-1]

    def run_app(self, mode):
        result = subprocess.run([str(self.executable), mode, DSN], capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, diagnostics(result))
        return result.stdout.splitlines()

    def test_postgres_values_and_bindings(self):
        self.assertEqual(self.run_app("postgres-values"), ["postgres-values=true"])

    def test_postgres_errors_recovery_and_metadata(self):
        self.assertEqual(self.run_app("postgres-errors"), ["postgres-errors=true"])

    def test_postgres_parameter_type_boundaries(self):
        self.assertEqual(self.run_app("postgres-parameter-types"), ["postgres-parameter-types=true"])

    def test_postgres_transactions_and_lifecycle(self):
        self.assertEqual(self.run_app("postgres-transactions"), ["postgres-transactions=true"])

    def test_postgres_cancellation_and_busy_sibling(self):
        self.assertEqual(self.run_app("postgres-cancel"), ["postgres-cancel=true"])


if __name__ == "__main__":
    unittest.main()
