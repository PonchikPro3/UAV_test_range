import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("procedural", ROOT / "analytics/procedural.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
LIMITS = json.loads((ROOT / "data/limits.json").read_text())
HEADER = ",".join(module.COLUMNS) + "\n"


class AnalyticsChecks(unittest.TestCase):
    def analyze(self, rows, limits=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "flight.csv"
            path.write_text(HEADER + rows, encoding="utf-8")
            return module.analyze_telemetry(path, LIMITS if limits is None else limits)

    def test_demo(self):
        result = module.analyze_telemetry(ROOT / "data/telemetry.csv", LIMITS)
        self.assertEqual((result["samples"], result["violation_count"], result["result"]), (5, 4, "FAILED"))
        self.assertEqual({v["code"] for v in result["violations"]},
                         {"OUTSIDE_ZONE", "HEIGHT_LIMIT", "SPEED_LIMIT", "LOW_BATTERY"})
        self.assertEqual(result["violations"][0]["actual_value"], 1)
        self.assertEqual(result["violations"][0]["seq_no"], 3)
        self.assertEqual(result["telemetry_sha256"],
                         hashlib.sha256((ROOT / "data/telemetry.csv").read_bytes()).hexdigest())

    def test_equal_thresholds_pass(self):
        self.assertEqual(self.analyze("0,100,100,120,15,20\n")["result"], "PASSED")

    def test_lower_bound_passes(self):
        self.assertEqual(self.analyze("0,0,0,0,0,100\n")["result"], "PASSED")

    def test_bad_rows_rejected(self):
        cases = ["", "0,0,0,nan,0,100\n", "0,0,0,inf,0,100\n", "0,0,0,-1,0,100\n",
                 "0,0,0,1,-1,100\n", "0,0,0,1,1,101\n", "0,0,0,1,1,-1\n",
                 "-1,0,0,1,1,50\n", "0,0,0,a,1,50\n", "0,0,0,1,1\n",
                 "0,0,0,1,1,50,extra\n", "0,0,0,1,,50\n",
                 "1,0,0,1,1,50\n1,0,0,1,1,50\n", "2,0,0,1,1,50\n1,0,0,1,1,50\n"]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.analyze(rows)

    def test_bad_limits_rejected(self):
        for name, value in [("x_max", 0), ("y_max", -1), ("height_max", -1),
                            ("speed_max", -1), ("battery_min", 101), ("battery_min", True), ("x_min", float("nan"))]:
            limits = dict(LIMITS, **{name: value})
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                self.analyze("0,0,0,0,0,100\n", limits)
        for limits in [None, [], {"x_min": "0"}, dict(LIMITS, x_min=None)]:
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                # Call directly because analyze(None) means use defaults in this helper.
                module.validate_limits(limits)

    def test_bad_header_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text("x,y\n1,2\n")
            with self.assertRaises(ValueError):
                module.analyze_telemetry(path, LIMITS)

    def test_bom_and_crlf(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "flight.csv"
            content = (HEADER + "0,0,0,0,0,100\n").replace("\n", "\r\n").encode("utf-8-sig")
            path.write_bytes(content)
            result = module.analyze_telemetry(path, LIMITS)
            self.assertEqual(result["telemetry_sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(result["result"], "PASSED")

    def test_protocol(self):
        analysis = self.analyze("0,0,0,0,0,100\n")
        protocol = module.build_protocol("T-DEMO", analysis)
        self.assertEqual(protocol["status"], "DRAFT")
        self.assertEqual(protocol["telemetry_sha256"], analysis["telemetry_sha256"])
        self.assertIn("пройдено", module.render_text(protocol))
        json.dumps(protocol, allow_nan=False)

    def test_bad_protocol_id(self):
        with self.assertRaises(ValueError):
            module.build_protocol("bad\nID", {})


if __name__ == "__main__":
    unittest.main()
