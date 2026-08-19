# OCR DRAWING - Supervisor Demo Handover

Date: 14 August 2026

## What is ready today

The system provides an AI-assisted drawing inspection workflow with mandatory human QC review.

- Upload a PDF engineering drawing and run OCR extraction.
- Review detected balloons and extracted values in the preview table.
- Add a missing balloon by drawing a box around its dimension.
- OCR the new box and add the result to the review table.
- Edit extracted values directly in the table.
- Delete an incorrect balloon and automatically reorder the remaining balloon numbers.
- Change a balloon number and automatically reorder the table and drawing preview.
- Download a corrected ballooned PDF and Excel inspection report.
- Approve a completely checked drawing and save the original and corrected data together.
- Prevent ordinary downloads from being treated as approved learning data.
- Prevent accidental duplicate approvals.

## Important model status

The active production model remains:

`krafo/ocr-balloon-system-5-yolov8s-t1`

The locally trained V1 model has the strongest standalone validation result currently saved:

- mAP50: 70.96%
- mAP50-95: 43.83%
- Recall: 81.07%

These values come from that model's own validation split and are not proof of full-system accuracy.

The latest V3 + V7 + V8 full-system candidate was rejected by the five-drawing golden gate:

- Approved characteristics: 379
- Candidate characteristics: 367
- Value differences: 24
- Balloon geometry differences: 60
- Balloon overlaps: 0

Therefore, no local candidate is automatically promoted today. The supervisor demonstration must be described as **AI-assisted with human QC**, not 100% automatic inspection.

## Start the system

Open PowerShell and run:

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING"
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

Open this address in a browser:

`http://127.0.0.1:8001`

If port 8001 is already in use, the system may already be running. Check with:

```powershell
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
```

## Recommended five-minute demonstration

1. Upload one drawing and click **Run Extraction**.
2. Show the ballooned drawing and editable review table.
3. Click **Add Balloon**, then draw a tight box around one missing dimension.
4. Show that OCR adds the new value to the table and updates the drawing preview.
5. Edit a yellow table cell and explain that the corrected value is used in the Excel report.
6. Change one balloon number and show that the table and drawing numbering reorder together.
7. Delete an incorrect row and show that the remaining balloons reorder.
8. Click **Corrected PDF** and **Download Excel**.
9. Explain that **Approve & Download** is only used after checking the complete drawing.
10. Explain that approval stores corrections for controlled future training; it does not silently replace the active model.

## Verified checks

- Approval comparison and learning-record tests: 13 passed.
- Model registry and safe-promotion tests: 5 passed.
- Browser JavaScript syntax check: passed.
- Automatic model promotion: disabled.

## Deployment decision for today

Use the current active model with the review workflow. Keep all new locally trained models as candidates until one passes the complete golden gate and repeatability test.
