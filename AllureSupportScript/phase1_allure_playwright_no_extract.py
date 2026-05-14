"""
Phase 1 - Open an existing Allure HTML report and count Suites using XPath.

Usage:
    python phase1_allure_playwright_no_extract.py /path/to/Allure_Report.html

Install:
    pip install playwright selenium
    python -m playwright install chromium

Notes:
    - This script assumes you already have the HTML report locally.
    - No zip extraction is performed.
    - Playwright opens the report in headed mode.
    - XPath locators are used for Suites section detection and suite counting.
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
            "python phase1_allure_playwright_timeout_fixed.py "
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


def main() -> None:
    if len(sys.argv) < 2:
        raise ValueError(
            "Please provide the HTML report path.\n"
            "Example:\n"
            "python phase1_allure_playwright_timeout_fixed.py "
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
            else:
                suite_count = count_suites(page)
                print("Suite section present: Yes")
                print(f"Suite count: {suite_count}")

        except PlaywrightTimeoutError as error:
            print("Timed out while opening or reading the report.")
            print("Reason: the report is large or the UI did not render within the configured timeout.")
            print(f"Error details: {error}")
            raise

        finally:
            browser.close()


if __name__ == "__main__":
    main()
