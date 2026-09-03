import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "db" / "seed" / "seed.py"


class DatastoreSeedContractTests(unittest.TestCase):
    def run_seed(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SEED_SCRIPT), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_d1_profile_is_canonical(self) -> None:
        result = self.run_seed("--describe-profile", "D1")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["seed"], 20260831)
        self.assertEqual(payload["profile"], "D1")
        self.assertEqual(payload["companies"], 10)
        self.assertEqual(payload["stations"], 50)
        self.assertEqual(payload["devices"], 500)
        self.assertEqual(payload["payments"], 100_000)

    def test_all_profile_sizes_are_frozen(self) -> None:
        result = self.run_seed("--describe-all")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["D1"]["devices"], 500)
        self.assertEqual(payload["D2"]["devices"], 5_000)
        self.assertEqual(payload["D3"]["devices"], 50_000)
        self.assertEqual(payload["D2"]["payments"], 1_000_000)
        self.assertEqual(payload["D3"]["payments"], 1_000_000)

    def test_schema_hash_is_stable_sha256(self) -> None:
        result = self.run_seed("--schema-hash")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = result.stdout.strip()
        self.assertEqual(len(value), 64)
        int(value, 16)


if __name__ == "__main__":
    unittest.main()
