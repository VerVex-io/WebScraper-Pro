"""Chrome automation (undetected-chromedriver).  Imported lazily so the rest of
the package - parsing, exporting, tests - works without Chrome installed."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

Log = Callable[[str], None]


def init_driver(headless: bool = True, *, no_sandbox: bool | None = None):
    """Start Chrome.

    The Chrome sandbox stays ON by default.  v1 always passed ``--no-sandbox``,
    which removes the main protection against malicious pages.  Enable it only
    where Chrome cannot run otherwise (e.g. Docker as root) via ``--no-sandbox``
    or ``WSP_NO_SANDBOX=1``.
    """
    import undetected_chromedriver as uc

    if no_sandbox is None:
        no_sandbox = os.environ.get("WSP_NO_SANDBOX") == "1"
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,720")
    options.add_argument("--lang=en-US")
    options.add_argument("--disable-dev-shm-usage")
    if no_sandbox:
        options.add_argument("--no-sandbox")
    # version_main is auto-detected (v1 hard-coded Chrome 137 and broke on update)
    return uc.Chrome(options=options, headless=headless, use_subprocess=True)


def load_page(
    driver,
    url: str,
    wait_selector: str | None = None,
    timeout: int = 20,
    settle: float = 2.0,
    log: Log = print,
) -> str:
    """Navigate, wait for content, scroll once to trigger lazy loading."""
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    log(f"Navigating to {url}")
    driver.get(url)
    if wait_selector:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
            )
        except TimeoutException:
            log(f"Timed out waiting for '{wait_selector}' - continuing with what loaded.")
    else:
        time.sleep(min(timeout, 5))
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(settle)
    html = driver.page_source
    log(f"Page source: {len(html)} chars")
    return html
