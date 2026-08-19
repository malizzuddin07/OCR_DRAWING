# OCR DRAWING - Development Workspace

The original OCR DRAWING project root remains the development workspace.

Development items include:

- detector training scripts;
- dataset preparation and label-review scripts;
- golden-test runners and quality gates;
- confidence sweeps and model comparisons;
- tests, checkpoints, training packages, and approved golden references.

Use `main_system/` for deployment. Make code changes and run quality gates in the development workspace first, then rebuild or refresh the deployment package only after validation.

Do not train models or run golden experiments inside `main_system/`.
