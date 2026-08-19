# Auto Ballooning Next Steps

This project is now moving from symbol detection into an AI-assisted inspection-plan workflow.

## Current Backend Flow

1. Convert drawing PDFs into page images.
2. Detect title block and read title-block fields.
3. Detect engineering symbols with local YOLO and the Roboflow Workflow when `ROBOFLOW_API_KEY` is set.
4. Extract measurement-like OCR text with PaddleOCR.
5. Assign balloon numbers.
6. Export an inspection-plan Excel file.
7. Save debug overlay images for staff review.

## Run Symbol Detection

Use the local model plus the configured Roboflow Workflow for now. The workflow
configuration lives in `.env.example` and defaults to:

```text
krafo / engineering-symbol-detection-2-vengineering-symbol-detection-2-2-yolov8s-t1-logic
```

```bash
cd "/c/Users/izzuddin/Desktop/OCR DRAWING"
python code/symbol_detection.py --conf 0.60 --classes all --output symbol_detection_results.xlsx
```

Outputs:

- `symbol_detection_results.xlsx`
- `debug/symbol_detection`

Smoke-test the Roboflow client separately:

```bash
python test_roboflow_requests.py
```

## Run Measurement Extraction

Start with one drawing first:

```bash
cd "/c/Users/izzuddin/Desktop/OCR DRAWING"
python code/measurement_extraction.py --limit 1 --output measurement_detection_results.xlsx
```

Run all drawings when the test result looks acceptable:

```bash
cd "/c/Users/izzuddin/Desktop/OCR DRAWING"
python code/measurement_extraction.py --output measurement_detection_results.xlsx --resume
```

Outputs:

- `measurement_detection_results.xlsx`
- `debug/measurement_detection`

Note: full OCR on CPU can be slow. One drawing took about one minute on the test laptop.

## Create Inspection Plan And Balloons

For a test:

```bash
cd "/c/Users/izzuddin/Desktop/OCR DRAWING"
python code/auto_ballooning.py --measurements measurement_detection_results.xlsx --symbols symbol_detection_results.xlsx --output inspection_plan.xlsx
```

For the full result:

```bash
cd "/c/Users/izzuddin/Desktop/OCR DRAWING"
python code/auto_ballooning.py --measurements measurement_detection_results.xlsx --symbols symbol_detection_results.xlsx --output inspection_plan.xlsx
```

Outputs:

- `inspection_plan.xlsx`
- `debug/ballooning`

Note: ballooning is fast by default. Use `--local-refine` only for a small test or difficult drawing because it runs extra PaddleOCR and can be slow on CPU.

## How To Judge The Result

Open the Excel files and check:

- Wrong OCR text
- False measurement rows from title block or notes
- Missing important dimensions
- Low confidence rows
- Wrong symbol classes

Then improve by correcting annotations, adding more examples, and retraining.
