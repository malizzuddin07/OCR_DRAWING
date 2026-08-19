# Phase 3 - Intelligent Layout Detection

## Current Status

Phase 2 works as a pipeline:

- PDFs are converted to images.
- A title block crop is produced.
- OCR text is extracted.
- AI extraction writes Excel output.

But Phase 2 uses a fixed bottom-right crop. This is why some drawings work well and some become REVIEW.

Phase 3 solves this by detecting the layout automatically.

## Important Lesson

Different drawings can have different title block positions, sizes, and table styles.

That means we should not expect one simple crop rule to work for every file.

The correct Phase 3 workflow is:

1. Detect possible regions.
2. Review visually.
3. Create verified labels.
4. Improve traditional CV if the patterns are simple.
5. Train YOLO if the patterns vary too much.

## Classes To Detect

Start with only one class:

```text
title_block
```

After title block detection is reliable, add:

```text
revision_table
notes_area
bom_table
```

Do not label all classes immediately. Title block is the most important because it directly affects OCR quality.

## How To Run The Current Phase 3 Baseline

From the project folder:

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING"
python code\layout_detection.py
```

Output folders:

```text
dataset/layout_regions
debug/layout_detection
```

Open the PNG files in:

```text
debug/layout_detection
```

Check whether the green box covers the title block.

## How To Review

For each drawing, decide one of these:

```text
OK
TOO_BIG
TOO_SMALL
WRONG_AREA
NO_TITLE_BLOCK
```

The current detector is only a baseline. If many files are TOO_BIG, TOO_SMALL, or WRONG_AREA, that is strong evidence that YOLO will be better than pure traditional CV.

## Recommended Next Step

Label 20 to 30 drawings manually for `title_block`.

Use this rule:

```text
The box should cover the full title block table, not the full drawing border.
```

Keep the box tight but do not cut off any title block cells.

## When To Use Traditional CV

Use traditional CV if:

- title blocks are always near the same area,
- table lines are clear,
- the outer drawing border can be removed reliably,
- all drawings have similar sheet format.

## When To Use YOLO

Use YOLO if:

- title blocks move around,
- some drawings have different title block designs,
- table lines connect to the drawing border,
- there are many suppliers or drawing templates,
- CV rules become too many and fragile.

For this project, YOLO is likely the better long-term choice if the drawings continue to vary.

## Phase 3 Success Target

Before connecting Phase 3 back into OCR, aim for:

```text
title_block detection accuracy: 90%+
```

Only then replace the fixed crop in `ocr_pipeline.py`.

