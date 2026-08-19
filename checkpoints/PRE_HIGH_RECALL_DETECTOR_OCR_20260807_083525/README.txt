Checkpoint purpose: preserve the OCR DRAWING files immediately before the optional high-recall detector crop-OCR candidate change.

Backed-up existing files:
- code\config.py
- code\auto_ballooning.py
- tests\test_measurement_regressions.py

New file introduced by the candidate (there is no previous copy):
- code\run_v3_v7_high_recall_single.ps1

The production default remains unchanged. The lower detector-to-OCR threshold is enabled only when YOLO_TEXT_OCR_MIN_DETECTOR_CONFIDENCE is explicitly set by a test runner.
