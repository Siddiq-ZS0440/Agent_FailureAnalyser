"""
Phase 3 Final - Allure HTML failure details extractor.

This script keeps the Phase 3 behavior and refactors the logic into separate methods:

1. fetch_total_test_count_from_overview
2. get_failed_suite_details
3. get_test_details_in_failed_suite
4. get_failed_test_case_details

All XPath locators are stored in an external JSON file.

Usage:
    python phase3_allure_failure_details_refactored.py <Allure_Report.html> [output_json_path] [locator_json_path]

Examples:
    python phase3_allure_failure_details_refactored.py "D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"

    python phase3_allure_failure_details_refactored.py "D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html" "D:\\Failure_Analyser\\allure_failure_details.json"

Install:
    pip install playwright selenium
    python -m playwright install chromium
"""

from __future__ import annotations

from pathlib import Path
import json
import sys
from typing import Any

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from selenium import webdriver  # noqa: F401 - imported for future Selenium phases


def load_locator_config(locator_json_path: str | None = None) -> dict[str, Any]:
    """Load XPath locator config from JSON."""
    if locator_json_path:
        config_path = Path(locator_json_path)
    else:
        config_path = Path(__file__).with_name("allure_phase3_locators.json")

    if not config_path.exists():
        raise FileNotFoundError(f"Locator JSON file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_timeout(config: dict[str, Any], key: str, default_value: int) -> int:
    """Read timeout/wait value from locator JSON."""
    return int(config.get("timeouts", {}).get(key, default_value))


def get_report_url(html_file_path: str) -> str:
    """Convert local HTML file path into file:// URL for Playwright."""
    html_path = Path(html_file_path)

    if not html_path.exists():
        raise FileNotFoundError(
            f"HTML report not found: {html_path}\n"
            "Pass the HTML path, for example:\n"
            "python phase3_allure_failure_details_refactored.py "
            '"D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"'
        )

    return html_path.resolve().as_uri()


def wait_for_report_to_load(page: Page, config: dict[str, Any]) -> None:
    """Wait until the HTML body and client-side report content are visible."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    initial_report_wait_ms = get_timeout(config, "initial_report_wait_ms", 3_000)

    page.wait_for_selector("xpath=//body", state="visible", timeout=default_timeout_ms)
    page.wait_for_timeout(initial_report_wait_ms)


def extract_first_integer(text: str) -> int | None:
    """Extract the first integer from text content."""
    number = ""

    for char in text:
        if char.isdigit():
            number += char
        elif number:
            break

    if not number:
        return None

    return int(number)


def get_text(locator: Locator, config: dict[str, Any]) -> str:
    """Get normalized text from a locator."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    return locator.inner_text(timeout=default_timeout_ms).strip()


def xpath_literal(text: str) -> str:
    """Return an XPath-safe string literal."""
    if "'" not in text:
        return f"'{text}'"

    if '"' not in text:
        return f'"{text}"'

    parts = text.split("'")
    return "concat(" + ', "\'", '.join([f"'{part}'" for part in parts]) + ")"


def click_direct_title(node: Locator, config: dict[str, Any]) -> None:
    """Click the direct node title for a suite or grouping node."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    direct_node_title_xpath = config["relative_node"]["direct_node_title_xpath"]

    title = node.locator(f"xpath={direct_node_title_xpath}").first
    title.scroll_into_view_if_needed(timeout=default_timeout_ms)
    title.click(timeout=default_timeout_ms)


def get_optional_text(page: Page, xpath: str, config: dict[str, Any]) -> str:
    """Get text from an optional right-side failure detail element."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    locator = page.locator(f"xpath={xpath}").first

    try:
        locator.wait_for(state="visible", timeout=default_timeout_ms)
        return locator.inner_text(timeout=default_timeout_ms).strip()
    except PlaywrightTimeoutError:
        return ""


def open_overview_section_if_present(page: Page, config: dict[str, Any]) -> bool:
    """Return True when Overview section exists; open it using an XPath locator."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    after_overview_click_wait_ms = get_timeout(config, "after_overview_click_wait_ms", 1_000)
    overview_section_xpath = config["overview"]["overview_section_xpath"]

    overview_section = page.locator(f"xpath={overview_section_xpath}").first

    try:
        overview_section.wait_for(state="visible", timeout=default_timeout_ms)
    except PlaywrightTimeoutError:
        return False

    overview_section.click()
    page.wait_for_timeout(after_overview_click_wait_ms)
    return True


def fetch_total_test_count_from_overview(page: Page, config: dict[str, Any]) -> int:
    """
    Fetch total number of test cases from the Overview section.

    Locator used from JSON:
        overview.total_test_count_xpath
    """
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)

    is_overview_present = open_overview_section_if_present(page, config)

    if not is_overview_present:
        print("Overview section present: No")
        print("Total test count: 0")
        return 0

    print("Overview section present: Yes")

    total_test_count_xpath = config["overview"]["total_test_count_xpath"]
    total_count_locator = page.locator(f"xpath={total_test_count_xpath}").first

    try:
        total_count_locator.wait_for(state="visible", timeout=default_timeout_ms)
        total_count_text = total_count_locator.inner_text(timeout=default_timeout_ms).strip()
        total_count = extract_first_integer(total_count_text)

        if total_count is not None:
            print(f"Total test count: {total_count}")
            return total_count

    except PlaywrightTimeoutError:
        pass

    print("Total test count: 0")
    return 0


def open_suites_section_if_present(page: Page, config: dict[str, Any]) -> bool:
    """Return True when Suites section exists; open it using an XPath locator."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    after_suites_click_wait_ms = get_timeout(config, "after_suites_click_wait_ms", 2_000)
    suites_section_xpath = config["suites"]["suites_section_xpath"]

    suites_section = page.locator(f"xpath={suites_section_xpath}").first

    try:
        suites_section.wait_for(state="visible", timeout=default_timeout_ms)
    except PlaywrightTimeoutError:
        return False

    suites_section.click()
    page.wait_for_timeout(after_suites_click_wait_ms)
    return True


def count_suites(page: Page, config: dict[str, Any]) -> int:
    """Count top-level suites using XPath locators from JSON."""
    top_level_suite_xpath = config["suites"]["top_level_suite_xpath"]
    top_level_suite_fallback_xpath = config["suites"]["top_level_suite_fallback_xpath"]

    suite_items = page.locator(f"xpath={top_level_suite_xpath}")
    suite_count = suite_items.count()

    if suite_count == 0:
        fallback_suite_items = page.locator(f"xpath={top_level_suite_fallback_xpath}")
        suite_count = fallback_suite_items.count()

    return suite_count


def get_failed_suite_details(page: Page, config: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Get suite details for suites that have failure labels.

    Returns:
        [
            {
                "suite_index": int,
                "suite_name": str,
                "suite_node": Locator
            }
        ]
    """
    is_suite_section_present = open_suites_section_if_present(page, config)

    if not is_suite_section_present:
        print("Suite section present: No")
        print("Suite count: 0")
        print("Failed suite count: 0")
        return []

    suite_count = count_suites(page, config)
    print("Suite section present: Yes")
    print(f"Suite count: {suite_count}")

    top_level_suite_node_xpath = config["suites"]["top_level_suite_node_xpath"]
    direct_node_name_xpath = config["relative_node"]["direct_node_name_xpath"]
    direct_failed_label_xpath = config["relative_node"]["direct_failed_label_xpath"]

    suite_nodes = page.locator(f"xpath={top_level_suite_node_xpath}")
    suite_node_count = suite_nodes.count()

    failed_suites = []

    for suite_index in range(suite_node_count):
        suite_node = suite_nodes.nth(suite_index)
        failed_label_count = suite_node.locator(f"xpath={direct_failed_label_xpath}").count()

        if failed_label_count == 0:
            continue

        suite_name = get_text(
            suite_node.locator(f"xpath={direct_node_name_xpath}").first,
            config,
        )

        failed_suites.append(
            {
                "suite_index": suite_index,
                "suite_name": suite_name,
                "suite_node": suite_node,
            }
        )

    print(f"Failed suite count: {len(failed_suites)}")
    for failed_suite in failed_suites:
        print(f"Failed suite: {failed_suite['suite_name']}")

    return failed_suites


def expand_failed_branches(page: Page, parent_node: Locator, config: dict[str, Any]) -> None:
    """
    Expand failed grouping nodes under the given parent until failed leaf tests are visible.

    This intentionally expands only nodes that have their own label_status_failed.
    It does not count these grouping nodes as failed tests.
    """
    collapsed_failed_branch_relative_xpath = config["failed_test_tree"]["collapsed_failed_branch_relative_xpath"]
    after_branch_click_wait_ms = get_timeout(config, "after_branch_click_wait_ms", 300)

    max_expand_attempts = 500

    for _ in range(max_expand_attempts):
        collapsed_failed_branch = parent_node.locator(
            f"xpath={collapsed_failed_branch_relative_xpath}"
        ).first

        if collapsed_failed_branch.count() == 0:
            break

        click_direct_title(collapsed_failed_branch, config)
        page.wait_for_timeout(after_branch_click_wait_ms)


def get_failed_leaf_parent_test_name(failed_test: Locator, config: dict[str, Any]) -> str:
    """Get the closest failed grouping/test name above the actual failed leaf test."""
    failed_leaf_parent_test_name_relative_xpath = (
        config["failed_test_tree"]["failed_leaf_parent_test_name_relative_xpath"]
    )
    parent_test_name = failed_test.locator(
        f"xpath={failed_leaf_parent_test_name_relative_xpath}"
    ).first

    try:
        return get_text(parent_test_name, config)
    except PlaywrightTimeoutError:
        return ""


def get_test_details_in_failed_suite(
    page: Page,
    suite_detail: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Get test details in one failed suite.

    This method:
        - clicks/expands the failed suite
        - expands failed grouping nodes
        - captures actual failed leaf test locators
        - returns failed test metadata for later detail extraction
    """
    after_suite_click_wait_ms = get_timeout(config, "after_suite_click_wait_ms", 500)
    suite_name = suite_detail["suite_name"]
    suite_node = suite_detail["suite_node"]

    print(f"\nSuite name: {suite_name}")

    click_direct_title(suite_node, config)
    page.wait_for_timeout(after_suite_click_wait_ms)

    expand_failed_branches(page, suite_node, config)

    failed_leaf_test_relative_xpath = config["failed_test_tree"]["failed_leaf_test_relative_xpath"]
    failed_leaf_test_case_name_relative_xpath = (
        config["failed_test_tree"]["failed_leaf_test_case_name_relative_xpath"]
    )

    failed_leaf_tests = suite_node.locator(f"xpath={failed_leaf_test_relative_xpath}")
    failed_leaf_count = failed_leaf_tests.count()

    print(f"Actual failed test count in suite '{suite_name}': {failed_leaf_count}")

    failed_tests = []

    for failed_test_index in range(failed_leaf_count):
        failed_test = failed_leaf_tests.nth(failed_test_index)

        failed_test_case_name = get_text(
            failed_test.locator(f"xpath={failed_leaf_test_case_name_relative_xpath}").first,
            config,
        )

        failed_test_name = get_failed_leaf_parent_test_name(failed_test, config)

        failed_tests.append(
            {
                "suite_name": suite_name,
                "failed_test_index": failed_test_index,
                "failed_test_name": failed_test_name,
                "failed_test_case_name": failed_test_case_name,
                "failed_test_locator": failed_test,
            }
        )

    return failed_tests


def wait_for_failed_test_in_right_panel(
    page: Page,
    failed_test_case_name: str,
    config: dict[str, Any],
) -> None:
    """Wait until the clicked failed test case name is present in right-side content."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    failed_test_case_name_literal = xpath_literal(failed_test_case_name)

    right_test_name_xpath = config["right_panel"]["failed_test_name_loaded_xpath_template"].replace(
        "{failed_test_case_name_literal}",
        failed_test_case_name_literal,
    )

    page.wait_for_selector(
        f"xpath={right_test_name_xpath}",
        state="visible",
        timeout=default_timeout_ms,
    )


def get_failure_details_from_right_panel(
    page: Page,
    failed_test_case_name: str,
    config: dict[str, Any],
) -> tuple[str, str]:
    """Get status-details__message and status-details__trace from right-side content."""
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    right_status_message_xpath = config["right_panel"]["status_message_xpath"]
    right_status_trace_xpath = config["right_panel"]["status_trace_xpath"]

    wait_for_failed_test_in_right_panel(page, failed_test_case_name, config)

    failure_message_locator = page.locator(f"xpath={right_status_message_xpath}").first
    failure_message_locator.wait_for(state="visible", timeout=default_timeout_ms)
    failure_message = failure_message_locator.inner_text(timeout=default_timeout_ms).strip()

    failure_message_locator.click(timeout=default_timeout_ms)

    failure_trace = get_optional_text(page, right_status_trace_xpath, config)

    return failure_message, failure_trace


def get_failed_test_case_details(
    page: Page,
    failed_test_detail: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, str] | None:
    """
    Get failed test case details along with failure message and stack trace.

    This method clicks the actual failed leaf test case, waits for the right panel,
    reads status-details__message, clicks it, and reads status-details__trace.
    """
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)
    after_failed_leaf_click_wait_ms = get_timeout(config, "after_failed_leaf_click_wait_ms", 300)

    suite_name = failed_test_detail["suite_name"]
    failed_test_name = failed_test_detail["failed_test_name"]
    failed_test_case_name = failed_test_detail["failed_test_case_name"]
    failed_test_locator = failed_test_detail["failed_test_locator"]

    failed_leaf_status_relative_xpath = config["failed_test_tree"]["failed_leaf_status_relative_xpath"]

    failed_test_locator.scroll_into_view_if_needed(timeout=default_timeout_ms)
    failed_test_locator.click(timeout=default_timeout_ms)
    page.wait_for_timeout(after_failed_leaf_click_wait_ms)

    failed_status_count = failed_test_locator.locator(
        f"xpath={failed_leaf_status_relative_xpath}"
    ).count()

    if failed_status_count == 0:
        print(
            f"  Skipped test case: {failed_test_case_name} "
            "because text_status_failed was not found under node__leaf"
        )
        return None

    failure_message, failure_trace = get_failure_details_from_right_panel(
        page,
        failed_test_case_name,
        config,
    )

    print(f"  Failed test: {failed_test_name}")
    print(f"    Failed test case: {failed_test_case_name}")
    print("    status-details__message:")
    print(f"    {failure_message}")
    print("    status-details__trace:")
    print(f"    {failure_trace}")

    return {
        "test_name": f"{suite_name} > {failed_test_name} > {failed_test_case_name}",
        "status": "Failed",
        "failure_message": failure_message,
        "stack_trace": failure_trace,
    }


def build_failure_details_json(
    html_file_path: str,
    report_name: str,
    total_test_count: int,
    failed_test_list: list[dict[str, str]],
) -> dict[str, Any]:
    """Build final JSON output."""
    html_path = Path(html_file_path)

    return {
        "source_html_file": html_path.name,
        "source_html_path": str(html_path.resolve()),
        "report_type": "allure",
        "report_name": report_name,
        "total_test_count": total_test_count,
        "failed_test_count": len(failed_test_list),
        "failed_test_list": failed_test_list,
    }


def resolve_output_json_path(html_file_path: str, output_json_path: str | None) -> Path:
    """Resolve output JSON path."""
    if output_json_path:
        return Path(output_json_path)

    return Path(html_file_path).with_suffix(".failure_details.json")


def main() -> None:
    if len(sys.argv) < 2:
        raise ValueError(
            "Please provide the HTML report path.\n"
            "Example:\n"
            "python phase3_allure_failure_details_refactored.py "
            '"D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"'
        )

    html_file_path = sys.argv[1]
    output_json_path = sys.argv[2] if len(sys.argv) >= 3 else None
    locator_json_path = sys.argv[3] if len(sys.argv) >= 4 else None

    config = load_locator_config(locator_json_path)

    navigation_timeout_ms = get_timeout(config, "navigation_timeout_ms", 120_000)
    default_timeout_ms = get_timeout(config, "default_timeout_ms", 120_000)

    report_url = get_report_url(html_file_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.set_default_timeout(default_timeout_ms)
        page.set_default_navigation_timeout(navigation_timeout_ms)

        try:
            page.goto(
                report_url,
                wait_until="domcontentloaded",
                timeout=navigation_timeout_ms,
            )

            wait_for_report_to_load(page, config)

            total_test_count = fetch_total_test_count_from_overview(page, config)

            failed_suite_details = get_failed_suite_details(page, config)

            failed_suite_summary = []
            failed_test_list = []

            for suite_detail in failed_suite_details:
                failed_tests_in_suite = get_test_details_in_failed_suite(
                    page,
                    suite_detail,
                    config,
                )

                failed_suite_summary.append(
                    (
                        suite_detail["suite_name"],
                        len(failed_tests_in_suite),
                    )
                )

                for failed_test_detail in failed_tests_in_suite:
                    failed_case_details = get_failed_test_case_details(
                        page,
                        failed_test_detail,
                        config,
                    )

                    if failed_case_details is not None:
                        failed_test_list.append(failed_case_details)

            print("\nFinal failed suite summary:")
            if len(failed_suite_summary) == 0:
                print("No failed suites found")
            else:
                for suite_name, failed_test_count in failed_suite_summary:
                    print(f"{suite_name}: {failed_test_count}")

            failure_details_json = build_failure_details_json(
                html_file_path=html_file_path,
                report_name=page.title(),
                total_test_count=total_test_count,
                failed_test_list=failed_test_list,
            )

            output_path = resolve_output_json_path(html_file_path, output_json_path)
            output_path.write_text(
                json.dumps(failure_details_json, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print(f"\nJSON output file: {output_path.resolve()}")

        except PlaywrightTimeoutError as error:
            print("Timed out while opening or reading the report.")
            print("Reason: the report is large or the UI did not render within the configured timeout.")
            print(f"Error details: {error}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
