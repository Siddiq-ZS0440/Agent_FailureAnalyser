"""
Phase 2 - Open an existing Allure HTML report, count Suites,
count Suites with failure labels, then expand each failed Suite and count failed tests.

Usage:
    python phase2_from_latest_phase1.py /path/to/Allure_Report.html

Install:
    pip install playwright selenium
    python -m playwright install chromium

Notes:
    - This script assumes you already have the HTML report locally.
    - No zip extraction is performed.
    - Playwright opens the report in headed mode.
    - XPath locators are used for Suites section detection, suite counting,
      failed suite detection, suite expansion, and failed test counting.
"""

from pathlib import Path
import sys

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
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
# This locator is preserved from the latest Phase 1 reference script.
TOP_LEVEL_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[@class='node']//div[@class='node__name'][not(ancestor::div[@class='node__children'])]"
)


# Fallback XPath for report variants where the top-level suite row is rendered
# as a tree node/container rather than a direct node__name element.
TOP_LEVEL_SUITE_FALLBACK_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' tree__node ') "
    "and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' tree__children ')])]"
)


# Phase 2 XPath: top-level suite name where the same suite node contains a failure label/count.
# This keeps the same node__name based structure from the latest Phase 1 script.
TOP_LEVEL_FAILED_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[@class='node' "
    "and not(ancestor::div[@class='node__children']) "
    "and .//*[contains(@class, 'label_status_failed') "
    "or contains(@class, 'status-failed') "
    "or contains(@class, 'failed') "
    "or normalize-space()='failed' "
    "or normalize-space()='Failed']]"
    "//div[@class='node__name']"
)


# Fallback Phase 2 XPath: supports tree-based Allure variants.
TOP_LEVEL_FAILED_SUITE_FALLBACK_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' tree__node ') "
    "and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' tree__children ')]) "
    "and .//*[contains(@class, 'label_status_failed') "
    "or contains(@class, 'status-failed') "
    "or contains(@class, 'failed') "
    "or normalize-space()='failed' "
    "or normalize-space()='Failed']]"
)


# Phase 2 XPath: failed tests visible after a failed suite is expanded.
# This targets child nodes/test rows with a failed status label.
FAILED_TEST_IN_EXPANDED_SUITE_RELATIVE_XPATH = (
    ".//ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' node ')][1]"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' node__children ')]"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' node ') "
    "and .//*[contains(@class, 'label_status_failed') "
    "or contains(@class, 'status-failed') "
    "or contains(@class, 'failed') "
    "or normalize-space()='failed' "
    "or normalize-space()='Failed']]"
)


FAILED_TEST_IN_EXPANDED_SUITE_FALLBACK_RELATIVE_XPATH = (
    ".//ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' tree__node ')][1]"
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' tree__children ')]"
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' tree__node ') "
    "and .//*[contains(@class, 'label_status_failed') "
    "or contains(@class, 'status-failed') "
    "or contains(@class, 'failed') "
    "or normalize-space()='failed' "
    "or normalize-space()='Failed']]"
)


def get_report_url(html_file_path: str) -> str:
    """Convert local HTML file path into file:// URL for Playwright."""
    html_path = Path(html_file_path)

    if not html_path.exists():
        raise FileNotFoundError(
            f"HTML report not found: {html_path}\n"
            "Pass the HTML path, for example:\n"
            "python phase2_from_latest_phase1.py "
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


def get_failed_suite_locator(page: Page):
    """Return locator for top-level suites that contain a failure label."""
    failed_suites = page.locator(f"xpath={TOP_LEVEL_FAILED_SUITE_XPATH}")

    if failed_suites.count() == 0:
        failed_suites = page.locator(f"xpath={TOP_LEVEL_FAILED_SUITE_FALLBACK_XPATH}")

    return failed_suites


def get_suite_name(failed_suite_locator) -> str:
    """Read suite name from a failed suite locator."""
    suite_name = failed_suite_locator.inner_text(timeout=DEFAULT_TIMEOUT_MS).strip()

    # Some Allure nodes may include count/status text in inner_text.
    # Keep the first non-empty line as suite name.
    suite_name_lines = [line.strip() for line in suite_name.splitlines() if line.strip()]
    return suite_name_lines[0] if suite_name_lines else "<suite name not found>"


def expand_suite(failed_suite_locator) -> None:
    """Click the failed suite name/node to expand test details."""
    failed_suite_locator.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT_MS)
    failed_suite_locator.click(timeout=DEFAULT_TIMEOUT_MS)


def count_failed_tests_for_suite(failed_suite_locator) -> int:
    """Count failed tests inside the currently expanded failed suite."""
    failed_tests = failed_suite_locator.locator(
        f"xpath={FAILED_TEST_IN_EXPANDED_SUITE_RELATIVE_XPATH}"
    )
    failed_test_count = failed_tests.count()

    if failed_test_count == 0:
        fallback_failed_tests = failed_suite_locator.locator(
            f"xpath={FAILED_TEST_IN_EXPANDED_SUITE_FALLBACK_RELATIVE_XPATH}"
        )
        failed_test_count = fallback_failed_tests.count()

    return failed_test_count


def process_failed_suites(page: Page) -> None:
    """
    Count failed suites, iterate through them using a for loop,
    expand each suite, and print failed test count.
    """
    failed_suites = get_failed_suite_locator(page)
    failed_suite_count = failed_suites.count()

    print(f"Suites with failure label: {failed_suite_count}")

    for index in range(failed_suite_count):
        # Re-fetch locator on every iteration because clicking may re-render the tree.
        failed_suites = get_failed_suite_locator(page)
        failed_suite = failed_suites.nth(index)

        suite_name = get_suite_name(failed_suite)
        print(f"\nProcessing failed suite {index + 1}: {suite_name}")

        expand_suite(failed_suite)
        page.wait_for_timeout(1_000)

        failed_test_count = count_failed_tests_for_suite(failed_suite)
        print(f"Failed test count in suite '{suite_name}': {failed_test_count}")


def main() -> None:
    if len(sys.argv) < 2:
        raise ValueError(
            "Please provide the HTML report path.\n"
            "Example:\n"
            "python phase2_from_latest_phase1.py "
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
                print("Suites with failure label: 0")
            else:
                suite_count = count_suites(page)
                print("Suite section present: Yes")
                print(f"Suite count: {suite_count}")

                if suite_count > 0:
                    process_failed_suites(page)
                else:
                    print("Suites with failure label: 0")

        except PlaywrightTimeoutError as error:
            print("Timed out while opening or reading the report.")
            print("Reason: the report is large or the UI did not render within the configured timeout.")
            print(f"Error details: {error}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
