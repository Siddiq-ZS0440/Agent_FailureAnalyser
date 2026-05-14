from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LogCallback = Optional[Callable[[str], None]]


def _emit(logger: LogCallback, message: str) -> None:
    if logger:
        logger(message)


class FailureCategorizer:
    def __init__(self, categorization_path: str = "failure_categorization.json", logger: LogCallback = None):
        self.categorization_path = Path(categorization_path)
        self.logger = logger
        self.config = self._load_config()
        _emit(self.logger, f"Loaded categorization config from {self.categorization_path}")

    def _load_config(self) -> Dict[str, Any]:
        with self.categorization_path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def categorize(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        categorized_failed_test_list: List[Dict[str, Any]] = []
        summary: Dict[str, int] = {}

        for failed_test in extracted_result.get("failed_test_list", []):
            category = self._categorize_failed_test(failed_test)
            categorized_test = dict(failed_test)
            categorized_test["failure_category"] = category
            categorized_failed_test_list.append(categorized_test)
            summary[category] = summary.get(category, 0) + 1

        _emit(self.logger, f"Categorized {len(categorized_failed_test_list)} failed test(s) into {len(summary)} category bucket(s)")
        return {
            "source_html_file": extracted_result.get("source_html_file", ""),
            "source_html_path": extracted_result.get("source_html_path", ""),
            "report_type": extracted_result.get("report_type", ""),
            "report_name": extracted_result.get("report_name", ""),
            "total_test_count": extracted_result.get("total_test_count", 0),
            "failed_test_count": extracted_result.get("failed_test_count", 0),
            "failure_category_summary": summary,
            "categorized_failed_test_list": categorized_failed_test_list,
        }

    def _categorize_failed_test(self, failed_test: Dict[str, Any]) -> str:
        combined_text = " ".join(
            part for part in [
                failed_test.get("test_name", ""),
                failed_test.get("failure_message", ""),
            ]
            if part
        )

        stack_trace = failed_test.get("stack_trace", "")
        default_category = self.config.get("default_category", "Unknown")

        for category in self.config.get("categories", []):
            category_name = category.get("name", default_category)

            for pattern in category.get("trace_patterns", []):
                if re.search(pattern, stack_trace, re.IGNORECASE):
                    _emit(self.logger, f"TRACE MATCH -> {category_name}: {pattern}")
                    return category_name

            for pattern in category.get("message_patterns", []):
                if re.search(pattern, combined_text, re.IGNORECASE):
                    _emit(self.logger, f"MESSAGE MATCH -> {category_name}: {pattern}")
                    return category_name

        _emit(self.logger, f"No match found for test '{failed_test.get('test_name', '')}'. Using default category '{default_category}'")
        return default_category


def run_categorization(
    extracted_json: str,
    categorization: str = "failure_categorization.json",
    output: str = "",
    logger: LogCallback = None,
) -> Path:
    extracted_json_path = Path(extracted_json).resolve()
    _emit(logger, f"Reading extraction JSON: {extracted_json_path}")
    extracted_result = json.loads(extracted_json_path.read_text(encoding="utf-8"))

    categorizer = FailureCategorizer(categorization, logger=logger)
    categorized_result = categorizer.categorize(extracted_result)

    output_path = Path(output) if output else extracted_json_path.parent / "report_failure_categorization.json"
    output_path.write_text(json.dumps(categorized_result, indent=2, ensure_ascii=False), encoding="utf-8")
    _emit(logger, f"Wrote categorization output to {output_path}")
    return output_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Categorize failures from extracted report JSON.")
    parser.add_argument("extracted_json", help="Path to report_failure_details.json")
    parser.add_argument("--categorization", default="failure_categorization.json", help="Path to failure categorization JSON file")
    parser.add_argument("--output", default="", help="Output JSON file path")
    args = parser.parse_args()

    output_path = run_categorization(
        extracted_json=args.extracted_json,
        categorization=args.categorization,
        output=args.output,
        logger=print,
    )
    print(str(output_path))


if __name__ == "__main__":
    main()
