# Candidate V9 Fair Evaluation

Date: 2026-08-17

## Decision

Candidate V9 is **not approved for production** and does not replace any active model.

V9 is kept only as an isolated experimental high-recall candidate. It finds more possible regions, but its low precision produces too many false detections for automatic ballooning.

## Verified input

- Return package: `RETURN_TO_OCR_LAPTOP_V9_20260817_082247.zip`
- Verified SHA-256: `D6B2C22A21B03B032198EE20A9E7225CF779A236932CE8523E9367A38CF65B74`
- Required weights and held-out-test outputs were present.
- All candidates were evaluated on the same protected test split with the same settings: image size 1280, batch 1, confidence 0.001, IoU 0.7, CPU.

## Fair comparison

| Model | Precision | Recall | F1 | mAP50 | mAP50-95 | Result |
|---|---:|---:|---:|---:|---:|---|
| V3 | 0.6654 | 0.4227 | 0.5170 | 0.5002 | **0.3421** | Best precise-box model |
| V7 | 0.5975 | 0.4904 | 0.5387 | 0.5463 | 0.3358 | Strong balanced model |
| V8 | 0.6166 | 0.4813 | **0.5406** | **0.5542** | 0.3346 | Best overall balance |
| V1 | 0.4752 | 0.5506 | 0.5102 | 0.4690 | 0.3210 | Older high-recall model |
| V9 | 0.3132 | **0.5905** | 0.4093 | 0.4232 | 0.2176 | Rejected as general model |

## Important V9 class results

- GD&T frame mAP50: 0.9425 — strong.
- Dimension mAP50: 0.5825 — useful.
- Radius mAP50: 0.4616 — useful.
- Hole callout mAP50: 0.0206 — unacceptable.
- Diameter mAP50: 0.2908 — much worse than V3/V7/V8.
- Overall precision: 0.3132 — too many false detections.

## Next action

1. Preserve V9 for future specialist experiments only.
2. Do not run the expensive full OCR golden suite for V9 as a general replacement.
3. Use V3 for precise detections and V7/V8 only through protected specialist rules.
4. Before supervisor handover, run a short normal-user smoke test using the existing protected configuration; do not claim 100% automatic accuracy.

The production model was not changed by this evaluation.
