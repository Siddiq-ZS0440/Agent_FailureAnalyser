"""
Phase 2 - Open an existing Allure HTML report, navigate to Suites,
iterate each suite element, and count failed tests using parent-child XPath locators.

Usage:
    python phase2_parent_child_failed_count.py /path/to/Allure_Report.html

Install:
    pip install playwright selenium
    python -m playwright install chromium

Notes:
    - This script assumes you already have the HTML report locally.
    - No zip extraction is performed.
    - Playwright opens the report in headed mode.
    - XPath locators are used for suite, test, label, and expanded status detection.
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


# Phase 1 reference locator retained.
TOP_LEVEL_SUITE_XPATH = (
    "//div[@class='side-by-side__left']//div[@class='node']//div[@class='node__name'][not(ancestor::div[@class='node__children'])]"
)


# Suite element locator: this returns the suite parent node, not only the suite name text node.
TOP_LEVEL_SUITE_ELEMENT_XPATH = (
    "//div[@class='side-by-side__left']"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' node ')]"
    "[./div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
    "//div[@class='node__name']]"
    "[not(ancestor::div[@class='node__children'])]"
)


# Relative locators used from a suite element.
SUITE_NAME_RELATIVE_XPATH = ".//div[@class='node__name']"
SUITE_FAILED_LABEL_RELATIVE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
    "//span[contains(@class, 'label_status_failed')]"
)
SUITE_CLICK_TARGET_RELATIVE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
)


# Relative locator used after a suite is expanded.
# This finds test elements only inside the expanded suite parent element.
TEST_ELEMENT_RELATIVE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' node__children ')]"
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' node ')]"
    "[./div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
    "//div[@class='node__name']]"
)


# Relative locators used from each test element.
TEST_NAME_RELATIVE_XPATH = ".//div[@class='node__name']"
TEST_FAILED_LABEL_RELATIVE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
    "//span[contains(@class, 'label_status_failed')]"
)
TEST_CLICK_TARGET_RELATIVE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' node__title ')]"
)


# After clicking a failed test, verify failed status inside that same failed test element.
# Required structure: anchor tag with node__leaf, and child span class containing text_status_failed.
EXPANDED_FAILED_STATUS_RELATIVE_XPATH = (
    ".//a[contains(@class, 'node__leaf')]"
    "//span[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'text_status_failed')]"
)


def get_report_url(html_file_path: str) -> str:
    """Convert local HTML file path into file:// URL for Playwright."""
    html_path = Path(html_file_path)

    if not html_path.exists():
        raise FileNotFoundError(
            f"HTML report not found: {html_path}\n"
            "Pass the HTML path, for example:\n"
            "python phase2_parent_child_failed_count.py "
            '"D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"'
        )

    return html_path.resolve().as_uri()


def wait_for_report_to_load(page: Page) -> None:
    """Wait until the HTML body and client-side report content are visible."""
    page.wait_for_selector("xpath=//body", state="visible", timeout=DEFAULT_TIMEOUT_MS)
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
    return suite_items.count()


def get_text(locator: Locator, relative_xpath: str) -> str:
    """Get text from a child element using a relative XPath locator."""
    child = locator.locator(f"xpath={relative_xpath}").first
    return child.inner_text().strip()


def click_relative(locator: Locator, relative_xpath: str) -> None:
    """Click a child element using a relative XPath locator."""
    click_target = locator.locator(f"xpath={relative_xpath}").first
    click_target.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT_MS)
    click_target.click()


def suite_has_failed_label(suite_element: Locator) -> bool:
    """Check whether the suite parent element has a failed label."""
    return suite_element.locator(f"xpath={SUITE_FAILED_LABEL_RELATIVE_XPATH}").count() > 0


def test_has_failed_label(test_element: Locator) -> bool:
    """Check whether the test parent element has a failed label."""
    return test_element.locator(f"xpath={TEST_FAILED_LABEL_RELATIVE_XPATH}").count() > 0


def expanded_test_has_failed_status(test_element: Locator) -> bool:
    """Check whether expanded failed test has node__leaf anchor with text_status_failed span."""
    return test_element.locator(f"xpath={EXPANDED_FAILED_STATUS_RELATIVE_XPATH}").count() > 0


def process_failed_suite(page: Page, suite_index: int) -> int:
    """Expand one failed suite and count failed tests inside that suite parent element."""
    suite_element = page.locator(f"xpath={TOP_LEVEL_SUITE_ELEMENT_XPATH}").nth(suite_index)
    suite_name = get_text(suite_element, SUITE_NAME_RELATIVE_XPATH)

    print(f"Suite name: {suite_name}")

    click_relative(suite_element, SUITE_CLICK_TARGET_RELATIVE_XPATH)
    page.wait_for_timeout(1_000)

    test_elements = suite_element.locator(f"xpath={TEST_ELEMENT_RELATIVE_XPATH}")
    total_test_count = test_elements.count()
    print(f"Total test count in suite '{suite_name}': {total_test_count}")

    failed_test_count = 0

    for test_index in range(total_test_count):
        test_element = test_elements.nth(test_index)

        if not test_has_failed_label(test_element):
            continue

        test_name = get_text(test_element, TEST_NAME_RELATIVE_XPATH)
        click_relative(test_element, TEST_CLICK_TARGET_RELATIVE_XPATH)
        page.wait_for_timeout(300)

        if expanded_test_has_failed_status(test_element):
            failed_test_count += 1
            print(f"  Failed test: {test_name}")

    print(f"Failed test count in suite '{suite_name}': {failed_test_count}")
    print(f"Expanded failed test count in suite '{suite_name}': {failed_test_count}")

    return failed_test_count


def main() -> None:
    if len(sys.argv) < 2:
        raise ValueError(
            "Please provide the HTML report path.\n"
            "Example:\n"
            "python phase2_parent_child_failed_count.py "
            '"D:\\Failure_Analyser\\Failure_Analyser_v6\\HTML Report\\Allure_Report.html"'
        )

    report_url = get_report_url(sys.argv[1])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        try:
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

            suite_elements = page.locator(f"xpath={TOP_LEVEL_SUITE_ELEMENT_XPATH}")
            suite_element_count = suite_elements.count()

            suites_with_failed_label_count = 0

            for suite_index in range(suite_element_count):
                suite_element = suite_elements.nth(suite_index)

                if not suite_has_failed_label(suite_element):
                    continue

                suites_with_failed_label_count += 1
                process_failed_suite(page, suite_index)

            print(f"Suites with failure label: {suites_with_failed_label_count}")

        except PlaywrightTimeoutError as error:
            print("Timed out while opening or reading the report.")
            print("Reason: the report is large or the UI did not render within the configured timeout.")
            print(f"Error details: {error}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
