# Right Now: Measure the Active Model and Test Candidates Safely

## Summary

The project can process drawings, use Roboflow, support manual corrections, and create corrected PDF/Excel files. Five checked golden drawings and a strict candidate gate now exist. However, it is **not safe to enable automatic retraining yet** because no newly trained candidate has completed the two-run promotion test.

Completed on 2026-07-21:

- Five approved golden drawings are installed.
- Downloading and approval are separate actions.
- Permanent approvals retain original and corrected data.
- `code/golden_quality_gate.py` checks all five drawings.
- `code/run_golden_suite.py` produces gate-ready model outputs.
- `code/model_registry.py` prevents failed candidates from replacing the active model.
- The golden file-integrity gate passes.

Current work order:

1. Record one fresh active-model baseline across all five drawings.
2. Keep collecting checked approval data.
3. Train one candidate from approved data only.
4. Process that candidate twice across all five drawings.
5. Promote it only when the strict gate passes and the user approves it.

Verified problems:

- The golden-test folders contain no approved Excel or PDF answer keys.
- 8 of 11 saved “learning” jobs contain zero actual corrections.
- Normal downloads are incorrectly treated as approved learning.
- Saved samples do not record the original value beside the corrected value.
- There is no automated test suite; `pytest` is not installed.
- The local YOLO dataset configuration points to an old `C:/Users/User/...` path.
- The main pipeline is a difficult-to-maintain 4,916-line file.
- Fresh processing can take approximately 29–41 minutes; cached processing still takes 7–8 minutes.
- The system has no model registry, candidate testing, promotion, or automatic rollback.

Therefore, the immediate priority is:

`Trusted approval data → Golden tests → Candidate evaluation → Automatic retraining`

## Implementation Changes

### 1. Create the first manufacturing QC baseline

Use these five existing drawings because they cover different dimensions, tolerances, GD&T, hole callouts, rotated text, and title-block formats:

1. `FAB-C-3020-175-6400 W3-C171246401-00.pdf`
2. `C3010-035-250F-01.pdf`
3. `C3020-060-201F-02.pdf`
4. `FAB-C-3060-010-9100 W3-C100807301-00.pdf`
5. `W3-C090489701-1A.pdf`

For each drawing, the user will check and approve:

- Every required characteristic
- Symbol and value
- Lower and upper tolerance
- Minimum and maximum
- Balloon number and sub-balloon number
- Missing, duplicate, or overlapping balloons
- Drawing metadata
- Final PDF and Excel

Store the checked results as immutable golden records. Preserve the existing successful detector-guided checkpoint as the rollback boundary.

### 2. Separate downloading from approval

Keep ordinary PDF and Excel downloads as download-only actions. They must stop writing learning data.

Add one explicit **Approve and Download** action:

- Require both corrected PDF and corrected Excel data.
- Show a confirmation that the complete drawing was checked.
- Create one approval record per drawing version.
- Prevent duplicate approval when the button is clicked twice.
- Record added, edited, deleted, moved, and unchanged characteristics separately.
- Store the original value and corrected value together.
- Save full drawing, crop, box coordinates, model version, metadata, and timestamp.
- Keep approval and training data outside the publicly mounted `/generated` folder.

New interfaces:

- `POST /api/jobs/{job_id}/approve`
- `GET /api/approvals/{approval_id}`
- `GET /api/training-jobs/{training_id}`
- `GET /api/models/status`

The approval response will contain the approval ID, PDF/Excel download links, training-job ID, and current learning status.

### 3. Build the automatic QC test system

Replace row-position-only comparison with stable characteristic matching using box location, type, symbol, value, and balloon identity.

Test every candidate against the newly approved drawing and all previous golden drawings.

Mandatory promotion gates:

- 100% required-characteristic recall
- No extra accepted characteristics
- Exact symbol, value, tolerance, minimum, and maximum values
- Exact approved title-block metadata
- No duplicate balloon identities
- No missing balloon identities
- No balloon-circle overlap
- No balloon covering another characteristic
- Identical results when the same model processes the same drawing twice
- No golden drawing performs worse than the active model
- At least one known error improves
- Processing time does not increase by more than 10%

Any failed gate rejects the candidate and leaves the active model unchanged.

### 4. Add controlled eager learning

The selected behaviour is:

- Training begins after **every approved drawing**.
- Training always uses the complete cumulative approved dataset, not only the latest drawing.
- Roboflow cloud custom training is used because no NVIDIA GPU was detected locally.
- Continue from the last accepted checkpoint.
- Do not use Roboflow Rapid because it is unsuitable for technical drawings and precision dimensions.

Route corrections into the correct learning group:

- Added/moved boxes → detector training
- Corrected text crops → OCR training dataset
- Corrected values and tolerances → parser regression cases
- Deleted false rows → negative detection examples
- Balloon movement/overlap corrections → placement tests

A training attempt may mark a component as “not enough new data” instead of producing an unsafe model.

### 5. Add candidate versioning and staged promotion

Maintain these model states:

- `active`
- `candidate`
- `rejected`
- `retired`
- `rollback`

For the first three successful candidate models:

1. Train automatically.
2. Test automatically.
3. Produce a simple QC report.
4. Require human approval before promotion.

After three successful human-approved promotions, candidates may be promoted automatically when every strict gate passes.

Always retain the previous active model. If the post-promotion smoke test fails, automatically restore it.

### 6. Stabilize the engineering foundation

Before enabling retraining:

- Add `pytest` and unit/integration tests.
- Pin dependency versions.
- Repair the YOLO dataset paths.
- Add durable job status so server restarts do not lose training state.
- Validate job IDs, PDF size, and file type.
- Restrict CORS and prevent public access to learning data.
- Extract approval, evaluation, and model-registry logic into separate modules.
- Avoid rewriting the existing OCR logic until the golden baseline measures its behaviour.

Performance optimisation comes after the QC gates. Start with the repeated OCR stages consuming the most time: full-page OCR, title-block OCR, stacked tolerances, detector-box OCR, and drill-callout OCR.

## Test Plan

- Unit tests for `195.5`, `25`, `0.5`, `DEPTH 6`, `DEPTH 15`, `4Mx6`, Japanese-text removal, asymmetric tolerances, GD&T, and basic dimensions.
- Verify normal downloads create no learning records.
- Verify Approve and Download creates exactly one immutable approval.
- Verify added, edited, deleted, and unchanged rows are classified correctly.
- Verify invalid or missing boxes are rejected from detector training.
- Verify training failure, Roboflow timeout, or internet failure never changes the active model.
- Run the five golden drawings twice and confirm identical results.
- Simulate one improved candidate and one regressed candidate.
- Confirm the improved candidate reaches manual review and the regressed candidate is rejected.
- Confirm rollback restores the previous model and output behaviour.

## Assumptions and Defaults

- The application remains a local single-company manufacturing tool.
- Roboflow training credits are available; every-drawing training may consume more credits.
- The five initial golden drawings must be manually verified before automatic training is enabled.
- Human review remains required before releasing an FA report for manufacturing, even after the learner becomes automatic.
- Existing detector/OCR improvements and the known-good rollback checkpoint are preserved.
