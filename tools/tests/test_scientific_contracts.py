"""Seed representative scientific-contract violations without changing baseline/."""
import copy
import types
import unittest
from unittest.mock import patch

from tools import verify_scientific_contracts as contracts


class ScientificContractRefusalTests(unittest.TestCase):
    def test_analytic_closed_moment_violation_is_refused(self):
        actual = contracts.renderer()
        changed = types.SimpleNamespace(**vars(actual))
        changed.channel_weights = lambda *args: 1.01*actual.channel_weights(*args)
        with patch.object(contracts, 'renderer', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'Fig1 TFIM P2'):
                contracts.analytic_contracts()

    def test_potts_top_ten_boundary_violation_is_refused(self):
        original = contracts.read_json(
            contracts.BASELINE/'data/potts-derived/projector-response-enclosures.json')
        changed = copy.deepcopy(original)
        changed['L14_ranks']['rows'][9]['projector_weight_interval'][0] = 0.0
        with self.assertRaisesRegex(ValueError, 'first ten protected'):
            contracts.potts_rank_contract(changed)

    def test_potts_rank_eleven_upgrade_is_refused(self):
        original = contracts.read_json(
            contracts.BASELINE/'data/potts-derived/projector-response-enclosures.json')
        changed = copy.deepcopy(original)
        changed['L14_ranks']['rows'][10]['projector_weight_interval'][0] = 0.01
        with self.assertRaisesRegex(ValueError, 'rank 11 is not upgraded'):
            contracts.potts_rank_contract(changed)

    def test_nnn_prg_residual_violation_is_refused(self):
        config = contracts.read_json(contracts.BASELINE/
            'producers/0.5.1.dev0/src/cc_repro/_resources/original/repro/config/'
            'nnn_tfim_expensive_reproduction.json')
        prg = contracts.read_csv(contracts.DATA/'nnn_tfim_prg_solver_diagnostics.csv')
        bench = contracts.read_csv(contracts.DATA/'interacting_benchmarks.csv')
        prg[0]['scaled_gap_residual'] = '1e-5'
        with self.assertRaisesRegex(ValueError, 'NNN PRG residual'):
            contracts.nnn_record_contract(config, prg, bench)

    def test_nnn_missing_pair_is_refused(self):
        config = contracts.read_json(contracts.BASELINE/
            'producers/0.5.1.dev0/src/cc_repro/_resources/original/repro/config/'
            'nnn_tfim_expensive_reproduction.json')
        prg = contracts.read_csv(contracts.DATA/'nnn_tfim_prg_solver_diagnostics.csv')
        bench = contracts.read_csv(contracts.DATA/'interacting_benchmarks.csv')
        with self.assertRaisesRegex(ValueError, 'complete J2/L inventory'):
            contracts.nnn_record_contract(config, prg[:-1], bench)


if __name__ == '__main__':
    unittest.main()
