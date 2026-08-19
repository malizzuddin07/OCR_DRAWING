import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from auto_ballooning import process_single_drawing


def process_single_drawing_for_web(pdf_file_path, job_dir):
    """
    Run one uploaded drawing through the balloon/FA-report workflow.

    The return value is intentionally web-friendly: the server can turn the
    generated paths into browser URLs without knowing OCR internals.
    """
    return process_single_drawing(
        pdf_path=Path(pdf_file_path),
        job_dir=Path(job_dir),
        use_cache=False,
    )
