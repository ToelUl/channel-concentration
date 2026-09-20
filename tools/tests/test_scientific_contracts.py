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

    def test_fig2_absolute_scaling_drift_is_refused(self):
        actual = contracts.renderer()
        changed = types.SimpleNamespace(**vars(actual))
        original = actual.KF_point

        def drift(h, gamma, tangent, size):
            offset = {512: 0.1, 2048: 0.01}.get(size, 0.0)
            return original(h, gamma, tangent, size) + offset

        changed.KF_point = drift
        with patch.object(contracts, 'renderer', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'Fig2 L=2048 absolute'):
                contracts.analytic_contracts()

    def test_fig3_field_absolute_scaling_drift_is_refused(self):
        actual = contracts.renderer()
        changed = types.SimpleNamespace(**vars(actual))
        original = actual.KF_point

        def drift(h, gamma, tangent, size):
            offset = ({4096: 0.01, 16384: 0.00001}.get(size, 0.0)
                      if tangent == (1.0, 0.0) else 0.0)
            return original(h, gamma, tangent, size) + offset

        changed.KF_point = drift
        with patch.object(contracts, 'renderer', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'Fig3 L=16384 field absolute'):
                contracts.analytic_contracts()

    def test_fig3_anisotropy_absolute_scaling_drift_is_refused(self):
        actual = contracts.renderer()
        changed = types.SimpleNamespace(**vars(actual))
        original = actual.KF_point

        def drift(h, gamma, tangent, size):
            offset = ({4096: 0.01, 16384: 0.001}.get(size, 0.0)
                      if tangent == (0.0, 1.0) else 0.0)
            return original(h, gamma, tangent, size) + offset

        changed.KF_point = drift
        with patch.object(contracts, 'renderer', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'Fig3 L=16384 anisotropy absolute'):
                contracts.analytic_contracts()

    def test_fig3_singular_field_endpoint_is_refused(self):
        actual = contracts.renderer()
        changed = types.SimpleNamespace(**vars(actual))
        original = actual.channel_weights

        def false_endpoint(h, gamma, momenta, yh, yg):
            result = original(h, gamma, momenta, yh, yg)
            return result + 1e-6 if (h, gamma, yh, yg) == (1.0, 0.0, 1.0, 0.0) else result

        changed.channel_weights = false_endpoint
        with patch.object(contracts, 'renderer', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'exact Lifshitz field P2 vanishes'):
                contracts.analytic_contracts()

    def test_fig6_tangent_sign_violation_is_refused(self):
        actual = contracts.renderer()
        changed = types.SimpleNamespace(**vars(actual))
        original = actual.KF_point

        def broken_sign(h, gamma, tangent, size):
            result = original(h, gamma, tangent, size)
            return result + 0.01 if size == 128 and tangent[0] < 0 else result

        changed.KF_point = broken_sign
        with patch.object(contracts, 'renderer', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'Fig6 tangent scale/sign/period'):
                contracts.analytic_contracts()

    def test_s1_closed_sixth_moment_drift_is_refused(self):
        original = contracts.tfim_critical_closed_moments

        def altered(size):
            p2, p4, p6 = original(size)
            return p2, p4, 1.01*p6

        with patch.object(contracts, 'tfim_critical_closed_moments', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'S1 critical closed P6'):
                contracts.analytic_contracts()

    def test_failed_refinement_receipt_is_refused(self):
        failed = types.SimpleNamespace(returncode=1, stdout='', stderr='failed')
        with patch.object(contracts.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(ValueError, 'R3 conditional refinement'):
                contracts.refinement_contracts()

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
