# -*- coding: utf-8 -*-
"""PhasePredictor SAC 문단이 melting _classify 의 SAC 분기와 일치하는지."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.phase import PhasePredictor


class PhasePredictorSACTest(unittest.TestCase):
    def test_sac_alloy_gets_sac_paragraph(self):
        norm = {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}
        out = PhasePredictor().predict(norm)
        self.assertIn("SAC", out)

    def test_high_bi_snbi_no_sac_paragraph(self):
        norm = {"Sn": 74.0, "Ag": 1.0, "Bi": 25.0}
        out = PhasePredictor().predict(norm)
        self.assertNotIn("SAC", out)

    def test_snag_no_cu_no_sac_paragraph(self):
        norm = {"Sn": 96.5, "Ag": 3.5}
        out = PhasePredictor().predict(norm)
        self.assertNotIn("SAC", out)


if __name__ == "__main__":
    unittest.main()
