"""Fail-loud checks for the public R3 arithmetic verifier."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from verify_refinement_budgets import enclose


ROOT = Path(__file__).resolve().parent


class RefinementBudgetRefusalTests(unittest.TestCase):
    def test_tail_domain_is_enforced(self):
        for value in ('0', '-0.1', '1.2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                enclose(value, (3, 4, 2, 1))

    def test_optimized_python_is_rejected(self):
        result = subprocess.run(
            [sys.executable, '-O', str(ROOT / 'verify_refinement_budgets.py')],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Run without -O', result.stderr + result.stdout)

    def test_changed_reviewed_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            location = Path(temp)
            shutil.copy2(ROOT / 'verify_refinement_budgets.py', location)
            expected = json.loads((ROOT / 'expected_bound_enclosures.json').read_text())
            expected['results']['Ising'][0]['B'][1] = '0.5'
            (location / 'expected_bound_enclosures.json').write_text(
                json.dumps(expected), encoding='utf-8',
            )
            result = subprocess.run(
                [sys.executable, '-B', str(location / 'verify_refinement_budgets.py')],
                capture_output=True, text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('differ from the reviewed receipt', result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
