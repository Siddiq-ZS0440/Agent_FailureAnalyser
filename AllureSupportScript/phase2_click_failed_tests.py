"""
Phase 2 - Open an existing Allure HTML report, count Suites, count failed Suites,
count failed tests inside each failed Suite using XPath, and click each failed test.

Usage:
    python phase2_click_failed_tests.py /path/to/Allure_Report.html

Install:
    pip install playwright selenium
    python -m playwright install chromium

Notes:
    - This script assumes you already have the HTML report locally.
    - No zip extraction is performed.
    - Playwright opens the report in headed mode.
    - XPath locators are used for Suites section detection, suite counting,
      failed suite detection, failed test counting, and failed test clicking.
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
# This targets Allure-style tree rows and excludes nested child rows.
TOP_LEVEL_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[@class='node']//div[@class='node__name'][not(ancestor::div[@class='node__children'])]"
)


# XPath locator to check whether a top-level suite has failed label.
# Replace replacesuitename with actual suite name before using this locator.
TOP_LEVEL_FAILED_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[contains(@class, 'node__title')]"
    "[.//div[@class='node__name' and normalize-space(.)='replacesuitename']]"
    "//span[contains(@class, 'label_status_failed')]"
)


# Relative XPath locator to count failed tests inside a suite after clicking/expanding it.
# Replace replacesuitename with actual suite name before using this locator.
FAILED_TEST_IN_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[contains(@class, 'node__title')]"
    "[.//div[@class='node__name' and normalize-space(.)='replacesuitename']]"
    "/following-sibling::div[contains(@class, 'node__children')]"
    "//div[contains(@class, 'node__title')]//span[contains(@class, 'label_status_failed')]"
)


# XPath locator to capture failed test element or elements inside expanded suite.
# Replace replacesuitename with actual suite name before using this locator.
FAILED_TEST_ELEMENT_IN_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[contains(@class, 'node__title')]"
    "[.//div[@class='node__name' and normalize-space(.)='replacesuitename']]"
    "/following-sibling::div[contains(@class, 'node__children')]"
    "//div[contains(@class, 'node__title')][.//span[contains(@class, 'label_status_failed')]]"
)


EXPANDED_FAILED_TEST_STATUS_XPATH = (
    ".//div[contains(@class, 'node__anchor')]"
    "//span[contains(@class, 'text_Status_failed')]"
)


# Fallback XPath for report variants where the top-level suite row is rendered
# as a node/container rather than a direct tree__item element.
TOP_LEVEL_SUITE_FALLBACK_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' tree__node ') "
    "and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' tree__children ')])]"
)


def get_report_url(html_file_path: str) -> str:
    """Convert local HTML file path into file:// URL for Playwright."""
    html_path = Path(html_file_path)

    if not html_path.exists():
        raise FileNotFoundError(
            f"HTML report not found: {html_path}\n"
            "Pass the HTML path, for example:\n"
            "python phase2_click_failed_tests.py "
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


def get_suite_names(page: Page) -> list[str]:
    """Get top-level suite names using the existing top-level suite XPath."""
    suite_items = page.locator(f"xpath={TOP_LEVEL_SUITE_XPATH}")
    suite_count = suite_items.count()

    suite_names = []
    for index in range(suite_count):
        suite_name = suite_items.nth(index).inner_text().strip()
        if suite_name:
            suite_names.append(suite_name)

    return suite_names


def build_suite_xpath(xpath_template: str, suite_name: str) -> str:
    """Replace replacesuitename with actual suite name before using the XPath."""
    return xpath_template.replace("replacesuitename", suite_name)


def get_failed_suite_names(page: Page, suite_names: list[str]) -> list[str]:
    """Return suite names that have a failure label using TOP_LEVEL_FAILED_SUITE_XPATH."""
    failed_suite_names = []

    for suite_name in suite_names:
        failed_suite_xpath = build_suite_xpath(TOP_LEVEL_FAILED_SUITE_XPATH, suite_name)
        failed_suite_label_count = page.locator(f"xpath={failed_suite_xpath}").count()

        if failed_suite_label_count > 0:
            failed_suite_names.append(suite_name)

    return failed_suite_names


def click_suite_name(page: Page, suite_name: str) -> None:
    """Click the suite name to expand test details."""
    suite_name_xpath = build_suite_xpath(
        "//div[@class='side-by-side__left']//div[contains(@class, 'node__title')]"
        "[.//div[@class='node__name' and normalize-space(.)='replacesuitename']]"
        "//div[@class='node__name']",
        suite_name,
    )

    page.locator(f"xpath={suite_name_xpath}").first.click()
    page.wait_for_timeout(1_000)


def count_failed_tests_in_suite(page: Page, suite_name: str) -> int:
    """Count failed tests inside expanded suite using suite-name relative XPath."""
    failed_test_xpath = build_suite_xpath(FAILED_TEST_IN_SUITE_XPATH, suite_name)
    return page.locator(f"xpath={failed_test_xpath}").count()


def click_failed_tests_and_count_expanded_failed_status(page: Page, suite_name: str) -> int:
    """Click each failed test element and count expanded failed status elements."""
    failed_test_element_xpath = build_suite_xpath(FAILED_TEST_ELEMENT_IN_SUITE_XPATH, suite_name)
    failed_test_elements = page.locator(f"xpath={failed_test_element_xpath}")
    failed_test_element_count = failed_test_elements.count()

    expanded_failed_status_count = 0

    for failed_test_index in range(failed_test_element_count):
        failed_test_elements = page.locator(f"xpath={failed_test_element_xpath}")
        failed_test_element = failed_test_elements.nth(failed_test_index)

        failed_test_element.click()
        page.wait_for_timeout(1_000)

        failed_status_count = failed_test_element.locator(
            f"xpath={EXPANDED_FAILED_TEST_STATUS_XPATH}"
        ).count()

        expanded_failed_status_count += failed_status_count

    return expanded_failed_status_count


def main() -> None:
    if len(sys.argv) < 2:
        raise ValueError(
            "Please provide the HTML report path.\n"
            "Example:\n"
            "python phase2_click_failed_tests.py "
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

                if suite_count == 0:
                    print("Suites with failure label: 0")
                else:
                    suite_names = get_suite_names(page)
                    failed_suite_names = get_failed_suite_names(page, suite_names)

                    print(f"Suites with failure label: {len(failed_suite_names)}")

                    for suite_name in failed_suite_names:
                        print(f"Suite name: {suite_name}")

                        click_suite_name(page, suite_name)

                        failed_test_count = count_failed_tests_in_suite(page, suite_name)
                        print(f"Failed test count in suite '{suite_name}': {failed_test_count}")

                        expanded_failed_test_count = click_failed_tests_and_count_expanded_failed_status(
                            page,
                            suite_name,
                        )
                        print(
                            f"Expanded failed test count in suite '{suite_name}': "
                            f"{expanded_failed_test_count}"
                        )

        except PlaywrightTimeoutError as error:
            print("Timed out while opening or reading the report.")
            print("Reason: the report is large or the UI did not render within the configured timeout.")
            print(f"Error details: {error}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
