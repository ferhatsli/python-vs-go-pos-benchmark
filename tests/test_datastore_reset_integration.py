import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "db" / "seed" / "seed.py"
RESET = ROOT / "db" / "reset" / "reset.py"


@unittest.skipUnless(os.environ.get("BENCH_INTEGRATION") == "1", "set BENCH_INTEGRATION=1")
class DatastoreResetIntegrationTests(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

    def json_cmd(self, *args: str) -> dict:
        result = self.run_cmd(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_d1_reset_restores_identical_fingerprint(self) -> None:
        seeded = self.json_cmd("python3", str(SEED), "--profile", "D1")
        self.assertEqual(seeded["row_counts"]["devices"], 500)
        self.assertEqual(seeded["row_counts"]["payments"], 100_000)

        mutation = self.run_cmd(
            "docker", "compose", "exec", "-T", "postgres", "psql",
            "-U", "benchmark", "-d", "pos_benchmark", "-v", "ON_ERROR_STOP=1",
            "-c", "DELETE FROM payment_transactions WHERE id = (SELECT max(id) FROM payment_transactions);",
        )
        self.assertEqual(mutation.returncode, 0, mutation.stderr)

        mutated = self.json_cmd("python3", str(SEED), "--profile", "D1", "--fingerprint-only")
        self.assertNotEqual(mutated["stable_keys_sha256"], seeded["stable_keys_sha256"])
        self.assertEqual(mutated["row_counts"]["payments"], 99_999)

        reset = self.json_cmd("python3", str(RESET), "--profile", "D1")
        self.assertEqual(reset["stable_keys_sha256"], seeded["stable_keys_sha256"])
        self.assertEqual(reset["schema_hash"], seeded["schema_hash"])
        self.assertEqual(reset["row_counts"], seeded["row_counts"])


if __name__ == "__main__":
    unittest.main()
