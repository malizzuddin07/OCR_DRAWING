import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from golden_quality_gate import (  # noqa: E402
    comparable_metadata_value,
    invalid_duplicate_balloon_identities,
    run_gate,
)


def write_fa(path, drawing_number, value="25"):
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
    sheet.append([])
    sheet.append(["BALLOON NO", "SYMBOL", "VALUE", "-", "+", "MIN", "MAX", "REMARKS"])
    sheet.append(["1", "", value, "0.2", "0.2", "24.8", "25.2", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_characteristics(path, x=100):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_count": 1,
                "records": [
                    {
                        "Balloon No": "1",
                        "X": x,
                        "Y": 100,
                        "Width": 50,
                        "Height": 20,
                        "Balloon Size": "1",
                        "Balloon Rotation": "0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class GoldenQualityGateTests(unittest.TestCase):
    def test_declared_compound_subrows_may_share_one_balloon_identity(self):
        excel_rows = [
            {"BALLOON NO": "39", "SYMBOL": "CBORE", "VALUE": "11"},
            {"BALLOON NO": "39", "SYMBOL": "", "VALUE": "DEPTH 7"},
        ]
        characteristics = [
            {"Balloon No": "39", "Subrow Count": 2, "Subrow Index": 1},
            {"Balloon No": "39", "Subrow Count": 2, "Subrow Index": 2},
        ]
        self.assertEqual(
            invalid_duplicate_balloon_identities(excel_rows, characteristics), []
        )

    def test_undeclared_duplicate_balloon_identity_is_rejected(self):
        excel_rows = [
            {"BALLOON NO": "39", "VALUE": "11"},
            {"BALLOON NO": "39", "VALUE": "7"},
        ]
        self.assertEqual(
            invalid_duplicate_balloon_identities(excel_rows, []), ["39"]
        )

    def test_part_name_comparison_ignores_comma_spacing_only(self):
        self.assertEqual(
            comparable_metadata_value("part_name", "BRACKET, 65,LTP,450MM"),
            comparable_metadata_value("part_name", "BRACKET, 65, LTP, 450MM"),
        )
        self.assertNotEqual(
            comparable_metadata_value("part_name", "BRACKET, 65,LTP,450MM"),
            comparable_metadata_value("part_name", "BRACKET, 66,LTP,450MM"),
        )

    def build_fixture(self, root):
        golden = root / "golden"
        candidate = root / "candidate"
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
            write_characteristics(expected_characteristics)
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
            write_fa(candidate / drawing / "fa_inspection_report.xlsx", drawing)
            write_characteristics(candidate / drawing / "characteristics.json")
            (candidate / drawing / "ballooned.pdf").write_bytes(f"candidate-{number}".encode())
            (candidate / drawing / "balloon_layout.json").write_text(
                json.dumps({"record_count": 1, "records": [{"balloon_no": "1"}], "issues": []}), encoding="utf-8"
            )
        return golden, candidate

    def test_exact_candidate_passes_all_five_drawings(self):
        with tempfile.TemporaryDirectory() as folder:
            golden, candidate = self.build_fixture(Path(folder))
            result = run_gate(golden, candidate_root=candidate)
            self.assertEqual(result["status"], "PASSED")
            self.assertEqual(result["golden_count"], 5)

    def test_changed_value_rejects_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            golden, candidate = self.build_fixture(Path(folder))
            write_fa(candidate / "DRAWING-3" / "fa_inspection_report.xlsx", "DRAWING-3", value="99")
            result = run_gate(golden, candidate_root=candidate)
            self.assertEqual(result["status"], "REJECTED")
            drawing = next(item for item in result["drawings"] if item["drawing_number"] == "DRAWING-3")
            self.assertTrue(any(item["COLUMN"] == "VALUE" for item in drawing["differences"]))

    def test_layout_overlap_rejects_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            golden, candidate = self.build_fixture(Path(folder))
            path = candidate / "DRAWING-2" / "balloon_layout.json"
            path.write_text(json.dumps({"records": [], "issues": [{"type": "circle_circle_overlap"}]}), encoding="utf-8")
            result = run_gate(golden, candidate_root=candidate)
            self.assertEqual(result["status"], "REJECTED")

    def test_changed_characteristic_position_rejects_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            golden, candidate = self.build_fixture(Path(folder))
            write_characteristics(candidate / "DRAWING-4" / "characteristics.json", x=300)
            result = run_gate(golden, candidate_root=candidate)
            self.assertEqual(result["status"], "REJECTED")
            drawing = next(item for item in result["drawings"] if item["drawing_number"] == "DRAWING-4")
            self.assertTrue(any(item["type"] == "position_changed" for item in drawing["geometry_differences"]))


if __name__ == "__main__":
    unittest.main()
