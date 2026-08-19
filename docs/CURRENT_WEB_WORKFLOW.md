# Current Web Workflow

This document describes the active website workflow.

## Run The Website

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING"
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

Open:

```text
http://127.0.0.1:8001
```

## Active Flow

```text
webapp/server.py
    receives uploaded PDF
    creates generated_jobs/jobs/<job_id>
        |
        v
code/api_bridge.py
    small wrapper for web usage
        |
        v
code/auto_ballooning.py
    renders first PDF page
    reads title-block metadata with OCR
    runs or reuses measurement OCR
    detects engineering symbols with local YOLO plus the Roboflow Workflow when enabled
    filters false candidates
    parses dimensions/callouts
    creates ballooned PNG/PDF
    creates FA Excel
        |
        v
webapp/static/app.js
    shows balloon preview
    allows table correction
    downloads corrected Excel
```

## Important Runtime Folders

```text
generated_jobs/jobs/     current website output
webapp/storage/          older website output; keep only if needed for history
debug/                   OCR/model debug images
test_outputs/            manual test outputs
```

## Title-Block OCR

The active web flow now runs title-block OCR before generating the balloon drawing
and FA workbook.

Title-block metadata is filled in this order:

```text
filename metadata / known drawing map
    then fill missing fields from title-block OCR
```

This keeps known reference drawings stable while allowing new drawings to fill:

```text
part number
drawing number
revision
material
part name
```

Debug output for each job is saved under:

```text
generated_jobs/jobs/<job_id>/titleblock_debug
```

## Roboflow Symbol Workflow

The web flow can call the published Roboflow Workflow:

```text
workspace: krafo
workflow: engineering-symbol-detection-2-vengineering-symbol-detection-2-2-yolov8s-t1-logic
input: image
output: predictions
```

Set the API key in the environment before running the website:

```powershell
$env:ROBOFLOW_API_KEY="your_roboflow_api_key"
```

Optional settings are already shown in `.env.example`: `ROBOFLOW_API_URL`,
`ROBOFLOW_WORKSPACE`, `ROBOFLOW_WORKFLOW_ID`, `ROBOFLOW_TIMEOUT_SECONDS`,
`ROBOFLOW_MAX_RETRIES`, `ROBOFLOW_ENABLED`, and `ROBOFLOW_CONFIDENCE`.

Run the smoke test with:

```powershell
python test_roboflow_requests.py
```

Note: on 2026-07-06 the MCP smoke run reached Roboflow but the published
workflow failed because the inner workflow step referenced an unsupported
`model_id` binding. The child workflow reported valid input names:
`class_agnostic_nms`, `confidence`, `image`, `iou_threshold`, and
`max_detections`. Fix and publish the Roboflow workflow before expecting the
local smoke test to pass.

## Current Accuracy Limits

- OCR can still read numbers from notes, title blocks, and tolerance tables.
- Repeated values can be hard to match to the correct balloon position.
- Title block OCR is connected, but some drawings may still need manual review if
  the crop score is low or the title block format is unusual.
- Hole callouts need more rule-based parsing before using ML.

## Next Cleanup Phase

1. Move report writing out of `auto_ballooning.py`.
2. Move balloon rendering out of `auto_ballooning.py`.
3. Add layout classes for `title_block`, `notes_area`, `tolerance_table`, and `revision_table`.
4. Connect title-block OCR to the web flow.
5. Add `GOOD`, `NEED CHECK`, and `REJECTED` status to each row.
