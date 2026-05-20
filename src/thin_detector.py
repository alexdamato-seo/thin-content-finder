"""
Thin Page Detector — implements Check A (SKU URL pattern) and Check B (title/H1).

Check A (URL-level, no crawl needed):
  Flags a URL if every path segment after /products/ matches a SKU-style regex,
  meaning the path has no descriptive category words.

  Regex: ^[a-z]{0,3}[0-9]+[a-z0-9]*$  (case-insensitive)
  - Matches: we402458, ax0003, e9701832
  - Does NOT match: microscopes, stereo-microscopes (no digits)

Check B (requires page fetch):
  Flags a page if its <title> or first <h1> is a bare SKU code with no
  descriptive words, matching the same regex after stripping site-name suffixes.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from .page_analyzer import PageResult
from .sitemap_parser import SitemapURL

logger = logging.getLogger(__name__)

# SKU slug pattern — up to 3 letters, then digits, then optional alphanumeric suffix
SKU_SLUG_RE = re.compile(r'^[a-z]{0,3}\d+[a-z0-9]*$', re.IGNORECASE)

# Strips trailing site-name suffix from titles, e.g. "ax0003 | Evident Scientific"
SITE_SUFFIX_RE = re.compile(r'\s*[|\-–—]\s*\S.*$')


@dataclass
class DetectionResult:
    """Per-URL result matching the CSV output columns exactly."""
    url: str
    locale: str
    flagged: bool
    check_a_sku_url: bool
    check_b_sku_title_h1: bool
    page_title: str
    h1: str
    flag_reasons: str
    http_status: Optional[int]
    check_b_skipped: bool


def check_a_sku_url(url: str) -> bool:
    """
    Return True if every path segment after /products/ matches the SKU regex.

    Good URL  — /products/microscopes/stereo-microscopes/szx16
      segments: ['microscopes', 'stereo-microscopes', 'szx16']
      'microscopes' has no digits → NOT all SKU → returns False

    Thin URLs — /products/ax0003/ax0003, /products/we402458/we402458
      all segments match SKU regex → returns True
    """
    parsed = urlparse(url)
    path = parsed.path

    match = re.search(r'/products/(.*)', path)
    if not match:
        return False

    products_path = match.group(1).rstrip('/')
    segments = [s for s in products_path.split('/') if s]

    if not segments:
        return False

    return all(SKU_SLUG_RE.match(seg) for seg in segments)


def check_b_sku_title_h1(page_title: str, h1: str) -> bool:
    """
    Return True if either the page title or first H1 is a bare SKU code.

    Strips common site-name suffixes before checking, so titles like
    "ax0003 | Evident Scientific" are still caught.
    """
    return _is_sku_only(page_title) or _is_sku_only(h1)


def build_result(sitemap_url: SitemapURL, page_result: PageResult) -> DetectionResult:
    """Combine sitemap URL metadata and page fetch result into a DetectionResult."""
    url = sitemap_url.url
    locale = sitemap_url.locale

    a_flag = check_a_sku_url(url)

    # Check B — skip if the page could not be fetched
    if page_result.check_b_skipped:
        b_flag = False
        check_b_skipped = True
    else:
        b_flag = check_b_sku_title_h1(page_result.page_title, page_result.h1)
        check_b_skipped = False

    flagged = a_flag or b_flag

    reasons: list[str] = []
    if a_flag:
        reasons.append('SKU-style URL slug')
    if b_flag:
        reasons.append('Title/H1 is bare SKU')
    if page_result.error:
        reasons.append(f'Fetch error: {page_result.error}')
        check_b_skipped = True   # mark skipped if error wasn't already set

    return DetectionResult(
        url=url,
        locale=locale,
        flagged=flagged,
        check_a_sku_url=a_flag,
        check_b_sku_title_h1=b_flag,
        page_title=page_result.page_title,
        h1=page_result.h1,
        flag_reasons='; '.join(reasons),
        http_status=page_result.http_status,
        check_b_skipped=check_b_skipped,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_sku_only(text: str) -> bool:
    """Return True if text (after stripping site-name suffix) matches SKU regex."""
    text = text.strip()
    if not text:
        return False
    text = SITE_SUFFIX_RE.sub('', text).strip()
    return bool(SKU_SLUG_RE.match(text))
