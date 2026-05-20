"""
Sitemap Parser — fetches XML sitemaps and extracts product URLs.

Handles both sitemap indexes (nested sitemaps) and regular urlsets.
Filters to URLs containing /products/ in the path.
Respects robots.txt for the target domain.
"""

import re
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

USER_AGENT = 'ThinContentAudit/1.0'
SM_NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


@dataclass
class SitemapURL:
    """A product URL extracted from a sitemap."""
    url: str
    locale: str
    lastmod: Optional[str] = None


class SitemapParser:
    """Fetches and parses XML sitemaps, filtering to product URLs."""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.session = _make_session(max_retries)
        self._robots: Optional[RobotFileParser] = None

    def load_robots(self, base_url: str = 'https://evidentscientific.com') -> None:
        """Fetch and parse robots.txt for the target domain."""
        rp = RobotFileParser()
        robots_url = f'{base_url}/robots.txt'
        try:
            resp = self.session.get(robots_url, timeout=self.timeout)
            if resp.ok:
                rp.parse(resp.text.splitlines())
                logger.info(f"Loaded robots.txt from {robots_url}")
            else:
                logger.warning(f"robots.txt returned HTTP {resp.status_code} — proceeding without restrictions")
        except Exception as e:
            logger.warning(f"Could not fetch robots.txt: {e} — proceeding without restrictions")
        self._robots = rp

    def is_allowed(self, url: str) -> bool:
        """Return True if robots.txt allows crawling this URL."""
        if self._robots is None:
            return True
        return self._robots.can_fetch(USER_AGENT, url)

    def fetch_xml(self, url: str) -> Optional[str]:
        """Fetch XML content from a URL. Returns None on failure."""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            logger.info(f"Fetched sitemap: {url} (HTTP {resp.status_code})")
            return resp.text
        except requests.HTTPError as e:
            logger.warning(f"HTTP error fetching sitemap {url}: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"Failed to fetch sitemap {url}: {e}")
            return None

    def _parse_xml(self, xml_content: str, source_url: str) -> List[dict]:
        """
        Parse a sitemap XML document into a list of {'url': ..., 'lastmod': ...} dicts.

        Handles both <sitemapindex> (index of child sitemaps) and <urlset>.
        """
        entries: List[dict] = []
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"XML parse error in {source_url}: {e}")
            return entries

        tag_lower = root.tag.lower()

        # Sitemap index — recurse into child sitemaps
        if 'sitemapindex' in tag_lower:
            child_locs = (
                root.findall('.//sm:sitemap/sm:loc', SM_NS)
                or root.findall('.//sitemap/loc')
            )
            child_urls = [el.text.strip() for el in child_locs if el.text]
            logger.info(f"Sitemap index at {source_url}: {len(child_urls)} child sitemaps")
            for child_url in child_urls:
                child_xml = self.fetch_xml(child_url)
                if child_xml:
                    entries.extend(self._parse_xml(child_xml, child_url))
            return entries

        # Regular urlset
        url_elements = (
            root.findall('.//sm:url', SM_NS)
            or root.findall('.//url')
        )
        for url_elem in url_elements:
            loc = url_elem.find('sm:loc', SM_NS)
            if loc is None:
                loc = url_elem.find('loc')
            lastmod_el = url_elem.find('sm:lastmod', SM_NS)
            if lastmod_el is None:
                lastmod_el = url_elem.find('lastmod')
            if loc is not None and loc.text:
                entries.append({
                    'url': loc.text.strip(),
                    'lastmod': lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None,
                })

        logger.info(f"Parsed {len(entries)} URLs from {source_url}")
        return entries

    def process_sitemap(self, sitemap_url: str) -> List[SitemapURL]:
        """
        Fetch, parse, and filter a sitemap to product URLs.

        Returns a list of SitemapURL objects for URLs containing /products/.
        """
        fallback_locale = _locale_from_sitemap_url(sitemap_url)
        xml_content = self.fetch_xml(sitemap_url)
        if xml_content is None:
            logger.warning(f"Skipping sitemap (could not fetch): {sitemap_url}")
            return []

        entries = self._parse_xml(xml_content, sitemap_url)
        product_urls: List[SitemapURL] = []

        for entry in entries:
            url = entry['url']
            if '/products/' not in url:
                continue
            if not self.is_allowed(url):
                logger.debug(f"Skipping robots-disallowed URL: {url}")
                continue

            locale = _locale_from_url(url) or fallback_locale
            product_urls.append(SitemapURL(
                url=url,
                locale=locale,
                lastmod=entry.get('lastmod'),
            ))

        logger.info(f"Found {len(product_urls)} product URLs in {sitemap_url}")
        return product_urls


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


def _locale_from_sitemap_url(sitemap_url: str) -> str:
    """Extract locale from sitemap filename, e.g. sitemap-ja.xml → 'ja'."""
    match = re.search(r'sitemap-([a-z]{2})(?:-\d+)?\.xml', sitemap_url, re.IGNORECASE)
    return match.group(1).lower() if match else 'en'


def _locale_from_url(url: str) -> Optional[str]:
    """Extract locale from URL path, e.g. /ja/products/... → 'ja'."""
    parsed = urlparse(url)
    match = re.match(r'^/([a-z]{2})/products/', parsed.path)
    return match.group(1).lower() if match else None
