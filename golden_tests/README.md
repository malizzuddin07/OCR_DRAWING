# Golden Tests

Use this folder to store verified correct results for drawings.

Purpose:
- Keep one trusted answer key per drawing.
- Compare new system output against the trusted answer key.
- Identify whether errors come from detection, OCR, parsing, validation, ballooning, or Excel export.

Folder usage:
- `drawings/`: copy the original PDF drawing here.
- `expected_excel/`: put the manually verified correct FA Excel here.
- `expected_pdf/`: put the manually verified correct ballooned PDF here.
- `expected_images/`: put the manually verified correct ballooned image here, if available.
- `expected_notes/`: write what was wrong and what the correct result should be.
- `current_outputs/`: copy new system outputs here when testing.
- `comparison_reports/`: generated comparison reports will go here later.

Recommended first drawing:
- `FAB-C-3020-175-6400 W3-C171246401-00.pdf`

Installed golden tests:
- Golden Test 1: `W3-C171246401-00` with 65 approved characteristics.
- Golden Test 2: `C3010-035-250F` with 29 approved characteristics.
- Golden Test 3: `W3-C111262801-2A` with 104 approved characteristics and 75 main balloons.
- Golden Test 4: `W3-C111265901-03` with 103 approved characteristics and 87 main balloons.
- Golden Test 5: `W3-C111266801-01` with 76 approved characteristics, 57 main balloons, and 76 approved crops.

Golden set status:
- Five drawings are now installed and approved.
- Use all five as the accuracy gate before accepting OCR, parser, detector, ballooning, or model changes.
- Run `python code\golden_quality_gate.py --verify-only` to verify all approved files and hashes.
- See `docs/GOLDEN_GATE_WORKFLOW.md` for the complete candidate test and promotion commands.
- The five-drawing integrity gate passed on 2026-07-21.
- Gate reports are saved under `comparison_reports/`.
- Full operator commands are documented in `../docs/GOLDEN_GATE_WORKFLOW.md`.

Approval workflow:
- Ordinary PDF and Excel downloads are not approvals and do not create learning data.
- Use `Approve & Download` only after checking the complete drawing.
- The approved ZIP contains the checked PDF, Excel, source drawing, approval record, and valid crops.
- Roboflow training remains disabled until the golden drawings pass the QC gates.

Important:
- Do not use system output as expected output until you manually verify it.
- Corrected Excel exported from the review app can become expected output only after you check it against the drawing.
- Corrected PDF/image exported from the review app can become expected output only after balloon positions are checked.
- Keep bad job outputs if they show useful failure evidence.
