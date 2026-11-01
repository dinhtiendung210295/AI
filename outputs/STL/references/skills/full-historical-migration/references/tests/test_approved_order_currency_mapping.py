import runpy
from pathlib import Path
import unittest

apply = runpy.run_path(str(Path(__file__).parents[1] / 'approved_order_currency_mapping.py'))['apply']


class CurrencyTests(unittest.TestCase):
    def test_approved_alias_overrides_exact_name_map_without_mutating_it(self):
        original = {'res.currency': {7: 6, 34: 34}}
        maps, proof = apply(original, [{'id': 7, 'name': 'CNH', 'rounding': 0.01}], [{'id': 7, 'name': 'CNY', 'rounding': 0.01}])
        self.assertEqual(7, maps['res.currency'][7])
        self.assertEqual(6, original['res.currency'][7])
        self.assertEqual(0, proof[0]['master_mutations'])

    def test_ambiguous_or_different_precision_refused(self):
        source = [{'id': 7, 'name': 'CNH', 'rounding': 0.01}]
        for targets in ([], [{'id': 7, 'name': 'CNY', 'rounding': 1}], [{'id': 7, 'name': 'CNY', 'rounding': 0.01}] * 2):
            with self.assertRaises(RuntimeError):
                apply({}, source, targets)
