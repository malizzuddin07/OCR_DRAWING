import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webapp import server  # noqa: E402


class JsonRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


class ApprovalEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.jobs = self.root / "generated" / "jobs"
        self.snapshots = self.root / "private" / "job_snapshots"
        self.approvals = self.root / "private" / "approvals"
        self.golden = self.root / "golden_tests"
        self.jobs.mkdir(parents=True)
        self.snapshots.mkdir(parents=True)
        self.approvals.mkdir(parents=True)
        self.golden.mkdir(parents=True)
        self.job_id = "a" * 12
        self.job = self.jobs / self.job_id
        (self.job / "upload").mkdir(parents=True)
        (self.job / "upload" / "drawing.pdf").write_bytes(b"test drawing")
        cv2.imwrite(str(self.job / "original.png"), np.full((100, 100, 3), 255, dtype=np.uint8))
        self.original_items = [
            {"Balloon No": "1", "Dimension": "95.5", "X": 10, "Y": 10, "Width": 20, "Height": 10}
        ]
        (self.snapshots / f"{self.job_id}.json").write_text(
            json.dumps(
                {
                    "job_id": self.job_id,
                    "source_filename": "drawing.pdf",
                    "source_sha256": "",
                    "original_items": self.original_items,
                    "original_metadata": {},
                    "detector_diagnostics": {"active_model": "test-model"},
                }
            ),
            encoding="utf-8",
        )
        self.patches = [
            patch.object(server, "JOBS_DIR", self.jobs),
            patch.object(server, "JOB_SNAPSHOTS_DIR", self.snapshots),
            patch.object(server, "APPROVALS_DIR", self.approvals),
            patch.object(server, "GOLDEN_TESTS_DIR", self.golden),
            patch.object(server, "render_corrected_outputs", side_effect=self.fake_render),
            patch.object(server, "save_fa_workbook", side_effect=self.fake_excel),
        ]
        for current_patch in self.patches:
            current_patch.start()

    def tearDown(self):
        for current_patch in reversed(self.patches):
            current_patch.stop()
        self.temporary.cleanup()

    def fake_render(self, job_id, _items, _metadata, include_pdf=True):
        job = self.jobs / job_id
        image = job / "ballooned_corrected.png"
        pdf = job / "ballooned_corrected.pdf"
        image.write_bytes(b"image")
        if include_pdf:
            pdf.write_bytes(b"pdf")
        return image, pdf

    @staticmethod
    def fake_excel(_items, output_path, metadata=None):
        del metadata
        Path(output_path).write_bytes(b"excel")

    def approval_payload(self, value="195.5"):
        return {
            "confirmed_complete": True,
            "metadata": {"drawing_number": "TEST-001"},
            "items": [
                {"Balloon No": "1", "Dimension": value, "X": 10, "Y": 10, "Width": 20, "Height": 10}
            ],
        }

    def test_approval_is_private_immutable_and_idempotent(self):
        first = asyncio.run(server.approve_job(self.job_id, JsonRequest(self.approval_payload())))
        first_data = response_json(first)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first_data["duplicate"])
        approval_dir = self.approvals / first_data["approval_id"]
        self.assertTrue((approval_dir / "approval.json").exists())
        self.assertTrue((approval_dir / "approved_package.zip").exists())
        self.assertFalse((self.root / "generated" / "learning_samples").exists())

        duplicate = asyncio.run(server.approve_job(self.job_id, JsonRequest(self.approval_payload())))
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(response_json(duplicate)["duplicate"])

        changed = asyncio.run(server.approve_job(self.job_id, JsonRequest(self.approval_payload("195.6"))))
        changed_data = response_json(changed)
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed_data["approval_id"], first_data["approval_id"])
        self.assertEqual(changed_data["approval_revision"], 2)
        self.assertEqual(changed_data["supersedes_approval_id"], first_data["approval_id"])
        changed_record = server.load_approval_record(changed_data["approval_id"])
        self.assertEqual(changed_record["approval_revision"], 2)
        self.assertEqual(changed_record["supersedes_approval_id"], first_data["approval_id"])

    def test_approval_requires_explicit_complete_confirmation(self):
        payload = self.approval_payload()
        payload["confirmed_complete"] = False
        response = asyncio.run(server.approve_job(self.job_id, JsonRequest(payload)))
        self.assertEqual(response.status_code, 400)

    def test_approval_is_blocked_when_balloon_frames_overlap(self):
        payload = self.approval_payload()
        payload["items"].append(
            {"Balloon No": "2", "Dimension": "25", "X": 10, "Y": 10, "Width": 20, "Height": 10}
        )
        response = asyncio.run(server.approve_job(self.job_id, JsonRequest(payload)))
        data = response_json(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["status"], "needs_review")
        self.assertTrue(any(issue["type"] == "balloon_layout_overlap" for issue in data["quality"]["issues"]))

    def test_known_golden_drawing_must_match_approved_excel_before_approval(self):
        source = self.job / "upload" / "drawing.pdf"
        source_hash = server.file_sha256(source).upper()
        expected_excel = self.golden / "expected_excel" / "TEST-001.xlsx"
        expected_excel.parent.mkdir(parents=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet["A6"] = "BALLOON NO"
        sheet["B6"] = "SYMBOL"
        sheet["C6"] = "VALUE"
        sheet["D6"] = "-"
        sheet["E6"] = "+"
        sheet["F6"] = "MIN"
        sheet["G6"] = "MAX"
        sheet["H6"] = "REMARKS"
        sheet.append(["1", "", "200", "0.5", "0.5", "199.5", "200.5", ""])
        workbook.save(expected_excel)
        manifest = {
            "status": "approved",
            "drawing_number": "TEST-001",
            "main_balloons": 1,
            "source_pdf": {"sha256": source_hash},
            "expected_excel": {"path": "expected_excel/TEST-001.xlsx"},
        }
        (self.golden / "TEST-001_golden_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        response = asyncio.run(server.approve_job(self.job_id, JsonRequest(self.approval_payload("195.5"))))
        data = response_json(response)
        self.assertEqual(response.status_code, 409)
        mismatch = next(issue for issue in data["quality"]["issues"] if issue["type"] == "golden_output_mismatch")
        self.assertGreater(mismatch["difference_count"], 0)

    def test_invalid_job_id_is_rejected(self):
        response = asyncio.run(server.approve_job("../../bad", JsonRequest(self.approval_payload())))
        self.assertEqual(response.status_code, 400)

    def test_normal_downloads_create_no_learning_or_approval_record(self):
        payload = self.approval_payload()
        payload["job_id"] = self.job_id
        excel_response = asyncio.run(server.export_to_excel(JsonRequest(payload)))
        pdf_response = asyncio.run(server.export_corrected_pdf(JsonRequest(payload)))

        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(list(self.approvals.iterdir()), [])
        self.assertFalse((self.root / "generated" / "learning_samples").exists())

    def test_corrected_items_normalise_depth_spacing_before_approval(self):
        rows = server.normalise_corrected_items(
            [{"Balloon No": "1", "Dimension": "DEPTH6", "Specification": "DEPTH6"}]
        )
        self.assertEqual(rows[0]["Dimension"], "DEPTH 6")
        self.assertEqual(rows[0]["Specification"], "DEPTH 6")

    def test_corrected_depth_replaces_stale_ocr_nominal_and_limits(self):
        rows = server.normalise_corrected_items(
            [
                {
                    "Balloon No": "1",
                    "Dimension": "DEPTH 15",
                    "Nominal": "1",
                    "Tolerance -": "0.1",
                    "Tolerance +": "0.1",
                    "MIN": "0.9",
                    "MAX": "1.1",
                },
                {"Balloon No": "2", "Dimension": "DEPTH 12", "Nominal": ""},
            ]
        )
        self.assertEqual(rows[0]["Nominal"], "15")
        self.assertEqual(rows[0]["Tolerance -"], "0.2")
        self.assertEqual(rows[0]["Tolerance +"], "0.2")
        self.assertEqual(rows[0]["MIN"], "14.8")
        self.assertEqual(rows[0]["MAX"], "15.2")
        self.assertEqual(rows[1]["Nominal"], "12")
        self.assertEqual(rows[1]["MIN"], "11.8")
        self.assertEqual(rows[1]["MAX"], "12.2")

    def test_manual_multiplier_crop_expands_into_subrows(self):
        rows = server.expand_manual_crop_row(
            {
                "Specification": "4X C1",
                "Measurement Type": "chamfer",
                "Symbol": "4XC",
                "Dimension": "1",
                "X": 10,
                "Y": 20,
                "Width": 30,
                "Height": 12,
            }
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["Multiplier Index"] for row in rows], [1, 2, 3, 4])
        self.assertTrue(all(row["Multiplier Count"] == 4 for row in rows))
        self.assertTrue(all(row["Report Symbol"] == "C" for row in rows))
        self.assertTrue(all(row["Dimension"] == "1" for row in rows))
        self.assertTrue(all(row["Nominal"] == "1" for row in rows))
        self.assertTrue(all((row["X"], row["Y"], row["Width"], row["Height"]) == (10, 20, 30, 12) for row in rows))

    def test_manual_diagonal_multiplier_ligature_is_normalised(self):
        self.assertEqual(server.normalise_manual_recognition_text("4\u80431"), "4XC1")
        self.assertEqual(server.normalise_manual_recognition_text("4 X C1"), "4XC1")
        # Do not rewrite unrelated Japanese/Unicode OCR text.
        self.assertEqual(server.normalise_manual_recognition_text("DEPTH\u6df16"), "DEPTH\u6df16")

    def test_manual_ocr_rejects_punctuation_only_noise(self):
        self.assertFalse(server.is_meaningful_manual_ocr_text(")"))
        self.assertFalse(server.is_meaningful_manual_ocr_text("+-"))
        self.assertTrue(server.is_meaningful_manual_ocr_text("25"))
        self.assertTrue(server.is_meaningful_manual_ocr_text("C1"))

    def test_dominant_diagonal_angle_finds_45_degree_callout(self):
        image = np.full((200, 200, 3), 255, dtype=np.uint8)
        cv2.line(image, (20, 180), (180, 20), (0, 0, 0), 3)
        angle = server.dominant_diagonal_angle(image)
        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, -45.0, delta=2.0)

    def test_manual_multiplier_subrows_are_normalised_before_approval(self):
        rows = server.normalise_corrected_items(
            [
                {
                    "Balloon No": "5.1",
                    "Display Balloon No": "5",
                    "Specification": "4X C1",
                    "Report Symbol": "4XC",
                    "Symbol": "4XC",
                    "Dimension": "1",
                    "Subrow Count": 4,
                    "Subrow Index": 1,
                },
                *[
                    {
                        "Balloon No": f"5.{index}",
                        "Display Balloon No": "5",
                        "Specification": "",
                        "Report Symbol": "C",
                        "Symbol": "C",
                        "Dimension": "1",
                        "Multiplier Count": 1,
                        "Subrow Count": 4,
                        "Subrow Index": index,
                    }
                    for index in range(2, 5)
                ],
            ]
        )

        self.assertEqual([row["Balloon No"] for row in rows], ["5.1", "5.2", "5.3", "5.4"])
        self.assertTrue(all(row["Report Symbol"] == "C" for row in rows))
        self.assertTrue(all(row["Dimension"] == "1" for row in rows))
        self.assertEqual([row["Multiplier Index"] for row in rows], [1, 2, 3, 4])
        self.assertTrue(all(row["Multiplier Count"] == 4 for row in rows))
        self.assertTrue(all(row["Specification"] == "4X C1" for row in rows))

    def test_multiplier_normalisation_replaces_stale_specification(self):
        rows = server.normalise_corrected_items(
            [
                {
                    "Balloon No": "5.1",
                    "Specification": "7",
                    "Report Symbol": "4XC",
                    "Symbol": "4XC",
                    "Dimension": "1",
                    "Subrow Count": 4,
                },
                *[
                    {
                        "Balloon No": f"5.{index}",
                        "Report Symbol": "C",
                        "Symbol": "C",
                        "Dimension": "1",
                        "Subrow Count": 4,
                    }
                    for index in range(2, 5)
                ],
            ]
        )

        self.assertTrue(all(row["Specification"] == "4X C1" for row in rows))

    def test_manual_counterbore_crop_expands_diameter_and_depth(self):
        rows = server.expand_manual_crop_row(
            {
                "Specification": "CBORE 9.5 DEPTH 15",
                "Measurement Type": "hole_callout",
                "X": 5,
                "Y": 6,
                "Width": 70,
                "Height": 20,
            }
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Report Symbol"], "CBORE")
        self.assertEqual(rows[0]["Dimension"], "9.5")
        self.assertEqual(rows[1]["Report Symbol"], "")
        self.assertEqual(rows[1]["Dimension"], "DEPTH 15")
        self.assertEqual([row["Subrow Index"] for row in rows], [1, 2])
        self.assertTrue(all(row["Subrow Count"] == 2 for row in rows))

    def test_compound_rows_receive_unique_decimal_balloon_numbers(self):
        rows = server.normalise_corrected_items(
            [
                {
                    "Balloon No": "11",
                    "Dimension": "9.5",
                    "Report Symbol": "CBORE",
                    "Subrow Count": 2,
                    "X": 5,
                    "Y": 6,
                    "Width": 70,
                    "Height": 20,
                },
                {
                    "Balloon No": "11",
                    "Dimension": "DEPTH 15",
                    "Subrow Count": 2,
                    "X": 5,
                    "Y": 6,
                    "Width": 70,
                    "Height": 20,
                },
            ]
        )
        self.assertEqual([row["Balloon No"] for row in rows], ["11.1", "11.2"])
        self.assertEqual([row["Display Balloon No"] for row in rows], ["11", "11"])

    def test_model_status_keeps_automatic_training_disabled(self):
        status = asyncio.run(server.model_status())
        self.assertEqual(status["status"], "success")
        self.assertFalse(status["training_enabled"])
        self.assertIn("active_model", status)


if __name__ == "__main__":
    unittest.main()
