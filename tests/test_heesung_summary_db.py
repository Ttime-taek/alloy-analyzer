# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from test7.analyzer import AlloyAnalyzer
from test7.solder_db import SOLDER_DB


def _find_by_name(name: str) -> dict:
    return next(e for e in SOLDER_DB if e["name"] == name)


class HeesungSummaryDbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = AlloyAnalyzer(SOLDER_DB)

    def test_new_heesung_rows_loaded(self):
        row = _find_by_name("Sn-0.5Cu-0.03Ni-0.015P")
        self.assertAlmostEqual(float(row["solidus"]), 227.0, places=3)
        self.assertAlmostEqual(float(row["liquidus"]), 231.0, places=3)
        self.assertAlmostEqual(float(row["density"]), 7.3, places=3)
        self.assertEqual(row.get("source"), "Heesung summary 2013-06-28")

        ge_row = _find_by_name("Sn-3.0Ag-0.5Cu-0.003Ni-0.0075Ge-0.0035P")
        self.assertAlmostEqual(float(ge_row["solidus"]), 217.0, places=3)
        self.assertAlmostEqual(float(ge_row["liquidus"]), 219.0, places=3)

    def test_duplicate_source_rows_collapsed_by_composition(self):
        hits = [e for e in SOLDER_DB if e["name"] == "Sn-0.5Cu-0.03Ni-0.015P"]
        self.assertEqual(len(hits), 1)

        hits = [e for e in SOLDER_DB if e["name"] == "Sn-0.3Cu-0.03Ni-0.015P"]
        self.assertEqual(len(hits), 1)

    def test_analyzer_uses_exact_melting_for_new_row(self):
        comp = {"Sn": 96.4895, "Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}
        out = self.analyzer.analyze_all(comp)
        self.assertEqual(out["best"]["name"], "Sn-3.0Ag-0.5Cu-0.003Ni-0.0075Ge")
        self.assertAlmostEqual(float(out["solidus"]), 217.0, places=3)
        self.assertAlmostEqual(float(out["liquidus"]), 219.0, places=3)

    def test_analyzer_exposes_density_for_exact_match(self):
        comp = {"Sn": 99.455, "Cu": 0.5, "Ni": 0.03, "P": 0.015}
        out = self.analyzer.analyze_all(comp)
        self.assertEqual(out["best"]["name"], "Sn-0.5Cu-0.03Ni-0.015P")
        self.assertAlmostEqual(float(out["props"]["density"]), 7.3, places=3)

    def test_sb_rows_updated_with_requested_melting_and_density(self):
        row_5 = _find_by_name("Sn-5Sb")
        self.assertAlmostEqual(float(row_5["solidus"]), 238.0, places=3)
        self.assertAlmostEqual(float(row_5["liquidus"]), 242.0, places=3)
        self.assertAlmostEqual(float(row_5["density"]), 7.3, places=3)

        row_10 = _find_by_name("Sn-10Sb")
        self.assertAlmostEqual(float(row_10["solidus"]), 242.0, places=3)
        self.assertAlmostEqual(float(row_10["liquidus"]), 249.25, places=3)
        self.assertAlmostEqual(float(row_10["density"]), 7.3, places=3)

    def test_analyzer_uses_updated_sb_exact_match(self):
        out_5 = self.analyzer.analyze_all({"Sn": 95.0, "Sb": 5.0})
        self.assertEqual(out_5["best"]["name"], "Sn-5Sb")
        self.assertAlmostEqual(float(out_5["solidus"]), 238.0, places=3)
        self.assertAlmostEqual(float(out_5["liquidus"]), 242.0, places=3)
        self.assertAlmostEqual(float(out_5["props"]["density"]), 7.3, places=3)

        out_10 = self.analyzer.analyze_all({"Sn": 90.0, "Sb": 10.0})
        self.assertEqual(out_10["best"]["name"], "Sn-10Sb")
        self.assertAlmostEqual(float(out_10["solidus"]), 242.0, places=3)
        self.assertAlmostEqual(float(out_10["liquidus"]), 249.2, places=3)
        self.assertAlmostEqual(float(out_10["props"]["density"]), 7.3, places=3)


if __name__ == "__main__":
    unittest.main()
