# Golden Gate Workflow

This is the safe workflow for testing a new OCR code change or model.

## What the gate checks

The gate checks all five approved drawings. It rejects a candidate when it:

- misses a characteristic;
- adds a false characteristic;
- changes a symbol, value, tolerance, minimum, maximum, or remark;
- changes approved title-block information;
- duplicates or loses a balloon number;
- creates a balloon overlap;
- gives a different result on the second run;
- is worse than the active model; or
- takes more than 10% longer.

The gate never trains or activates a model by itself.

## 1. Check the five approved files

```powershell
C:\Users\izzuddin\python311\python.exe code\golden_quality_gate.py --verify-only
```

Expected result: `Status: PASSED`.

## 2. Record the current active-model baseline

Use a new folder. A complete fresh run is intentionally slow.

```powershell
C:\Users\izzuddin\python311\python.exe code\run_golden_suite.py `
  --output-root golden_tests\runs\active_baseline
```

## 3. Run a candidate twice

Set the candidate model, then create two fresh runs:

```powershell
$env:ROBOFLOW_EXPECTED_MODEL_ID="your-candidate-model-id"

C:\Users\izzuddin\python311\python.exe code\run_golden_suite.py `
  --output-root golden_tests\runs\candidate_run_1

C:\Users\izzuddin\python311\python.exe code\run_golden_suite.py `
  --output-root golden_tests\runs\candidate_run_2
```

Do not use `--use-cache` for a promotion decision.

## 4. Run the strict promotion gate

```powershell
C:\Users\izzuddin\python311\python.exe code\golden_quality_gate.py `
  --candidate-id "your-candidate-model-id" `
  --candidate-root golden_tests\runs\candidate_run_1 `
  --repeat-root golden_tests\runs\candidate_run_2 `
  --baseline-root golden_tests\runs\active_baseline `
  --promotion `
  --report-dir golden_tests\comparison_reports\your-candidate-model-id
```

- `PASSED` means the candidate is safe for human review.
- `REJECTED` means the active model stays unchanged.

## 5. Register and approve a passing candidate

```powershell
C:\Users\izzuddin\python311\python.exe code\model_registry.py register `
  --candidate-id "your-candidate-model-id"

C:\Users\izzuddin\python311\python.exe code\model_registry.py promote `
  --candidate-id "your-candidate-model-id" `
  --report golden_tests\comparison_reports\your-candidate-model-id\golden_gate_report.json `
  --human-approved
```

The first three successful candidates always require `--human-approved`.
The previous active model is kept as the rollback model.
