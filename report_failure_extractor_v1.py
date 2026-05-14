from __future__ import annotations

import argparse
import json
import re
import shutil
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Iterator, Tuple
from urllib.parse import quote, urljoin

from lxml import etree, html

LogCallback = Optional[Callable[[str], None]]


def _emit(logger: LogCallback, message: str) -> None:
    if logger:
        logger(message)


@dataclass
class FailedTestRecord:
    test_name: str = ""
    status: str = ""
    failure_message: str = ""
    stack_trace: str = ""


@dataclass
class ReportExtraction:
    source_html_file: str
    source_html_path: str
    report_type: str
    report_name: str
    total_test_count: int
    failed_test_count: int
    failed_test_list: List[Dict[str, Any]]


class ProfileDrivenReportAnalyzer:
    def __init__(
        self,
        profile_index_path: str = "report_profiles.json",
        profiles_dir: str = "profiles",
        runtime_profile_path: str = "",
        logger: LogCallback = None,
    ):
        self.profile_index_path = Path(profile_index_path)
        self.profiles_dir = Path(profiles_dir)
        self.runtime_profile_path = Path(runtime_profile_path) if runtime_profile_path else None
        self.logger = logger
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        if self.runtime_profile_path:
            self.profiles = self._load_runtime_profile_and_save(self.runtime_profile_path)
            self.force_runtime_profile = True
        else:
            self.profiles = self._load_profiles_for_detection()
            self.force_runtime_profile = False
        _emit(self.logger, f"Loaded {len(self.profiles)} profile(s) from {self.profiles_dir}")

    def list_available_report_types(self) -> List[str]:
        return [profile.get("profile_name", "") for profile in self.profiles if profile.get("profile_name")]

    def analyze(self, html_path: str, forced_report_type: str = "") -> Dict[str, Any]:
        html_path_obj = Path(html_path)
        _emit(self.logger, f"Reading HTML report: {html_path_obj}")
        content = html_path_obj.read_text(encoding="utf-8", errors="ignore")
        tree = html.fromstring(content)

        if forced_report_type:
            profile = self._get_profile_by_name(forced_report_type)
            if not profile:
                raise ValueError(f"Report type '{forced_report_type}' was not found in the loaded profiles.")
            _emit(self.logger, f"Using user-selected report type: {forced_report_type}")
        elif self.force_runtime_profile and len(self.profiles) == 1:
            profile = self.profiles[0]
            _emit(self.logger, f"Using runtime profile: {profile.get('profile_name', 'unknown')}")
        else:
            profile = self._detect_profile(tree, content)
            _emit(self.logger, f"Auto-detected report type: {profile.get('profile_name', 'unknown')}")

        return asdict(self._extract_using_profile(tree, html_path_obj, profile))

    def _get_profile_by_name(self, profile_name: str) -> Optional[Dict[str, Any]]:
        for profile in self.profiles:
            if profile.get("profile_name", "").lower() == profile_name.lower():
                return profile
        return None

    def _load_runtime_profile_and_save(self, runtime_profile_path: Path) -> List[Dict[str, Any]]:
        payload = self._load_json(runtime_profile_path)
        profiles = self._normalize_profile_payload(payload, runtime_profile_path)
        saved_profiles: List[Dict[str, Any]] = []
        for profile in profiles:
            profile_name = self._safe_profile_name(profile.get("profile_name") or runtime_profile_path.stem)
            profile["profile_name"] = profile_name
            destination = self.profiles_dir / f"{profile_name}.json"
            destination.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
            _emit(self.logger, f"Saved runtime profile to {destination}")
            saved_profiles.append(profile)
        return saved_profiles

    def _load_profiles_for_detection(self) -> List[Dict[str, Any]]:
        profile_index = self._load_profile_index()
        loaded_by_name: Dict[str, Dict[str, Any]] = {}
        for profile_file in profile_index.get("profile_files", []):
            path = self._resolve_profile_path(profile_file)
            if path.exists():
                for profile in self._normalize_profile_payload(self._load_json(path), path):
                    loaded_by_name[profile["profile_name"]] = profile
        for path in sorted(self.profiles_dir.glob("*.json")):
            for profile in self._normalize_profile_payload(self._load_json(path), path):
                loaded_by_name[profile["profile_name"]] = profile
        profiles = list(loaded_by_name.values())
        load_order = profile_index.get("profile_load_order", [])
        order_lookup = {name: index for index, name in enumerate(load_order)}
        profiles.sort(key=lambda item: (order_lookup.get(item.get("profile_name", ""), 999), item.get("priority", 999)))
        return profiles

    def _load_profile_index(self) -> Dict[str, Any]:
        if not self.profile_index_path.exists():
            return {"profile_files": [], "profile_load_order": []}
        return self._load_json(self.profile_index_path)

    def _resolve_profile_path(self, profile_file: str) -> Path:
        path = Path(profile_file)
        return path if path.is_absolute() else self.profile_index_path.parent / path

    def _load_json(self, path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def _normalize_profile_payload(self, payload: Dict[str, Any], source_path: Path) -> List[Dict[str, Any]]:
        if "profiles" in payload and isinstance(payload["profiles"], dict):
            profiles: List[Dict[str, Any]] = []
            for profile_name, profile in payload["profiles"].items():
                if isinstance(profile, dict):
                    normalized = dict(profile)
                    normalized["profile_name"] = normalized.get("profile_name", profile_name)
                    profiles.append(normalized)
            return profiles
        normalized = dict(payload)
        normalized["profile_name"] = normalized.get("profile_name", source_path.stem)
        return [normalized]

    def _safe_profile_name(self, value: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
        return value or "custom_generated"

    def _detect_profile(self, tree: etree._Element, content: str) -> Dict[str, Any]:
        lowered = content.lower()
        generic_profile: Optional[Dict[str, Any]] = None
        for profile in self.profiles:
            if profile.get("profile_name") == "generic_html":
                generic_profile = profile
                continue
            detection = profile.get("detection", {})
            for marker in detection.get("contains_text", []):
                if marker.lower() in lowered:
                    return profile
            for xpath_expr in detection.get("xpaths", []):
                try:
                    if tree.xpath(xpath_expr):
                        return profile
                except etree.XPathError:
                    continue
        if generic_profile:
            return generic_profile
        raise ValueError("No matching profile found and generic_html profile is not available.")

    def _extract_using_profile(self, tree: etree._Element, html_path_obj: Path, profile: Dict[str, Any]) -> ReportExtraction:
        report_name = self._extract_value(tree, profile.get("report", {}).get("name", {}), html_path_obj.stem)
        records_config = profile.get("records", {})
        record_nodes = self._all_nodes(tree, self._get_root_xpaths(records_config))
        _emit(self.logger, f"Found {len(record_nodes)} candidate record node(s)")
        failed_test_list: List[Dict[str, Any]] = []
        total_test_count = self._extract_total_test_count(tree, records_config, len(record_nodes))
        for record_node in record_nodes:
            extracted_fields = self._extract_record_fields(record_node, records_config.get("fields", {}))
            filter_config = records_config.get("filter", {})
            filter_field = filter_config.get("field", "")
            if filter_field in extracted_fields and not self._record_matches_filter(extracted_fields, filter_config):
                continue

            for detail_root in self._resolve_detail_roots(tree, record_node, records_config.get("detail_context", {})):
                detail_fields = self._extract_record_fields(detail_root, records_config.get("detail_fields", {}))
                for field_name, value in detail_fields.items():
                    if value:
                        extracted_fields[field_name] = value

            if filter_field not in extracted_fields and not self._record_matches_filter(extracted_fields, filter_config):
                continue

            failed_test_list.append(
                asdict(
                    FailedTestRecord(
                        test_name=extracted_fields.get("test_name", ""),
                        status=extracted_fields.get("status", ""),
                        failure_message=extracted_fields.get("failure_message", ""),
                        stack_trace=extracted_fields.get("stack_trace", ""),
                    )
                )
            )
        failed_test_count = self._extract_failed_test_count(tree, records_config, len(failed_test_list))
        _emit(self.logger, f"Extraction completed with {failed_test_count} failed test(s)")
        return ReportExtraction(
            source_html_file=html_path_obj.name,
            source_html_path=str(html_path_obj.resolve()),
            report_type=profile.get("profile_name", "unknown"),
            report_name=report_name,
            total_test_count=total_test_count,
            failed_test_count=failed_test_count,
            failed_test_list=failed_test_list,
        )

    def _get_root_xpaths(self, records_config: Dict[str, Any]) -> List[str]:
        if "root_xpaths" in records_config:
            return records_config.get("root_xpaths", [])
        root_xpath = records_config.get("root_xpath", "")
        return [root_xpath] if root_xpath else []

    def _extract_record_fields(self, root: etree._Element, fields_config: Dict[str, Any]) -> Dict[str, str]:
        extracted: Dict[str, str] = {}
        for field_name, field_config in fields_config.items():
            extracted[field_name] = self._extract_value(root, field_config, field_config.get("default", ""))
        return extracted

    def _resolve_detail_roots(self, tree: etree._Element, record_node: etree._Element, detail_context: Dict[str, Any]) -> List[etree._Element]:
        if not detail_context:
            return []
        link_value = self._extract_value(record_node, {"xpaths": [detail_context.get("link_xpath", "")]}, "")
        if not link_value:
            return []
        link_value = self._apply_transforms(link_value, detail_context.get("transforms", []))
        target_xpaths = list(detail_context.get("target_xpath_templates", []))
        if detail_context.get("target_xpath_template"):
            target_xpaths.append(detail_context["target_xpath_template"])
        resolved_xpaths = []
        for xpath_template in target_xpaths:
            try:
                resolved_xpaths.append(xpath_template.format(value=link_value))
            except KeyError:
                resolved_xpaths.append(xpath_template)
        return self._all_nodes(tree, resolved_xpaths)

    def _extract_total_test_count(self, tree: etree._Element, records_config: Dict[str, Any], fallback_count: int) -> int:
        count_config = records_config.get("total_test_count", {})
        value = self._extract_value(tree, count_config, "")
        if value:
            match = re.search(r"\d+", value)
            if match:
                return int(match.group(0))
        return fallback_count

    def _extract_failed_test_count(self, tree: etree._Element, records_config: Dict[str, Any], fallback_count: int) -> int:
        count_config = records_config.get("failed_test_count", {})
        value = self._extract_value(tree, count_config, "")
        if value:
            match = re.search(r"\d+", value)
            if match:
                return int(match.group(0))
        return fallback_count

    def _record_matches_filter(self, fields: Dict[str, str], filter_config: Dict[str, Any]) -> bool:
        if not filter_config:
            return True
        field_name = filter_config.get("field", "")
        operator = filter_config.get("operator", "equals_ignore_case")
        expected_value = str(filter_config.get("value", ""))
        actual_value = str(fields.get(field_name, ""))
        if operator == "equals":
            return actual_value == expected_value
        if operator == "equals_ignore_case":
            return actual_value.lower() == expected_value.lower()
        if operator == "contains":
            return expected_value in actual_value
        if operator == "contains_ignore_case":
            return expected_value.lower() in actual_value.lower()
        if operator == "regex":
            return re.search(expected_value, actual_value, re.IGNORECASE) is not None
        if operator == "not_empty":
            return bool(actual_value.strip())
        return True

    def _extract_value(self, root: etree._Element, value_config: Dict[str, Any], default: str = "") -> str:
        for xpath_expr in value_config.get("xpaths", []):
            if not xpath_expr:
                continue
            try:
                result = root.xpath(xpath_expr)
            except etree.XPathError:
                continue
            value = self._stringify_xpath_result(result)
            value = self._clean_text(value)
            value = self._apply_transforms(value, value_config.get("transforms", []))
            if value:
                return value
        return default

    def _all_nodes(self, root: etree._Element, xpaths: List[str]) -> List[etree._Element]:
        nodes: List[etree._Element] = []
        for xpath_expr in xpaths:
            if not xpath_expr:
                continue
            try:
                results = root.xpath(xpath_expr)
            except etree.XPathError:
                continue
            if not isinstance(results, list):
                results = [results]
            for result in results:
                if isinstance(result, etree._Element):
                    nodes.append(result)
        return nodes

    def _stringify_xpath_result(self, result: Any) -> str:
        if isinstance(result, list):
            if not result:
                return ""
            return self._stringify_xpath_result(result[0])
        if isinstance(result, etree._ElementUnicodeResult):
            return str(result)
        if isinstance(result, etree._Element):
            return " ".join(result.itertext())
        return str(result) if result is not None else ""

    def _clean_text(self, value: str) -> str:
        value = value or ""
        value = html.fromstring(f"<div>{value}</div>").text_content() if "<" in value and ">" in value else value
        return re.sub(r"\s+", " ", value).strip()

    def _apply_transforms(self, value: str, transforms: List[Dict[str, Any]]) -> str:
        for transform in transforms:
            transform_type = transform.get("type", "")
            if transform_type == "strip_prefix":
                prefix = str(transform.get("value", ""))
                if value.startswith(prefix):
                    value = value[len(prefix):]
            elif transform_type == "strip_suffix":
                suffix = str(transform.get("value", ""))
                if value.endswith(suffix):
                    value = value[:-len(suffix)]
            elif transform_type == "replace":
                value = value.replace(str(transform.get("old", "")), str(transform.get("new", "")))
            elif transform_type == "replace_regex":
                value = re.sub(str(transform.get("pattern", "")), str(transform.get("replacement", "")), value)
            elif transform_type == "lower":
                value = value.lower()
            elif transform_type == "upper":
                value = value.upper()
            elif transform_type == "trim":
                value = value.strip()
            elif transform_type == "extract_regex_group":
                match = re.search(str(transform.get("pattern", "")), value)
                group_index = int(transform.get("group", 1))
                value = match.group(group_index) if match else ""
        return value


def run_extraction(
    html_report: str,
    profile_index: str = "report_profiles.json",
    profiles_dir: str = "profiles",
    runtime_profile: str = "",
    output: str = "",
    run_dir: str = "",
    forced_report_type: str = "",
    logger: LogCallback = None,
) -> Path:
    analyzer = ProfileDrivenReportAnalyzer(
        profile_index_path=profile_index,
        profiles_dir=profiles_dir,
        runtime_profile_path=runtime_profile,
        logger=logger,
    )
    result = analyzer.analyze(html_report, forced_report_type=forced_report_type)

    html_report_path = Path(html_report).resolve()
    if run_dir:
        run_folder = Path(run_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = Path("Results") / f"Run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_report_path, run_folder / html_report_path.name)
    _emit(logger, f"Copied source report to {run_folder / html_report_path.name}")

    output_path = Path(output) if output else run_folder / "report_failure_details.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _emit(logger, f"Wrote extraction output to {output_path}")
    return output_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract failed-test details from an HTML automation report using JSON profiles.")
    parser.add_argument("html_report", help="Path to HTML report")
    parser.add_argument("--profile", default="", help="Optional runtime profile JSON. If passed, it is saved into the profiles folder and used for this run.")
    parser.add_argument("--report-type", default="", help="Optional report type/profile name to force, e.g. testng_custom")
    parser.add_argument("--profile-index", default="report_profiles.json", help="Profile index JSON used when --profile is not passed")
    parser.add_argument("--profiles-dir", default="profiles", help="Folder containing individual report profile JSON files")
    parser.add_argument("--output", default="", help="Optional output JSON file path")
    parser.add_argument("--run-dir", default="", help="Optional run directory. If omitted, Results/Run_<timestamp> is created.")
    args = parser.parse_args()

    output_path = run_extraction(
        html_report=args.html_report,
        profile_index=args.profile_index,
        profiles_dir=args.profiles_dir,
        runtime_profile=args.profile,
        output=args.output,
        run_dir=args.run_dir,
        forced_report_type=args.report_type,
        logger=print,
    )
    print(str(output_path))


if __name__ == "__main__":
    main()
