import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from run_golden_suite import run_suite  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_fa(path, drawing_number):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A4"] = "PART NUMBER"
    sheet["B4"] = f"PART-{drawing_number}"
    sheet["D4"] = "REVISION"
    sheet["E4"] = "01"
    sheet["F4"] = "MATERIAL"
    sheet["G4"] = "A5052"
    sheet["A5"] = "DRAWING NUMBER"
    sheet["B5"] = drawing_number
    sheet["D5"] = "PART NAME"
    sheet["E5"] = "TEST PART"
    sheet["A6"] = "BALLOON NO"
    sheet["B6"] = "SYMBOL"
    sheet["C6"] = "VALUE"
    sheet["D6"] = "-"
    sheet["E6"] = "+"
    sheet["F6"] = "MIN"
    sheet["G6"] = "MAX"
    sheet["H6"] = "REMARKS"
    sheet.append(["1", "", "25", "0.2", "0.2", "24.8", "25.2", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


class GoldenSuiteTests(unittest.TestCase):
    def build_golden(self, root):
        golden = root / "golden"
        for number in range(1, 6):
            drawing = f"DRAWING-{number}"
            source = golden / "drawings" / f"{drawing}.pdf"
            expected_pdf = golden / "expected_pdf" / f"{drawing}.pdf"
            expected_excel = golden / "expected_excel" / f"{drawing}.xlsx"
            expected_characteristics = golden / "expected_characteristics" / f"{drawing}.json"
            source.parent.mkdir(parents=True, exist_ok=True)
            expected_pdf.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f"source-{number}".encode())
            expected_pdf.write_bytes(f"pdf-{number}".encode())
            write_fa(expected_excel, drawing)
            expected_characteristics.parent.mkdir(parents=True, exist_ok=True)
            expected_characteristics.write_text(json.dumps({"records": [{"Balloon No": "1", "X": 100, "Y": 100, "Width": 50, "Height": 20}]}), encoding="utf-8")
            manifest = {
                "status": "approved",
                "golden_test_number": number,
                "drawing_number": drawing,
                "approved_characteristics": 1,
                "main_balloons": 1,
                "source_pdf": {"path": f"drawings/{drawing}.pdf", "sha256": digest(source)},
                "expected_pdf": {"path": f"expected_pdf/{drawing}.pdf", "sha256": digest(expected_pdf)},
                "expected_excel": {"path": f"expected_excel/{drawing}.xlsx", "sha256": digest(expected_excel)},
                "expected_characteristics": {"path": f"expected_characteristics/{drawing}.json", "sha256": digest(expected_characteristics)},
            }
            (golden / f"{drawing}_golden_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return golden

    def test_suite_processes_all_five_fresh_then_runs_strict_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            golden = self.build_golden(root)
            output = root / "candidate"
            calls = []

            def fake_process(source, drawing_output, use_cache):
                drawing = Path(source).stem
                calls.append((drawing, use_cache))
                write_fa(Path(drawing_output) / "fa_inspection_report.xlsx", drawing)
                (Path(drawing_output) / "characteristics.json").write_text(
                    json.dumps([{"Balloon No": "1", "X": 100, "Y": 100, "Width": 50, "Height": 20}]), encoding="utf-8"
                )
                (Path(drawing_output) / "ballooned.pdf").write_bytes(b"candidate")
                (Path(drawing_output) / "balloon_layout.json").write_text(
                    json.dumps({"record_count": 1, "records": [{"balloon_no": "1"}], "issues": []}), encoding="utf-8"
                )
                (Path(drawing_output) / "processing_timings.json").write_text(
                    json.dumps({"seconds": {"total": 1}}), encoding="utf-8"
                )
                return {
                    "rows": [{}],
                    "metadata": SimpleNamespace(
                        part_number=f"PART-{drawing}",
                        drawing_number=drawing,
                        revision="01",
                        material="A5052",
                        part_name="TEST PART",
                        general_tolerances={},
                    ),
                    "processing_timings": {"seconds": {"total": 1}},
                }

            with (
                patch("run_golden_suite.preload_required_ensemble"),
                patch("run_golden_suite.process_single_drawing", side_effect=fake_process),
            ):
                suite = run_suite(golden, output, use_cache=False)

            self.assertEqual(suite["status"], "passed")
            self.assertEqual(suite["gate_status"], "PASSED")
            self.assertEqual(len(calls), 5)
            self.assertTrue(all(use_cache is False for _drawing, use_cache in calls))
            self.assertTrue(Path(suite["gate_report_json"]).is_file())

    def test_promotion_requires_repeat_and_active_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            golden = self.build_golden(root)
            with (
                patch("run_golden_suite.preload_required_ensemble"),
                self.assertRaisesRegex(ValueError, "Promotion requires"),
            ):
                run_suite(golden, root / "candidate", promotion=True)

    def test_resume_reuses_verified_outputs_and_reprocesses_only_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            golden = self.build_golden(root)
            output = root / "candidate"

            def fake_process(source, drawing_output, use_cache):
                drawing = Path(source).stem
                write_fa(Path(drawing_output) / "fa_inspection_report.xlsx", drawing)
                (Path(drawing_output) / "characteristics.json").write_text(
                    json.dumps(
                        [{"Balloon No": "1", "X": 100, "Y": 100, "Width": 50, "Height": 20}]
                    ),
                    encoding="utf-8",
                )
                (Path(drawing_output) / "ballooned.pdf").write_bytes(b"candidate")
                (Path(drawing_output) / "balloon_layout.json").write_text(
                    json.dumps(
                        {
                            "record_count": 1,
                            "records": [{"balloon_no": "1"}],
                            "issues": [],
                        }
                    ),
                    encoding="utf-8",
                )
                (Path(drawing_output) / "processing_timings.json").write_text(
                    json.dumps({"seconds": {"total": 1}}),
                    encoding="utf-8",
                )
                return {
                    "rows": [{}],
                    "metadata": SimpleNamespace(
                        part_number=f"PART-{drawing}",
                        drawing_number=drawing,
                        revision="01",
                        material="A5052",
                        part_name="TEST PART",
                        general_tolerances={},
                    ),
                    "processing_timings": {"seconds": {"total": 1}},
                }

            with (
                patch("run_golden_suite.preload_required_ensemble"),
                patch("run_golden_suite.process_single_drawing", side_effect=fake_process),
            ):
                run_suite(golden, output, use_cache=False)

            state_path = output / "suite_run.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "running"
            state["drawings"] = state["drawings"][:4]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            incomplete = output / "DRAWING-5"
            for artifact in incomplete.iterdir():
                artifact.unlink()
            (incomplete / "partial.tmp").write_text("interrupted", encoding="utf-8")

            resumed_calls = []

            def resumed_process(source, drawing_output, use_cache):
                resumed_calls.append(Path(source).stem)
                return fake_process(source, drawing_output, use_cache)

            with (
                patch("run_golden_suite.preload_required_ensemble"),
                patch(
                    "run_golden_suite.process_single_drawing",
                    side_effect=resumed_process,
                ),
            ):
                suite = run_suite(golden, output, use_cache=False, resume=True)

            self.assertEqual(resumed_calls, ["DRAWING-5"])
            self.assertEqual(suite["status"], "passed")
            backups = list((output / "interrupted_backups").glob("DRAWING-5_*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "partial.tmp").is_file())


if __name__ == "__main__":
    unittest.main()
