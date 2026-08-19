Checkpoint purpose: preserve OCR DRAWING immediately before the second high-recall extraction candidate.

Backed-up files:
- code\config.py
- code\auto_ballooning.py
- code\run_v3_v7_high_recall_single.ps1
- tests\test_measurement_regressions.py

Candidate changes:
- configurable lower GD&T crop-OCR threshold used only by the candidate runner
- detector OCR edge-mark cleanup
- validated single-digit preservation
- detector-versus-page OCR conflict handling
- separate geometry for compound counterbore and depth values
- collision handling for adjacent padded boxes

Production model selection remains unchanged until golden validation passes.
