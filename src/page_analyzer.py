"""
Page Analyzer — fetches product pages and extracts <title> and <h1>.

Uses requests + BeautifulSoup (no headless browser required).
Applies a 0.5–1 s random delay between requests.
"""

import random
import time
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = 'ThinContentAudit/1.0'


@dataclass
class PageResult:
    """Outcome of fetching and parsing a single product page."""
    url: str
    http_status: Optional[int] = None
    page_title: str = ''
    h1: str = ''
    error: Optional[str] = None
    check_b_skipped: bool = False


class PageFetcher:
    """Fetches pages with requests and extracts title + H1 via BeautifulSoup."""

    def __init__(
        self,
        timeout: int = 30,
        min_delay: float = 0.5,
        max_delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.timeout = timeout
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session = _make_session(max_retries)

    def fetch(self, url: str) -> PageResult:
        """
        Fetch a page and extract its <title> and first <h1>.

        Applies a random delay before the request to avoid hammering the server.
        On HTTP error (4xx/5xx) the status code is still recorded.
        On network/timeout error the result is marked with check_b_skipped=True.
        """
        time.sleep(random.uniform(self.min_delay, self.max_delay))
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            soup = BeautifulSoup(resp.text, 'lxml')

            title = ''
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

            h1_tag = soup.find('h1')
            h1 = h1_tag.get_text(strip=True) if h1_tag else ''

            return PageResult(
                url=url,
                http_status=resp.status_code,
                page_title=title,
                h1=h1,
            )

        except requests.Timeout:
            logger.warning(f"Timeout fetching {url}")
            return PageResult(url=url, error='Timeout', check_b_skipped=True)

        except requests.ConnectionError as e:
            msg = f'Connection error: {str(e)[:80]}'
            logger.warning(f"{msg} — {url}")
            return PageResult(url=url, error=msg, check_b_skipped=True)

        except Exception as e:
            msg = f'Error: {str(e)[:80]}'
            logger.error(f"{msg} — {url}")
            return PageResult(url=url, error=msg, check_b_skipped=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(max_retries: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({'User-Agent': USER_AGENT})
    return session
