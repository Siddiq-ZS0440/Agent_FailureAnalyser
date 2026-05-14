from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

from report_failure_categorizer_v1 import run_categorization
from report_failure_excel_generator_v1 import generate_excel
from report_failure_extractor_v1 import run_extraction

UiCallback = Optional[Callable[[str], None]]


class PipelineLogger:
    def __init__(self, run_dir: Path, ui_callback: UiCallback = None):
        self.run_dir = run_dir
        self.ui_callback = ui_callback
        self.log_path = self.run_dir / "analysis.log"
        self._logger = logging.getLogger(f"report_pipeline_{self.run_dir.name}_{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._logger.handlers.clear()

        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

    def __call__(self, message: str) -> None:
        self._logger.info(message)
        if self.ui_callback:
            self.ui_callback(message)

    def close(self) -> None:
        handlers = list(self._logger.handlers)
        for handler in handlers:
            handler.flush()
            handler.close()
            self._logger.removeHandler(handler)


def create_run_dir(results_root: str = "Results") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(results_root) / f"Run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir.resolve()


def run_pipeline(
    html_report: str,
    report_type: str = "",
    profile_index: str = "report_profiles.json",
    profiles_dir: str = "profiles",
    categorization_config: str = "failure_categorization.json",
    results_root: str = "Results",
    ui_callback: UiCallback = None,
) -> Dict[str, object]:
    run_dir = create_run_dir(results_root)
    logger = PipelineLogger(run_dir, ui_callback=ui_callback)

    try:
        logger(f"Created run directory: {run_dir}")
        logger("Stage 1/3: Starting extraction")
        extraction_json = run_extraction(
            html_report=html_report,
            profile_index=profile_index,
            profiles_dir=profiles_dir,
            output=str(run_dir / "report_failure_details.json"),
            run_dir=str(run_dir),
            forced_report_type=report_type,
            logger=logger,
        )

        logger("Stage 2/3: Starting categorization")
        categorization_json = run_categorization(
            extracted_json=str(extraction_json),
            categorization=categorization_config,
            output=str(run_dir / "report_failure_categorization.json"),
            logger=logger,
        )

        logger("Stage 3/3: Starting Excel generation")
        excel_path = generate_excel(
            input_json_path=str(categorization_json),
            output_excel_path=str(run_dir / "report_failure_categorization.xlsx"),
            logger=logger,
        )

        categorized_data = json.loads(Path(categorization_json).read_text(encoding="utf-8"))
        logger("Pipeline completed successfully")
        return {
            "run_dir": str(run_dir),
            "log_path": str(logger.log_path),
            "extraction_json": str(extraction_json),
            "categorization_json": str(categorization_json),
            "excel_path": str(excel_path),
            "categorized_data": categorized_data,
        }
    finally:
        logger.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run extractor, categorizer, and Excel generator in sequence.")
    parser.add_argument("html_report", help="Path to the HTML report file")
    parser.add_argument("--report-type", default="", help="Optional report type/profile name to force. If omitted, auto-detection is used.")
    parser.add_argument("--profile-index", default="report_profiles.json", help="Path to report_profiles.json")
    parser.add_argument("--profiles-dir", default="profiles", help="Path to profiles folder")
    parser.add_argument("--categorization", default="failure_categorization.json", help="Path to failure_categorization.json")
    parser.add_argument("--results-root", default="Results", help="Folder where Run_<timestamp> will be created")
    args = parser.parse_args()

    result = run_pipeline(
        html_report=args.html_report,
        report_type=args.report_type,
        profile_index=args.profile_index,
        profiles_dir=args.profiles_dir,
        categorization_config=args.categorization,
        results_root=args.results_root,
        ui_callback=print,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
