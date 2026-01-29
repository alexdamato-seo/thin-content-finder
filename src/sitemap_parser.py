"""
Sitemap Parser Module

Fetches and parses XML sitemaps, extracting product URLs for analysis.
"""

import re
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class SitemapURL:
    """Represents a URL extracted from a sitemap."""
    url: str
    language: str
    sku: str
    lastmod: Optional[str] = None


class SitemapParser:
    """Parses XML sitemaps and extracts product URLs."""

    # Pattern to match product URLs: /products/[sku]/[sku]
    PRODUCT_URL_PATTERN = re.compile(r'/products/([^/]+)/([^/]+)/?$')

    # Language code extraction pattern
    LANGUAGE_PATTERN = re.compile(r'evidentscientific\.com/([a-z]{2})/')

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize the sitemap parser.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.session = self._create_session(max_retries)

    def _create_session(self, max_retries: int) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=2,  # Exponential backoff: 2, 4, 8 seconds
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_sitemap(self, url: str) -> Optional[str]:
        """
        Fetch sitemap XML content from URL.

        Args:
            url: Sitemap URL to fetch

        Returns:
            XML content as string, or None if fetch failed
        """
        try:
            logger.info(f"Fetching sitemap: {url}")
            response = self.session.get(
                url,
                timeout=self.timeout,
                headers={
                    'User-Agent': 'ThinPageAnalyzer/1.0 (SEO Analysis Tool)'
                }
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch sitemap {url}: {e}")
            return None

    def parse_sitemap(self, xml_content: str) -> List[str]:
        """
        Parse sitemap XML and extract all URLs.

        Args:
            xml_content: XML content as string

        Returns:
            List of URLs found in the sitemap
        """
        urls = []
        try:
            # Handle XML namespaces
            root = ET.fromstring(xml_content)

            # Common sitemap namespace
            namespaces = {
                'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'
            }

            # Try with namespace first
            url_elements = root.findall('.//sm:url', namespaces)

            if not url_elements:
                # Try without namespace
                url_elements = root.findall('.//url')

            for url_elem in url_elements:
                loc = url_elem.find('sm:loc', namespaces)
                if loc is None:
                    loc = url_elem.find('loc')

                if loc is not None and loc.text:
                    urls.append(loc.text.strip())

            logger.info(f"Found {len(urls)} URLs in sitemap")

        except ET.ParseError as e:
            logger.error(f"Failed to parse sitemap XML: {e}")

        return urls

    def filter_product_urls(self, urls: List[str]) -> List[SitemapURL]:
        """
        Filter URLs to only include product pages.

        Product URL pattern: /products/[sku]/[sku]

        Args:
            urls: List of all URLs from sitemap

        Returns:
            List of SitemapURL objects for product pages only
        """
        product_urls = []

        for url in urls:
            match = self.PRODUCT_URL_PATTERN.search(url)
            if match:
                sku = match.group(2)  # Use second capture group as SKU

                # Extract language code
                lang_match = self.LANGUAGE_PATTERN.search(url)
                language = lang_match.group(1) if lang_match else 'unknown'

                product_urls.append(SitemapURL(
                    url=url,
                    language=language,
                    sku=sku
                ))

        logger.info(f"Filtered to {len(product_urls)} product URLs")
        return product_urls

    def process_sitemap(self, sitemap_url: str) -> List[SitemapURL]:
        """
        Process a single sitemap: fetch, parse, and filter.

        Args:
            sitemap_url: URL of the sitemap to process

        Returns:
            List of product SitemapURL objects
        """
        xml_content = self.fetch_sitemap(sitemap_url)
        if xml_content is None:
            return []

        all_urls = self.parse_sitemap(xml_content)
        return self.filter_product_urls(all_urls)

    def process_all_sitemaps(self, sitemap_urls: List[str]) -> Dict[str, List[SitemapURL]]:
        """
        Process multiple sitemaps.

        Args:
            sitemap_urls: List of sitemap URLs to process

        Returns:
            Dictionary mapping sitemap URL to list of product URLs
        """
        results = {}

        for sitemap_url in sitemap_urls:
            logger.info(f"Processing sitemap: {sitemap_url}")
            product_urls = self.process_sitemap(sitemap_url)
            results[sitemap_url] = product_urls
            logger.info(f"Found {len(product_urls)} product URLs in {sitemap_url}")

        total_urls = sum(len(urls) for urls in results.values())
        logger.info(f"Total product URLs across all sitemaps: {total_urls}")

        return results


def get_language_from_sitemap_url(sitemap_url: str) -> str:
    """Extract language code from sitemap filename."""
    match = re.search(r'sitemap-([a-z]{2})\.xml', sitemap_url)
    return match.group(1) if match else 'unknown'
