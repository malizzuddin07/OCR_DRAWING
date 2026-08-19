# OCR DRAWING - Main System

This folder contains only the code and files needed to run the OCR DRAWING web system in deployment.

Development-only training, golden-test, dataset-building, review, and experiment scripts are intentionally excluded.

## Run on Windows

1. Open PowerShell in this folder.
2. Create and activate a Python 3.11 virtual environment.
3. Install dependencies.
4. Copy `.env.example` to `.env` and configure the required model/API settings.
5. Start the server.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\START_SYSTEM.ps1
```

Open `http://127.0.0.1:8001`.

## Important folders

- `code/`: OCR and ballooning runtime modules.
- `webapp/`: FastAPI server and browser interface.
- `generated_jobs/`: runtime output; safe to clear only when no job is running.
- `private_data/`: approval records and the model registry. Back this up.
- `models/`: local YOLO candidates copied from the protected V3, V7, and V8 models.

The deployment package does not include golden drawings, training datasets, test scripts, checkpoints, or experiment outputs.
