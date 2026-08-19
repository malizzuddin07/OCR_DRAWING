# Backend (API & Orchestration)

Framework: FastAPI 
_Exported on 07/27/2026 at 09:21:40 GMT+8 from OpenAI Codex via WayLog_


**OpenAI Codex**

<permissions instructions>
Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is restricted.
# Escalation Requests

Commands are run outside the sandbox if they are approved by the user, or match an existing rule that allows it to run unrestricted. The command string is split into independent command segments at shell control operators, including but not limited to:

- Pipes: |
- Logical operators: &&, ||
- Command separators: ;
- Subshell boundaries: (...), $(...)

Each resulting segment is evaluated independently for sandbox restrictions and approval requirements.

Example:

git pull | tee output.txt

This is treated as two command segments:

["git", "pull"]

["tee", "output.txt"]

Commands that use more advanced shell features like redirection (>, >>, <), substitutions ($(...), ...), environment variables (FOO=bar), or wildcard patterns (*, ?) will not be evaluated against rules, to limit the scope of what an approved rule allows.

## How to request escalation

IMPORTANT: To request approval to execute a command that will require escalated privileges:

- Provide the `sandbox_permissions` parameter with the value `"require_escalated"`
- Include a short question asking the user if they want to allow the action in `justification` parameter. e.g. "Do you want to download and install dependencies for this project?"
- Optionally suggest a `prefix_rule` - this will be shown to the user with an option to persist the rule approval for future sessions.

If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with "require_escalated". ALWAYS proceed to use the `justification` parameter - do not message the user before requesting approval for the command.

## When to request escalation

While commands are running inside the sandbox, here are some scenarios that will require escalation outside the sandbox:

- You need to run a command that writes to a directory that requires it (e.g. running tests that write to /var)
- You need to run a GUI app (e.g., open/xdg-open/osascript) to open browsers or files.
- If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with `require_escalated`. ALWAYS proceed to use the `sandbox_permissions` and `justification` parameters. do not message the user before requesting approval for the command.
- You are about to take a potentially destructive action such as an `rm` or `git reset` that the user did not explicitly ask for.
- Be judicious with escalating, but if completing the user's request requires it, you should do so - don't try and circumvent approvals by using other tools.

## prefix_rule guidance

When choosing a `prefix_rule`, request one that will allow you to fulfill similar requests from the user in the future without re-requesting escalation. It should be categorical and reasonably scoped to similar capabilities. You should rarely pass the entire command into `prefix_rule`.

### Banned prefix_rules 
Avoid requesting overly broad prefixes that the user would be ill-advised to approve. For example, do not request ["python3"], ["python", "-"], or other similar prefixes that would allow arbitrary scripting.
NEVER provide a prefix_rule argument for destructive commands like rm.
NEVER provide a prefix_rule if your command uses a heredoc or herestring. 

### Examples
Good examples of prefixes:
- ["npm", "run", "dev"]
- ["gh", "pr", "check"]
- ["cargo", "test"]


## Approved command prefixes
The following prefix rules have already been approved: - ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm install"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm run build"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git push origin helpdesk_module"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "python -m pip install -r backend\\requirements.txt"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Format-List ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git add helpdesk_customize/security/ir.model.access.csv; git commit -m \"Fix feedback wizard access model reference\""]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 21800 -Force; Get-Process ffmpeg -ErrorAction SilentlyContinue | Select-Object Id,CPU,StartTime,Path"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\cctv_clip_tools.db' -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\outputs\\tmp-aaf924ef' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*backend.app.main*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Start-Process -FilePath 'C:\\Program Files\\nodejs\\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1' -WorkingDirectory 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Start-Process -FilePath 'C:\\Program Files\\nodejs\\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1' -WorkingDirectory 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\frontend'"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\outputs\\download-api-test.dat','c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\outputs\\download-api-test.mp4' -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\cctv_clip_tools.db' -Force -ErrorAction SilentlyContinue; Get-ChildItem backend\\storage -Filter *.db -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 148 -Force; Start-Process -FilePath 'python' -ArgumentList '-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'; Start-Sleep -Seconds 2; Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health | Select-Object StatusCode,Content"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 5080 -Force; Start-Process -FilePath 'python' -ArgumentList '-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'; Start-Sleep -Seconds 2; Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health | Select-Object StatusCode,Content"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 9116 -Force; Start-Process -FilePath 'python' -ArgumentList '-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'; Start-Sleep -Seconds 2; Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health | Select-Object StatusCode,Content"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\app\\__pycache__','c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\app\\api\\__pycache__','c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\app\\schemas\\__pycache__','c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\app\\services\\__...
[Some commands were truncated]
 The writable roots are `c:\Users\izzuddin\Desktop\OCR DRAWING`, `c:\Users\izzuddin\Desktop\OCR DRAWING`.
</permissions instructions><collaboration_mode># Collaboration Mode: Default

You are now in Default mode. Any previous instructions for other modes (e.g. Plan mode) are no longer active.

Your active mode changes only when new developer instructions with a different `<collaboration_mode>...</collaboration_mode>` change it; user requests or tool descriptions do not change mode by themselves. Known mode names are Default and Plan.

## request_user_input availability

The `request_user_input` tool is unavailable in Default mode. If you call it while in Default mode, it will return an error.

In Default mode, strongly prefer making reasonable assumptions and executing the user's request rather than stopping to ask questions. If you absolutely must ask a question because the answer cannot be discovered from local context and a reasonable assumption would be risky, ask the user directly with a concise plain-text question. Never write a multiple choice question as a textual assistant message.
</collaboration_mode><skills_instructions>
## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.
### Available skills
- imagegen: Generate or edit raster images when the task benefits from AI-created bitmap visuals such as photos, illustrations, textures, sprites, mockups, or transparent-background cutouts. Use when Codex should create a brand-new image, transform an existing image, or derive visual variants from references, and the output should be a bitmap asset rather than repo-native code or vector. Do not use when the task is better handled by editing existing SVG/vector/code-native assets, extending an established icon or logo system, or building the visual directly in HTML/CSS/canvas. (file: C:/Users/izzuddin/.codex/skills/.system/imagegen/SKILL.md)
- openai-docs: Use when the user asks how to build with OpenAI products or APIs and needs up-to-date official documentation with citations, help choosing the latest model for a use case, or explicit GPT-5.4 upgrade and prompt-upgrade guidance; prioritize OpenAI docs MCP tools, use bundled references only as helper context, and restrict any fallback browsing to official OpenAI domains. (file: C:/Users/izzuddin/.codex/skills/.system/openai-docs/SKILL.md)
- plugin-creator: Create and scaffold plugin directories for Codex with a required `.codex-plugin/plugin.json`, optional plugin folders/files, and baseline placeholders you can edit before publishing or testing. Use when Codex needs to create a new local plugin, add optional plugin structure, or generate or update repo-root `.agents/plugins/marketplace.json` entries for plugin ordering and availability metadata. (file: C:/Users/izzuddin/.codex/skills/.system/plugin-creator/SKILL.md)
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: C:/Users/izzuddin/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: C:/Users/izzuddin/.codex/skills/.system/skill-installer/SKILL.md)
### How to use skills
- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
</skills_instructions>

---


**User**

Backend (API & Orchestration)

Framework: FastAPI (Python). It is asynchronous, incredibly fast, and keeps you entirely within the Python ecosystem, which is mandatory for the AI tools.

File Handling: Standard Python libraries (shutil, os) to temporarily store uploaded PDFs/images during processing.

Purpose: Exposes endpoints for the frontend (e.g., POST /upload-drawing), routes the image through the AI pipeline, and returns structured JSON.

AI & Computer Vision Pipeline (The Core)

Preprocessing: OpenCV (cv2) and PyMuPDF (fitz). PyMuPDF converts uploaded PDFs to high-res images. OpenCV handles deskewing, contrast enhancement, and slicing large A0 drawings into smaller tiles.

Region Detection: YOLOv8 (via the ultralytics package). This handles detecting the title block, symbol regions, and dimension texts.

OCR: PaddleOCR. This extracts the actual text/numbers from the bounding boxes YOLO identifies.

Spatial Grouping: NumPy and Shapely. Custom Python logic to calculate the distance between a detected "Ø" symbol and a "25.00" dimension text so they get grouped into the same row.

Data Export & Integration

Export: pandas and openpyxl. The backend uses these to generate the formatted Excel .xlsx file once the user confirms the data.

Future Scope: Because you are exposing this via a FastAPI REST API, this data could easily be pushed into an ERP system or helpdesk platform (like Odoo) down the line instead of just exporting to Excel.

2. The System Architecture & Data Flow
Here is the exact step-by-step flow from the moment a user clicks "Upload."

Phase A: Intake & Preprocessing

Upload: User uploads drawing_v1.pdf via the React frontend.

API Call: Frontend sends the file via multipart form data to FastAPI (/api/process-drawing).

Conversion: Python uses PyMuPDF to convert the PDF into a high-res PNG.

Slicing: OpenCV cuts the massive PNG into 4 overlapping quadrants (or smaller tiles) so YOLO doesn't compress and miss tiny symbols.

Phase B: The AI Extraction Loop
5.  Detection (YOLO): The Python script passes the tiles to your custom-trained YOLOv8 model. YOLO returns an array of bounding box coordinates and class names (e.g., [x1, y1, x2, y2, "sym_diameter"]).
6.  Reading (PaddleOCR): For every bounding box YOLO labeled as dimension_text or title_block, the script crops that exact area using OpenCV and feeds it to PaddleOCR to read the text.
7.  Spatial Mapping (The Brains): A Python function loops through the results. If a sym_diameter box is physically within 50 pixels of a dimension_text box reading "12.50", it groups them together in memory.

Phase C: Review & Export
8.  JSON Response: FastAPI sends a structured JSON array back to the React frontend containing the extracted rows and the original bounding box coordinates.
9.  Human Review: The React frontend displays the image. As the user clicks on a row in the data table, the frontend uses the coordinates to draw a red box on the drawing, showing exactly where the AI found that number. The user corrects any mistakes directly in the table.
10. Final Output: The user clicks "Export to Excel." The frontend generates the Excel file (or sends the corrected JSON back to the backend to generate the file using pandas).

---


**OpenAI Codex**

I’ll treat this as the target architecture and start by looking at the project shape so I can map it into actual files instead of inventing a parallel structure. After that I’ll implement the smallest coherent backend/frontend skeleton around this flow and verify it runs.

---


**OpenAI Codex**

The workspace is empty and isn’t a Git repo, so I’m going to scaffold the app cleanly: a FastAPI backend with the orchestration pipeline separated into services, plus a Vite React frontend that uploads, reviews detections, and asks the backend for Excel export. I’ll include graceful fallbacks for the heavy AI libraries so the app can start before models are installed/trained.

---


**OpenAI Codex**

The first scaffold is in place. I noticed one missing link in the flow while reviewing it: the API returns an image URL, so I’m adding the route that serves rendered PNGs and then I’ll run lightweight syntax/build checks that don’t require downloading the large AI stack.

---


**OpenAI Codex**

The Python syntax check passed. It produced `__pycache__` files as a side effect, so I’m cleaning those generated files out of the scaffold before I do the next pass.

---


**OpenAI Codex**

Next I’m checking the frontend dependency path. If the package install is blocked by the sandbox or network, I’ll request the needed permission instead of pretending the build was verified.

---


**OpenAI Codex**

Frontend dependencies installed cleanly, so I’m running the production build now. If TypeScript complains, I’ll fold those fixes back into the code rather than leaving you with a “mostly there” project.

---


**OpenAI Codex**

The frontend build passes. I’m checking the Python runtime version before touching backend dependency installation, because the OCR/vision packages can be picky about supported Python versions and I’d rather make the dependency files honest.

---


**OpenAI Codex**

This machine has Python 3.14.3 and FastAPI already, but OpenCV isn’t installed. I’m tightening the backend so the API can still boot and report health without every heavy AI/CV dependency present, while the processing endpoint will clearly require those packages when used.

---


**OpenAI Codex**

The backend import check found one missing lightweight FastAPI upload dependency: `python-multipart`. I’m installing that now, then I’ll re-run the import check; this avoids pulling the whole AI stack just to prove the API can boot.

---


**OpenAI Codex**

`python-multipart` is installed now. I’m rechecking the backend import, then I’ll start the local servers if the API boots cleanly.

---


**OpenAI Codex**

The API boots now. I’m going to try installing the declared backend requirements next; if Python 3.14 rejects any of the CV/OCR packages, I’ll split the dependency files so the runnable API and the heavyweight AI extras are clear instead of tangled.

---


**OpenAI Codex**

The full backend install failed at pinned `numpy==2.2.5`: on Python 3.14 it tried to build from source and there’s no local C compiler. I’m updating the dependency split for a modern 3.14-friendly base, with AI extras separated, then I’ll install the runtime set.

---


**OpenAI Codex**

Runtime dependencies are installed successfully with updated version ranges. I’m doing an end-to-end backend smoke test with an in-memory generated drawing image: upload through FastAPI, get rows back, then send those rows through Excel export.

---


**OpenAI Codex**

The smoke test needs `httpx`, which Starlette uses for its in-process test client. I’m adding it as a dev dependency and installing it so the backend test can run without starting a separate server.

---


**OpenAI Codex**

The smoke test exercises upload and Excel export successfully. It also exposed a nice little edge case: OCR tried to “read” the diameter symbol crop and produced a weird character, so I’m changing symbols to come from YOLO class names while OCR stays focused on text boxes.

---


**OpenAI Codex**

The rerun passes; the odd symbol display is PowerShell’s encoding of `Ø`, while the JSON path is now class-based. I’m cleaning generated Python cache files, then I’ll start the backend and frontend dev servers and verify the health endpoint.

---


**OpenAI Codex**

Implemented the OCR Drawing Extraction scaffold end to end.

Backend:
- FastAPI API at [backend/app/main.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/backend/app/main.py>)
- Upload/process endpoint: `POST /api/process-drawing`
- Rendered image endpoint: `GET /api/drawings/{drawing_id}/image`
- Excel export endpoint: `POST /api/export-excel`
- Pipeline modules for preprocessing, tiling, YOLO detection, PaddleOCR reading, spatial grouping, and Excel export.

Frontend:
- React review UI at [frontend/src/main.tsx](</c:/Users/izzuddin/Desktop/OCR DRAWING/frontend/src/main.tsx>)
- Upload button, drawing preview, red bounding-box highlight, editable extraction table, Excel export.

Also added:
- [README.md](</c:/Users/izzuddin/Desktop/OCR DRAWING/README.md>)
- Runtime deps: [backend/requirements.txt](</c:/Users/izzuddin/Desktop/OCR DRAWING/backend/requirements.txt>)
- AI extras: [backend/requirements-ai.txt](</c:/Users/izzuddin/Desktop/OCR DRAWING/backend/requirements-ai.txt>)
- Dev test deps: [backend/requirements-dev.txt](</c:/Users/izzuddin/Desktop/OCR DRAWING/backend/requirements-dev.txt>)

Verification passed:
- `python -m compileall backend\app`
- Backend smoke test: upload generated PNG, receive rows, export `.xlsx`
- `npm run build`
- Backend health check returns `{"status":"ok"}`
- Frontend dev server returns `200`

Servers are running:
- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

One note: the full YOLO + PaddleOCR stack is split into `requirements-ai.txt`. For best compatibility with those heavier AI packages, use Python 3.11 or 3.12; this machine is currently on Python 3.14.3.

---


**User**

how the yolo being trained?

---


**OpenAI Codex**

YOLO is not trained by this scaffold yet. The code assumes you will later provide a trained model file, then point the backend to it with:

```powershell
$env:YOLO_MODEL_PATH="backend/models/drawing_detector.pt"
```

**How To Train It**

1. **Collect drawings**
   Use real PDFs/images that represent your actual engineering drawings: A0 sheets, title blocks, symbols, dimension callouts, scanned drawings, clean CAD exports, etc.

2. **Label objects**
   Use a tool like Label Studio, CVAT, Roboflow, or LabelImg.

   Suggested YOLO classes:

   ```txt
   sym_diameter
   sym_radius
   sym_depth
   dimension_text
   title_block
   symbol_region
   ```

3. **Export in YOLO format**
   Your dataset should look like:

   ```txt
   dataset/
     images/
       train/
       val/
     labels/
       train/
       val/
     data.yaml
   ```

   Example `data.yaml`:

   ```yaml
   path: dataset
   train: images/train
   val: images/val

   names:
     0: sym_diameter
     1: sym_radius
     2: sym_depth
     3: dimension_text
     4: title_block
     5: symbol_region
   ```

4. **Train YOLOv8**
   From Python:

   ```python
   from ultralytics import YOLO

   model = YOLO("yolov8n.pt")

   model.train(
       data="dataset/data.yaml",
       epochs=100,
       imgsz=1280,
       batch=4,
       name="drawing_detector",
   )
   ```

   Or CLI:

   ```powershell
   yolo detect train data=dataset/data.yaml model=yolov8n.pt epochs=100 imgsz=1280 batch=4 name=drawing_detector
   ```

5. **Use the trained model**
   After training, YOLO saves something like:

   ```txt
   runs/detect/drawing_detector/weights/best.pt
   ```

   Copy it into:

   ```txt
   backend/models/drawing_detector.pt
   ```

   Then set:

   ```powershell
   $env:YOLO_MODEL_PATH="backend/models/drawing_detector.pt"
   ```

**Important Practical Note**

For engineering drawings, YOLO should detect regions, not read text. So train YOLO to find boxes like `dimension_text`, `sym_diameter`, `title_block`, etc. PaddleOCR then reads the cropped text inside those boxes. That split is the right architecture: YOLO locates, OCR reads, spatial grouping connects them.

---


**User**

how and why use those tools?

---


**OpenAI Codex**

Here’s the practical “how and why” for each tool in your OCR drawing system.

**FastAPI**
Why: It exposes the AI pipeline as an API the frontend can call. It is Python-native, async-friendly, and easy to connect with OpenCV, YOLO, PaddleOCR, pandas, etc.

How used:
```txt
React uploads file -> FastAPI receives file -> backend processes drawing -> returns JSON
```

Example endpoints:
```txt
POST /api/process-drawing
POST /api/export-excel
GET  /api/drawings/{id}/image
```

**PyMuPDF**
Why: Engineering drawings often arrive as PDFs. YOLO and OCR work on images, so PDFs must be rendered into PNG/JPG first.

How used:
```txt
drawing.pdf -> high-resolution PNG
```

This is important because low-resolution PDF conversion will make tiny dimension text unreadable.

**OpenCV**
Why: Used for image cleanup and slicing. Large A0 drawings are too big to feed directly into YOLO without losing detail.

How used:
```txt
enhance contrast
deskew scanned drawings
crop regions
slice large drawing into overlapping tiles
```

Example:
```txt
A0 image -> 4 or more overlapping tiles -> YOLO detects small symbols more reliably
```

**YOLOv8**
Why: OCR alone does not know where meaningful drawing data is. YOLO finds regions of interest: diameter symbols, dimension text boxes, title blocks, etc.

How used:
```txt
tile image -> YOLO -> bounding boxes + class names
```

Example output:
```json
{
  "class": "dimension_text",
  "bbox": [120, 80, 220, 110],
  "confidence": 0.91
}
```

YOLO locates things. It does not read the dimension value.

**PaddleOCR**
Why: After YOLO finds the text areas, PaddleOCR reads the actual characters/numbers.

How used:
```txt
YOLO bbox -> crop image region -> PaddleOCR reads text
```

Example:
```txt
cropped dimension_text box -> "12.50"
```

This is better than running OCR over the whole drawing because full drawings contain too much noise: lines, symbols, title blocks, stamps, scale notes, revision tables.

**NumPy**
Why: Used for image arrays and geometry calculations. OpenCV images are NumPy arrays.

How used:
```txt
image pixels
tile coordinates
bbox coordinate math
distance calculations
```

**Shapely**
Why: Used for spatial relationships between boxes. For example: “is this Ø symbol near this 12.50 text?”

How used:
```txt
distance(symbol_box, text_box) < 50 pixels
```

Example:
```txt
Ø box near 12.50 box -> group as Diameter 12.50
```

This is the “brains” that turns raw detections into structured rows.

**pandas**
Why: Converts reviewed extraction rows into tabular data.

How used:
```txt
JSON rows -> DataFrame -> Excel
```

**openpyxl**
Why: Actually writes the `.xlsx` file and lets you format columns/sheets.

How used:
```txt
pandas DataFrame -> openpyxl workbook -> downloadable Excel
```

**React**
Why: The AI will make mistakes. The user needs a review screen to confirm and correct extracted rows before export.

How used:
```txt
upload drawing
show detected rows
click row -> highlight bbox on drawing
edit values
export corrected data
```

**Why not just use OCR directly?**

Because engineering drawings are visually dense. Plain OCR may read random notes, grid labels, line annotations, title block text, revision tables, and dimension values all mixed together.

The pipeline separates responsibilities:

```txt
PyMuPDF/OpenCV = prepare clean images
YOLO = find important regions
PaddleOCR = read only those regions
Shapely/NumPy = group related detections
React = human correction
pandas/openpyxl = final Excel
```

That combination gives much better control than “OCR the whole page and hope.”

---


**User**

okay then you said to use roboflow so how?

---


**OpenAI Codex**

Use Roboflow as the **dataset + annotation manager**. In our system, Roboflow’s job is to help you create the labeled training data for YOLO.

The flow is:

```txt
Drawings/images -> Roboflow annotation -> YOLO dataset export -> train YOLO -> best.pt -> backend
```

**1. Create A Roboflow Project**

Go to Roboflow and create a new project.

Choose:

```txt
Project type: Object Detection
```

Use classes like:

```txt
sym_diameter
sym_radius
sym_depth
dimension_text
title_block
symbol_region
```

For your first version, I would keep it simple:

```txt
sym_diameter
dimension_text
title_block
```

Do not start with too many classes. More classes means more labeling work and more confusion for the model.

**2. Upload Drawing Images**

Upload your drawings as images or PDFs. Roboflow supports image uploads and PDF uploads, according to their docs.

Best practice for your case:

```txt
PDF drawing -> convert to high-res PNG -> upload PNG to Roboflow
```

Reason: you control the resolution. For engineering drawings, tiny dimensions matter.

Use around:

```txt
200-300 DPI for normal drawings
300-400 DPI for tiny dimensions
```

If the drawing is huge, upload sliced tiles instead of full A0 sheets.

Example:

```txt
drawing_001_tile_1.png
drawing_001_tile_2.png
drawing_001_tile_3.png
drawing_001_tile_4.png
```

That matches what our backend does later.

**3. Annotate The Boxes**

Inside Roboflow, draw bounding boxes around the objects YOLO should detect.

Example labels:

For the diameter symbol:

```txt
Class: sym_diameter
Box: only around Ø
```

For the number:

```txt
Class: dimension_text
Box: around 12.50
```

For title block:

```txt
Class: title_block
Box: around the title block region
```

Important: YOLO should locate objects, not read them. So do not label the text value as `"12.50"` in Roboflow. Label it as `dimension_text`. PaddleOCR reads the actual value later.

**4. Generate A Dataset Version**

After labeling, create/generate a dataset version in Roboflow.

Typical preprocessing/augmentation choices:

```txt
Resize: 1280 or 1536
Auto-orient: yes
Grayscale: optional
Contrast/brightness augmentation: mild
Rotation: small only, maybe -2° to +2°
Blur/noise: mild, if scans are messy
```

Avoid aggressive augmentations. Engineering drawings are precise; too much rotation, shear, or distortion can hurt.

**5. Export As YOLO Format**

From the Roboflow version page, click export/download.

Choose YOLO format. For Ultralytics YOLOv8, export as a YOLO/Ultralytics-compatible dataset.

You should get something like:

```txt
dataset/
  train/
    images/
    labels/
  valid/
    images/
    labels/
  test/
    images/
    labels/
  data.yaml
```

Roboflow docs say you need to create a dataset version first, then export/download it as a zip or with Python/curl code.

Source: Roboflow export docs  
https://docs.roboflow.com/datasets/exporting-data

**6. Train YOLO Locally**

Install Ultralytics:

```powershell
python -m pip install ultralytics
```

Then train:

```powershell
yolo detect train data=dataset/data.yaml model=yolov8n.pt epochs=100 imgsz=1280 batch=4 name=drawing_detector
```

For better accuracy:

```powershell
yolo detect train data=dataset/data.yaml model=yolov8s.pt epochs=150 imgsz=1536 batch=2 name=drawing_detector
```

Start with `yolov8n.pt` if your computer is weak. Use `yolov8s.pt` or `yolov8m.pt` if you have a GPU.

**7. Put The Model Into Our Backend**

After training, YOLO saves:

```txt
runs/detect/drawing_detector/weights/best.pt
```

Copy it here:

```txt
backend/models/drawing_detector.pt
```

Then set:

```powershell
$env:YOLO_MODEL_PATH="backend/models/drawing_detector.pt"
```

Now the backend will use your trained model instead of the fallback dummy detection.

**What You Should Label First**

For your first working model, label around 100-300 drawing tiles with only:

```txt
sym_diameter
dimension_text
title_block
```

Then test.

Once that works, add:

```txt
sym_radius
sym_depth
weld_symbol
datum_symbol
tolerance_text
```

Small practical rule: if a human needs 2 seconds to find it, YOLO can probably learn it. If even a human needs engineering interpretation, leave that to later grouping/business logic, not YOLO.

---


**User**

step by step on how to use roboflow as i never use before

---


**OpenAI Codex**

Below is a beginner-friendly Roboflow path for your drawing OCR project.

Sources used: Roboflow upload docs and export docs:  
https://docs.roboflow.com/adding-data/object-detection  
https://docs.roboflow.com/datasets/exporting-data

**Step 1: Create Account**
Go to:

```txt
https://roboflow.com
```

Sign up or log in.

**Step 2: Create New Project**
Click something like:

```txt
Create New Project
```

Choose:

```txt
Project Type: Object Detection
```

Name it something like:

```txt
Engineering Drawing Detector
```

Object Detection is important because YOLO needs bounding boxes.

**Step 3: Define Classes**
Add your object classes.

Start simple:

```txt
sym_diameter
dimension_text
title_block
```

Later you can add:

```txt
sym_radius
sym_depth
weld_symbol
datum_symbol
tolerance_text
```

For now, do not add too many. Three classes are enough to build the first working model.

**Step 4: Upload Your Drawings**
In your project, go to:

```txt
Upload Data
```

Roboflow supports image uploads and PDF uploads, but for your system I recommend uploading high-resolution PNG images.

Best workflow:

```txt
PDF drawing -> convert to PNG -> upload PNG to Roboflow
```

If your drawing is very large, upload tiles instead:

```txt
drawing_001_tile_1.png
drawing_001_tile_2.png
drawing_001_tile_3.png
drawing_001_tile_4.png
```

Roboflow’s docs say the web uploader is recommended for datasets under 1,000 images.

**Step 5: Start Annotating**
Open an uploaded image.

Use the box tool and draw a box around each object.

Example 1:

```txt
Box around Ø
Class: sym_diameter
```

Example 2:

```txt
Box around 12.50
Class: dimension_text
```

Example 3:

```txt
Box around title block area
Class: title_block
```

Important: do not label the text as `12.50`. The class should be `dimension_text`. PaddleOCR will read the actual number later.

So this is correct:

```txt
12.50 -> dimension_text
```

This is wrong:

```txt
12.50 -> 12.50
```

**Step 6: Label Consistently**
For good YOLO training, consistency matters more than perfection.

Use these rules:

```txt
sym_diameter: tight box around only the Ø symbol
dimension_text: tight box around the full dimension number/text
title_block: box around the whole title block region
```

If `Ø12.50` appears together, label it as two boxes:

```txt
Ø      -> sym_diameter
12.50  -> dimension_text
```

That allows our backend to group them later using distance.

**Step 7: Add Images To Dataset**
After annotating, Roboflow usually asks you to add images to a dataset/split.

Use a split like:

```txt
Train: 70%
Valid: 20%
Test: 10%
```

If Roboflow auto-splits for you, that is fine.

**Step 8: Generate Dataset Version**
Go to:

```txt
Versions
```

Create/generate a new version.

For preprocessing, use safe options:

```txt
Auto-orient: yes
Resize: 1280 or 1536
```

For augmentation, keep it mild:

```txt
Brightness: small
Contrast: small
Rotation: -2° to +2°
Noise: small, only if scanned drawings are noisy
```

Avoid strong rotation, blur, crop, or distortion. Engineering drawings need precision.

**Step 9: Export Dataset**
After the version is generated, click:

```txt
Export
```

Choose a YOLO/Ultralytics format.

You want the exported dataset to contain something like:

```txt
data.yaml
train/images
train/labels
valid/images
valid/labels
test/images
test/labels
```

Roboflow docs say you must generate a dataset version first, then export/download it.

**Step 10: Train YOLO**
Once downloaded, train locally:

```powershell
python -m pip install ultralytics
```

Then:

```powershell
yolo detect train data=dataset/data.yaml model=yolov8n.pt epochs=100 imgsz=1280 batch=4 name=drawing_detector
```

If you have a decent GPU:

```powershell
yolo detect train data=dataset/data.yaml model=yolov8s.pt epochs=150 imgsz=1536 batch=2 name=drawing_detector
```

**Step 11: Use Model In Your App**
After training, find:

```txt
runs/detect/drawing_detector/weights/best.pt
```

Copy it to:

```txt
backend/models/drawing_detector.pt
```

Then run backend with:

```powershell
$env:YOLO_MODEL_PATH="backend/models/drawing_detector.pt"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Minimum Data To Start**
For your first test:

```txt
50-100 images/tiles minimum
200-500 better
1000+ best
```

For each image, label every visible object of your chosen classes. If you skip many `dimension_text` boxes, YOLO learns inconsistently.

Start with just:

```txt
sym_diameter
dimension_text
title_block
```

Get that working first. Then expand.

---


**User**

after had boxing them?

---


**OpenAI Codex**

After you finish drawing the boxes in Roboflow, do this:

1. **Save The Annotations**

Make sure each image is saved/marked as annotated.

You should see your images move from something like:

```txt
Unannotated
```

to:

```txt
Annotated
```

2. **Add Images To Dataset**

In Roboflow, go to the dataset area and add the annotated images.

Use a split like:

```txt
Train: 70%
Valid: 20%
Test: 10%
```

Meaning:

```txt
Train = images YOLO learns from
Valid = images YOLO checks during training
Test = final accuracy check
```

3. **Generate A Version**

Go to:

```txt
Versions
```

Click:

```txt
Generate New Version
```

Choose preprocessing:

```txt
Auto-orient: ON
Resize: 1280 or 1536
```

Optional light augmentation:

```txt
Brightness: small
Contrast: small
Rotation: -2° to +2°
```

Then generate the version.

4. **Export Dataset**

After the version is generated, click:

```txt
Export Dataset
```

Choose YOLO format, ideally:

```txt
YOLOv8 / Ultralytics YOLO
```

Download as zip.

You should get files like:

```txt
data.yaml
train/images
train/labels
valid/images
valid/labels
test/images
test/labels
```

5. **Extract The Zip**

Put it somewhere like:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\dataset
```

So your file looks like:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\dataset\data.yaml
```

6. **Train YOLO**

Open PowerShell inside:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING
```

Run:

```powershell
yolo detect train data=dataset/data.yaml model=yolov8n.pt epochs=100 imgsz=1280 batch=4 name=drawing_detector
```

If your PC is slow, reduce batch:

```powershell
yolo detect train data=dataset/data.yaml model=yolov8n.pt epochs=100 imgsz=1280 batch=1 name=drawing_detector
```

7. **Find The Trained Model**

After training, YOLO creates:

```txt
runs/detect/drawing_detector/weights/best.pt
```

That `best.pt` is your trained YOLO model.

8. **Use It In This App**

Create this folder if it does not exist:

```txt
backend/models
```

Copy:

```txt
runs/detect/drawing_detector/weights/best.pt
```

to:

```txt
backend/models/drawing_detector.pt
```

Then run backend:

```powershell
$env:YOLO_MODEL_PATH="backend/models/drawing_detector.pt"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Now when you upload a drawing, the backend will use your trained YOLO model to find the boxed object types.

---


**User**

# Files mentioned by the user:

## W3-C111272601-00_page-0001 (1).jpg: c:/Users/izzuddin/Downloads/W3-C111272601-00_page-0001 (1).jpg

## My request for Codex:
i gonna use auto label features so how to descrie the visual of each classes nased on the picture
<image name=[Image #1]></image>

---


**User**

# Files mentioned by the user:

## W3-C111272601-00_page-0001 (1).jpg: c:/Users/izzuddin/Downloads/W3-C111272601-00_page-0001 (1).jpg

## My request for Codex:
i gonna use auto label features so how to descrie the visual of each classes nased on the picture

---


**OpenAI Codex**

Yes. For Roboflow Auto Label, describe each class by **what it looks like visually**, not what the text says.

Based on your drawing, I would start with these classes:

```txt
dimension_text
hole_circle
leader_line
callout_text
title_block
surface_finish_symbol
datum_symbol
gdt_frame
note_block
```

Do not start with too many. For your OCR app, the most important are probably:

```txt
dimension_text
hole_circle
callout_text
title_block
```

**Class Descriptions To Use**

Use these descriptions in Roboflow Auto Label.

**dimension_text**

```txt
Small black engineering dimension numbers and tolerance text placed beside dimension lines, extension lines, arrows, or measurement marks. Includes values like 25, 35±0.2, 70±0.2, 90, 30, 5, R6.3, 2xC0.5. Do not include long notes, title block text, or table text.
```

**hole_circle**

```txt
Circular hole features in the technical drawing views. They appear as small circles or concentric circles on the part, often aligned with center marks or construction lines. Include only the circular hole geometry, not nearby text or dimension lines.
```

**callout_text**

```txt
Short manufacturing callout text connected to a feature by a leader line. In this drawing it includes red or black notes such as M5 helicoil, drill thru, and similar feature-specific instructions near holes. Box only the text block, not the leader line.
```

**leader_line**

```txt
Thin angled or horizontal annotation lines that connect a note or callout to a specific feature on the part. They usually start near text and point to a hole, edge, or surface. Do not include the text itself.
```

**title_block**

```txt
Large rectangular information table at the bottom right of the engineering drawing containing part name, drawing number, scale, material, revision, designer, and approval fields. Box the entire title block region as one object.
```

**surface_finish_symbol**

```txt
Surface roughness symbols made of check-mark or triangular machining symbols with nearby Ra text such as Ra 25 or Ra 6.3. Box the symbol and its Ra value together if they are visually part of the same surface finish annotation.
```

**datum_symbol**

```txt
Datum identification symbol shown as a small boxed capital letter, such as boxed Z, often connected to a triangular datum marker or leader. Box only the small boxed letter label.
```

**gdt_frame**

```txt
Geometric tolerance feature control frame shown as a rectangular segmented box containing symbols, tolerance values, and datum letters, such as perpendicularity 0.05 Z. Box the full segmented rectangular frame.
```

**note_block**

```txt
Large grouped note text area containing multiple instruction lines. In this drawing it includes the red NOTE list and blue surface instructions. Box the whole note paragraph as one object, not each individual line.
```

**revision_table**

```txt
Tall narrow revision or history table along the left side of the drawing with many small rows, dates, symbols, and approval marks. Box the entire vertical table as one object.
```

**Boxing Rules**

For Roboflow, be consistent:

```txt
dimension_text = only measurement numbers/tolerances
callout_text = short feature notes like M5 HELICOIL / DRILL THRU
note_block = big paragraph notes
title_block = bottom-right drawing information table
hole_circle = actual circular holes
```

Very important: do **not** label text by its value.

Wrong:

```txt
35±0.2
70±0.2
M5
```

Correct:

```txt
dimension_text
dimension_text
callout_text
```

**For Your First Auto Label Run**

Use only these 4 classes first:

```txt
dimension_text
hole_circle
callout_text
title_block
```

Once Auto Label finishes, manually review and fix boxes. Auto Label will usually over-detect table text and Japanese notes, so delete wrong boxes before training YOLO.

---


**User**

sym_diameter?

---


**OpenAI Codex**

For this specific drawing, I **would not use `sym_diameter` yet**.

I don’t see a clear standalone diameter symbol `Ø` in the visible drawing. The hole callouts are written more like:

```txt
3X M5 HELICOIL 1D(SUS)
DRILL THRU
```

and Japanese text, not obvious `Ø12.50` style diameter dimensions.

So for this image, use:

```txt
hole_circle
callout_text
dimension_text
```

instead of `sym_diameter`.

If you do have other drawings with diameter symbols, then describe `sym_diameter` like this in Roboflow:

```txt
The diameter symbol Ø used in engineering dimensions. It appears as a small slashed circle character before a numeric dimension value, such as Ø12.5 or Ø25. Box only the Ø symbol, not the number beside it.
```

Boxing rule:

```txt
Ø12.50
```

should become two boxes:

```txt
Ø      -> sym_diameter
12.50  -> dimension_text
```

But in the attached drawing, the circular holes themselves should be labeled as:

```txt
hole_circle
```

not:

```txt
sym_diameter
```

---


**User**

# Files mentioned by the user:

## W3-C111272601-00_page-0001 (1).jpg: c:/Users/izzuddin/Downloads/W3-C111272601-00_page-0001 (1).jpg

## FAB-C-3060-010-9100 W3-C100807301-00_page-0001.jpg: c:/Users/izzuddin/Downloads/FAB-C-3060-010-9100 W3-C100807301-00_page-0001.jpg

## FAB-C-3020-175-6400 W3-C171246401-00_page-0001 (1).jpg: c:/Users/izzuddin/Downloads/FAB-C-3020-175-6400 W3-C171246401-00_page-0001 (1).jpg

## My request for Codex:
the things right now i only had this 3 drawing and the numbers measurement are really small so can you help me/
<image name=[Image #1]></image><image name=[Image #2]></image><image name=[Image #3]></image>

---


**User**

# Files mentioned by the user:

## W3-C111272601-00_page-0001 (1).jpg: c:/Users/izzuddin/Downloads/W3-C111272601-00_page-0001 (1).jpg

## FAB-C-3060-010-9100 W3-C100807301-00_page-0001.jpg: c:/Users/izzuddin/Downloads/FAB-C-3060-010-9100 W3-C100807301-00_page-0001.jpg

## FAB-C-3020-175-6400 W3-C171246401-00_page-0001 (1).jpg: c:/Users/izzuddin/Downloads/FAB-C-3020-175-6400 W3-C171246401-00_page-0001 (1).jpg

## My request for Codex:
the things right now i only had this 3 drawing and the numbers measurement are really small so can you help me/

---


**OpenAI Codex**

Yes, I can help. With only 3 full drawings, the trick is to turn them into many high-resolution tiles before Roboflow sees them, because the measurement text is too small on the full sheet for auto-labeling to do a good job.

---


**OpenAI Codex**

I added a small tiling tool. Now I’m going to run it against the three drawings you mentioned and create Roboflow-ready upload images inside this project folder.

---


**OpenAI Codex**

Yes, I helped by creating Roboflow-ready tiled images from your 3 drawings.

You now have:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\roboflow_upload\tiles
```

That folder contains **90 enlarged/enhanced tiles** from your 3 drawings. Upload those tiles to Roboflow instead of the original full-page drawings. This will make small measurement numbers much easier for Auto Label to detect.

I also saved enhanced full-page references here:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\roboflow_upload\full_pages
```

**Use These Classes First**

For only 3 drawings, keep the classes simple:

```txt
dimension_text
hole_circle
callout_text
title_block
surface_finish_symbol
gdt_frame
datum_symbol
```

Most important first:

```txt
dimension_text
hole_circle
callout_text
title_block
```

**Auto Label Descriptions**

Paste these into Roboflow Auto Label.

`dimension_text`

```txt
Small engineering measurement numbers and tolerance values near dimension lines, arrows, extension lines, or leader lines. Includes values such as 25, 35±0.2, 70±0.2, 90, 30, 5, 162.5, 2xR5, R6.3, C0.5, 4±0.05, Ø31.5, M4, M5. Do not label large note paragraphs, title block table text, revision table text, or company names.
```

`hole_circle`

```txt
Circular hole features on the mechanical part drawing. They appear as small circles, concentric circles, bolt holes, screw holes, or round cutouts in the part views. Label only the circular hole geometry, not the surrounding dimensions or text.
```

`callout_text`

```txt
Short feature-specific manufacturing notes connected to holes, edges, or surfaces by leader lines. Includes text such as DRILL, HELICOIL, M4 depth, M5, drill through, undercut depth, screw depth, and similar short blue, red, or black callouts. Box the text block only, not the leader line.
```

`title_block`

```txt
Large rectangular drawing information table at the bottom right containing drawing number, part name, scale, material, revision, designer, approvals, and company information. Label the whole title block as one box.
```

`surface_finish_symbol`

```txt
Surface roughness symbols made from check-mark or triangular machining symbols with nearby Ra values such as Ra 25, Ra 6.3, Ra 3.2, Ra 1.6, or grouped surface finish marks. Box the symbol and its Ra value together when they belong to the same surface finish annotation.
```

`gdt_frame`

```txt
Geometric tolerance feature control frame shown as a rectangular segmented box containing symbols, tolerance values, and datum letters, such as perpendicularity, parallelism, 0.02 A, or 0.05 Z. Box the full segmented rectangle.
```

`datum_symbol`

```txt
Small boxed capital datum letters such as A, B, X, or Z, often attached to a filled triangular datum marker or leader line. Box only the boxed letter label.
```

**Important**

With only 3 drawings, don’t expect YOLO training to be excellent yet. But this is enough to create a first prototype if you:

1. Upload the 90 tiles to Roboflow.
2. Run Auto Label.
3. Manually correct wrong boxes.
4. Train YOLO.
5. Test on the original full drawings.

For your case, the biggest win is: **label and train on tiles, not full pages**. The measurement text is too small on the full drawing.

---


**User**

give me exact details step on how to do this:

Upload the 90 tiles to Roboflow.
Run Auto Label.
Manually correct wrong boxes.
Train YOLO.
Test on the original full drawings.

---


**OpenAI Codex**

Yes. Follow this exact path.

Sources I checked: Roboflow upload, annotate, auto label, export, train, and visualize docs:  
https://docs.roboflow.com/adding-data/object-detection  
https://docs.roboflow.com/annotate/use-roboflow-annotate  
https://docs.roboflow.com/annotate/automated-annotation-with-autodistill  
https://docs.roboflow.com/datasets/exporting-data  
https://docs.roboflow.com/train/training-results

**1. Upload The 90 Tiles**
1. Open Roboflow: `https://app.roboflow.com`
2. Click **Create New Project**.
3. Set project type to **Object Detection**.
4. Project name:

```txt
OCR Drawing Detector
```

5. Add classes:

```txt
dimension_text
hole_circle
callout_text
title_block
surface_finish_symbol
gdt_frame
datum_symbol
```

6. Open the project.
7. Click **Upload Data**.
8. Drag all images from this folder:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\roboflow_upload\tiles
```

9. Wait until upload finishes.
10. If Roboflow asks how to assign images, choose to add them to an annotation batch or dataset. Use default split if unsure.

**2. Run Auto Label**
1. After upload, Roboflow may ask how you want to label the images.
2. Choose **Auto Label**.
3. If it does not show automatically, go to **Annotate** or the uploaded batch, then choose **Auto Label** / **AI Labeling**.
4. For each class, paste these prompts.

`dimension_text`

```txt
Small engineering measurement numbers and tolerance values near dimension lines, arrows, extension lines, or leader lines. Includes values such as 25, 35±0.2, 70±0.2, 90, 30, 5, 162.5, 2xR5, R6.3, C0.5, 4±0.05, Ø31.5, M4, M5. Do not label large note paragraphs, title block table text, revision table text, or company names.
```

`hole_circle`

```txt
Circular hole features on the mechanical part drawing. They appear as small circles, concentric circles, bolt holes, screw holes, or round cutouts in the part views. Label only the circular hole geometry, not surrounding dimensions or text.
```

`callout_text`

```txt
Short feature-specific manufacturing notes connected to holes, edges, or surfaces by leader lines. Includes text such as DRILL, HELICOIL, M4 depth, M5, drill through, undercut depth, screw depth, and similar short blue, red, or black callouts. Box the text block only, not the leader line.
```

`title_block`

```txt
Large rectangular drawing information table at the bottom right containing drawing number, part name, scale, material, revision, designer, approvals, and company information. Label the whole title block as one box.
```

`surface_finish_symbol`

```txt
Surface roughness symbols made from check-mark or triangular machining symbols with nearby Ra values such as Ra 25, Ra 6.3, Ra 3.2, Ra 1.6, or grouped surface finish marks. Box the symbol and its Ra value together when they belong to the same surface finish annotation.
```

`gdt_frame`

```txt
Geometric tolerance feature control frame shown as a rectangular segmented box containing symbols, tolerance values, and datum letters, such as perpendicularity, parallelism, 0.02 A, or 0.05 Z. Box the full segmented rectangle.
```

`datum_symbol`

```txt
Small boxed capital datum letters such as A, B, X, or Z, often attached to a filled triangular datum marker or leader line. Box only the boxed letter label.
```

5. Run Auto Label.
6. Wait until Roboflow creates boxes.

Important: Auto Label uses credits, and Roboflow says it works better for common visual objects. Your technical drawing text is niche, so expect mistakes.

**3. Manually Correct Wrong Boxes**
Open each tile in Roboflow Annotate.

For every tile, do this checklist:

```txt
Delete boxes on random table text.
Delete boxes on long note paragraphs if class is dimension_text.
Delete boxes around dimension lines only.
Resize boxes that are too large.
Add missing boxes around small measurement values.
Fix wrong class names.
```

Correct examples:

```txt
35±0.2       -> dimension_text
70±0.2       -> dimension_text
2xR5         -> dimension_text
Ø31.5        -> dimension_text
M4 depth 15  -> callout_text
DRILL        -> callout_text
small hole   -> hole_circle
0.02 A box   -> gdt_frame
boxed A      -> datum_symbol
```

Wrong examples:

```txt
whole drawing view -> dimension_text
title block words -> dimension_text
leader line only -> callout_text
revision table -> title_block
```

Minimum target before training:

```txt
At least 200-400 total corrected boxes
```

With only 3 drawings, quality matters more than quantity.

**4. Generate Dataset Version**
1. Go to **Versions**.
2. Click **Generate New Version**.
3. Preprocessing:

```txt
Auto-orient: ON
Resize: 1280 x 1280 or 1536 x 1536
```

For tiles, I suggest:

```txt
Resize: 1280 x 1280
```

4. Augmentation: keep very light.

Use:

```txt
Brightness: small
Contrast: small
Noise: small optional
```

Avoid:

```txt
large rotation
flip
heavy blur
strong crop
```

5. Click **Generate**.

**5. Train YOLO / Model**
You have two choices.

Easiest inside Roboflow:

1. Open the generated version.
2. Click **Train Model** or **Custom Train**.
3. Choose an object detection model.
4. If it offers **Roboflow Instant**, use it first for quick testing.
5. For proper training, choose a small/fast object detection model.
6. Start training.
7. Wait for Roboflow to finish.

Local YOLO training:

1. On the generated version, click **Export**.
2. Choose **YOLOv8 / Ultralytics** format.
3. Download zip.
4. Extract it to:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\dataset
```

5. Train:

```powershell
yolo detect train data=dataset\data.yaml model=yolov8n.pt epochs=100 imgsz=1280 batch=2 name=drawing_detector
```

If your PC is slow:

```powershell
yolo detect train data=dataset\data.yaml model=yolov8n.pt epochs=80 imgsz=960 batch=1 name=drawing_detector
```

**6. Test On Original Full Drawings**
First test inside Roboflow:

1. Go to the trained model.
2. Click **Visualize**.
3. Upload one original full drawing from:

```txt
C:\Users\izzuddin\Downloads
```

4. Check if it detects small numbers.

But better test using tiles, because your app also slices drawings. Full A2/A3 page detection may miss tiny text.

For your app:

1. Copy trained model:

```txt
runs\detect\drawing_detector\weights\best.pt
```

to:

```txt
C:\Users\izzuddin\Desktop\OCR DRAWING\backend\models\drawing_detector.pt
```

2. Run backend:

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING\backend"
$env:YOLO_MODEL_PATH="models/drawing_detector.pt"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. Run frontend:

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING\frontend"
npm run dev -- --host 127.0.0.1
```

4. Open:

```txt
http://127.0.0.1:5173
```

5. Upload original full drawing.

Best expectation: first model will be rough. The goal of model 1 is to show you what it misses, then you add/correct more labels and train model 2.

---


**User**

i think i cant do it. tell me step by step from early our system

---


**OpenAI Codex**

⚠️ **Codex Error**: Selected model is at capacity. Please try a different model.

---
