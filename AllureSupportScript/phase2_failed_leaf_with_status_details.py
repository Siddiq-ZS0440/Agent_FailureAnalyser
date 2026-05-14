"""
Phase 2 - Open an existing Allure HTML report, navigate to Suites,
expand failed suite/test branches, and count only actual failed leaf tests using XPath.

Usage:
    python phase2_failed_leaf_with_status_details.py /path/to/Allure_Report.html

Install:
    pip install playwright selenium
    python -m playwright install chromium

Notes:
    - This script assumes you already have the HTML report locally.
    - No zip extraction is performed.
    - Playwright opens the report in headed mode.
    - XPath locators are used for Suites section detection, suite traversal,
      failed label detection, failed branch expansion, and failed leaf-test counting.
"""

from pathlib import Path
import sys

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from selenium import webdriver  # noqa: F401 - imported for future Selenium phases


# Timeout values in milliseconds
NAVIGATION_TIMEOUT_MS = 120_000
DEFAULT_TIMEOUT_MS = 120_000


# XPath locator to identify whether the Suites section exists in the Allure report UI.
SUITES_SECTION_XPATH = (
    "//a[contains(@href, '#suites') "
    "or .//*[normalize-space()='Suites'] "
    "or normalize-space()='Suites']"
)


# XPath locator to count top-level suite rows once the Suites section is opened.
# This targets Allure-style tree rows and excludes nested child rows.
TOP_LEVEL_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[@class='node']//div[@class='node__name'][not(ancestor::div[@class='node__children'])]"
)


# Fallback XPath for report variants where the top-level suite row is rendered
# as a node/container rather than a direct tree__item element.
TOP_LEVEL_SUITE_FALLBACK_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' tree__node ') "
    "and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' tree__children ')])]"
)


# Top-level suite node element. This is used as the parent for all relative lookups.
TOP_LEVEL_SUITE_NODE_XPATH = (
    "//div[@class='side-by-side__left']"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' node ')]"
    "[./div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
    "[.//div[@class='node__name']]]"
    "[not(ancestor::div[@class='node__children'])]"
)


# Relative locators from suite/test parent elements.
DIRECT_NODE_TITLE_XPATH = "./div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
DIRECT_NODE_NAME_XPATH = DIRECT_NODE_TITLE_XPATH + "//div[@class='node__name']"
DIRECT_FAILED_LABEL_XPATH = DIRECT_NODE_TITLE_XPATH + "//span[contains(@class, 'label_status_failed')]"


# A failed branch is a non-leaf node that has a failed label in its own title.
# These are grouping nodes, not final failed tests. They must be expanded until
# the actual <a class="node node__leaf"> failed test becomes available.
COLLAPSED_FAILED_BRANCH_RELATIVE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' node ')]"
    "[not(contains(concat(' ', normalize-space(@class), ' '), ' node__expanded '))]"
    "[./div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
    "[.//span[contains(@class, 'label_status_failed')]]]"
)


# Actual failed tests are leaf anchor elements with node__leaf and a child span
# whose class contains text_status_failed.
FAILED_LEAF_TEST_RELATIVE_XPATH = (
    ".//a[contains(concat(' ', normalize-space(@class), ' '), ' node__leaf ')]"
    "[.//span[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'text_status_failed')]]"
)


FAILED_LEAF_TEST_NAME_RELATIVE_XPATH = ".//div[@class='node__name']"
FAILED_LEAF_STATUS_RELATIVE_XPATH = (
    ".//span[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'text_status_failed')]"
)


# Right-side failure detail locators used after clicking the actual failed leaf test.
RIGHT_TEST_RESULT_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' side-by-side__right ')]"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' test-result ')]"
)

RIGHT_STATUS_MESSAGE_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' side-by-side__right ')]"
    "//pre[contains(concat(' ', normalize-space(@class), ' '), ' status-details__message ')]"
)

RIGHT_STATUS_TRACE_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' side-by-side__right ')]"
    "//pre[contains(concat(' ', normalize-space(@class), ' '), ' status-details__trace ')]"
)


def get_report_url(html_file_path: str) -> str:
    """Convert local HTML file path into file:// URL for Playwright."""
    html_path = Path(html_file_path)

    if not html_path.exists():
        raise FileNotFoundError(
            f"HTML report not found: {html_path}\n"
            "Pass the HTML path, for example:\n"
            "python phase2_failed_leaf_with_status_details.py "
            '"D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"'
        )

    return html_path.resolve().as_uri()


def wait_for_report_to_load(page: Page) -> None:
    """Wait until the HTML body and client-side report content are visible."""
    page.wait_for_selector("xpath=//body", state="visible", timeout=DEFAULT_TIMEOUT_MS)

    # Give Allure's JavaScript time to render content after DOMContentLoaded.
    # This is intentionally small and stable for large single-file reports.
    page.wait_for_timeout(3_000)


def open_suites_section_if_present(page: Page) -> bool:
    """Return True when Suites section exists; open it using an XPath locator."""
    suites_section = page.locator(f"xpath={SUITES_SECTION_XPATH}").first

    try:
        suites_section.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return False

    suites_section.click()
    page.wait_for_timeout(2_000)
    return True


def count_suites(page: Page) -> int:
    """Count top-level suites using XPath locators only."""
    suite_items = page.locator(f"xpath={TOP_LEVEL_SUITE_XPATH}")
    suite_count = suite_items.count()

    if suite_count == 0:
        fallback_suite_items = page.locator(f"xpath={TOP_LEVEL_SUITE_FALLBACK_XPATH}")
        suite_count = fallback_suite_items.count()

    return suite_count


def get_text(locator: Locator) -> str:
    """Get normalized text from a locator."""
    return locator.inner_text(timeout=DEFAULT_TIMEOUT_MS).strip()


def click_direct_title(node: Locator) -> None:
    """Click the direct node title for a suite or grouping node."""
    title = node.locator(f"xpath={DIRECT_NODE_TITLE_XPATH}").first
    title.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT_MS)
    title.click(timeout=DEFAULT_TIMEOUT_MS)


def get_optional_text(page: Page, xpath: str) -> str:
    """Get text from an optional right-side failure detail element."""
    locator = page.locator(f"xpath={xpath}").first

    try:
        locator.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
        return locator.inner_text(timeout=DEFAULT_TIMEOUT_MS).strip()
    except PlaywrightTimeoutError:
        return ""


def get_failure_details_from_right_panel(page: Page) -> tuple[str, str]:
    """Get status-details__message and status-details__trace from right-side content."""
    page.wait_for_selector(
        f"xpath={RIGHT_TEST_RESULT_XPATH}",
        state="visible",
        timeout=DEFAULT_TIMEOUT_MS,
    )

    failure_message = get_optional_text(page, RIGHT_STATUS_MESSAGE_XPATH)
    failure_trace = get_optional_text(page, RIGHT_STATUS_TRACE_XPATH)

    return failure_message, failure_trace


def expand_failed_branches(page: Page, parent_node: Locator) -> None:
    """
    Expand failed grouping nodes under the given parent until failed leaf tests are visible.

    This intentionally expands only nodes that have their own label_status_failed.
    It does not count these grouping nodes as failed tests.
    """
    max_expand_attempts = 500

    for _ in range(max_expand_attempts):
        collapsed_failed_branch = parent_node.locator(
            f"xpath={COLLAPSED_FAILED_BRANCH_RELATIVE_XPATH}"
        ).first

        if collapsed_failed_branch.count() == 0:
            break

        click_direct_title(collapsed_failed_branch)
        page.wait_for_timeout(300)


def process_failed_suite(page: Page, suite_node: Locator, suite_index: int) -> tuple[str, int] | None:
    """Process one suite node, expand it, and count only failed leaf tests."""
    suite_name = get_text(suite_node.locator(f"xpath={DIRECT_NODE_NAME_XPATH}").first)

    failed_label_count = suite_node.locator(f"xpath={DIRECT_FAILED_LABEL_XPATH}").count()
    if failed_label_count == 0:
        return None

    print(f"Suite name: {suite_name}")

    click_direct_title(suite_node)
    page.wait_for_timeout(500)

    expand_failed_branches(page, suite_node)

    failed_leaf_tests = suite_node.locator(f"xpath={FAILED_LEAF_TEST_RELATIVE_XPATH}")
    failed_leaf_count = failed_leaf_tests.count()

    print(f"Actual failed test count in suite '{suite_name}': {failed_leaf_count}")

    for failed_test_index in range(failed_leaf_count):
        failed_test = failed_leaf_tests.nth(failed_test_index)
        failed_test_name = get_text(
            failed_test.locator(f"xpath={FAILED_LEAF_TEST_NAME_RELATIVE_XPATH}").first
        )

        failed_test.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT_MS)
        failed_test.click(timeout=DEFAULT_TIMEOUT_MS)
        page.wait_for_timeout(300)

        failed_status_count = failed_test.locator(
            f"xpath={FAILED_LEAF_STATUS_RELATIVE_XPATH}"
        ).count()

        if failed_status_count > 0:
            failure_message, failure_trace = get_failure_details_from_right_panel(page)

            print(f"  Failed test {failed_test_index + 1}: {failed_test_name}")
            print("    status-details__message:")
            print(f"    {failure_message}")
            print("    status-details__trace:")
            print(f"    {failure_trace}")
        else:
            print(
                f"  Skipped test {failed_test_index + 1}: {failed_test_name} "
                "because text_status_failed was not found under node__leaf"
            )

    return suite_name, failed_leaf_count


def main() -> None:
    if len(sys.argv) < 2:
        raise ValueError(
            "Please provide the HTML report path.\n"
            "Example:\n"
            "python phase2_failed_leaf_with_status_details.py "
            '"D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"'
        )

    report_url = get_report_url(sys.argv[1])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        try:
            # domcontentloaded is safer than load for large local Allure HTML files.
            page.goto(
                report_url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS,
            )

            wait_for_report_to_load(page)

            is_suite_section_present = open_suites_section_if_present(page)

            if not is_suite_section_present:
                print("Suite section present: No")
                print("Suite count: 0")
                return

            suite_count = count_suites(page)
            print("Suite section present: Yes")
            print(f"Suite count: {suite_count}")

            suite_nodes = page.locator(f"xpath={TOP_LEVEL_SUITE_NODE_XPATH}")
            suite_node_count = suite_nodes.count()

            failed_suite_summary = []

            for suite_index in range(suite_node_count):
                suite_node = suite_nodes.nth(suite_index)
                suite_result = process_failed_suite(page, suite_node, suite_index)

                if suite_result is not None:
                    failed_suite_summary.append(suite_result)

            print("\nFinal failed suite summary:")
            if len(failed_suite_summary) == 0:
                print("No failed suites found")
            else:
                for suite_name, failed_test_count in failed_suite_summary:
                    print(f"{suite_name}: {failed_test_count}")

        except PlaywrightTimeoutError as error:
            print("Timed out while opening or reading the report.")
            print("Reason: the report is large or the UI did not render within the configured timeout.")
            print(f"Error details: {error}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
