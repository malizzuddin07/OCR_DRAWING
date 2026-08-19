# YOLO Title Block Training Steps

## Goal

Train YOLO to find one object:

```text
title_block
```

Use YOLO only to find the crop. OCR still extracts the text after the crop is found.

## 1. Prepare Images For Labeling

From the project folder:

```powershell
python code\prepare_yolo_dataset.py --stage labeling
```

This creates:

```text
dataset/yolo_titleblock/images/all
dataset/yolo_titleblock/labels/all
dataset/yolo_titleblock/classes.txt
```

If an image is missing from `dataset/images`, the script converts the PDF from
`dataset/raw_pdfs` first.

## 2. Label The Images

Use LabelImg, CVAT, Roboflow, or Label Studio.

Recommended simple option:

```powershell
pip install labelImg
labelImg
```

In LabelImg:

1. Open `dataset/yolo_titleblock/images/all`.
2. Change save directory to `dataset/yolo_titleblock/labels/all`.
3. Set format to YOLO.
4. Draw one box around the full title block.
5. Use the class name `title_block`.
6. Save every image.

Good label:

```text
tight box around the full title block table
```

Bad label:

```text
whole drawing border
only drawing number cell
only revision cell
too much empty area
```

## 3. Split Dataset

After every image has a label file:

```powershell
python code\prepare_yolo_dataset.py --stage split
```

This creates:

```text
dataset/yolo_titleblock/images/train
dataset/yolo_titleblock/images/val
dataset/yolo_titleblock/labels/train
dataset/yolo_titleblock/labels/val
dataset/yolo_titleblock/data.yaml
```

## 4. Train YOLO

Install Ultralytics:

```powershell
pip install ultralytics
```

Train:

```powershell
python code\train_yolo_titleblock.py --epochs 100 --imgsz 960 --batch 4
```

If you have an NVIDIA GPU:

```powershell
python code\train_yolo_titleblock.py --epochs 100 --imgsz 960 --batch 4 --device 0
```

The trained model will be saved under:

```text
runs/titleblock/yolo_titleblock/weights/best.pt
```

## 5. Test Prediction

```powershell
python code\predict_yolo_titleblock.py
```

Open the output images under:

```text
runs/titleblock/predict_titleblock
```

Check whether the box covers the title block correctly.

## 6. Improve

If YOLO is wrong, fix labels first.

Common fixes:

```text
make boxes more consistent
avoid including the full drawing border
avoid cutting off title block cells
add more drawings
train with imgsz 1280 if title blocks are too small
```

