"""
Page Analyzer Module

Renders JavaScript-heavy pages with a headless browser and extracts content metrics.
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class PageMetrics:
    """Metrics extracted from a page."""
    url: str
    page_title: str = ""
    word_count: int = 0
    has_description: bool = False
    has_specifications: bool = False
    image_count: int = 0
    description_text: str = ""
    specifications_text: str = ""
    content_sections: List[str] = field(default_factory=list)
    error: Optional[str] = None
    raw_title: str = ""  # Original title without processing


class PageAnalyzer:
    """Analyzes page content using a headless browser."""

    # Elements to exclude when counting words (navigation, headers, footers)
    EXCLUDE_SELECTORS = [
        'nav', 'header', 'footer', 'script', 'style', 'noscript',
        '.navigation', '.nav', '.header', '.footer', '.menu',
        '#navigation', '#nav', '#header', '#footer', '#menu',
        '.cookie-banner', '.cookie-notice', '.breadcrumb',
        '.site-header', '.site-footer', '.main-nav',
    ]

    # Selectors for product content
    PRODUCT_TITLE_SELECTORS = [
        'h1', '.product-title', '.product-name', '#product-title',
        '[data-testid="product-title"]', '.pdp-title'
    ]

    DESCRIPTION_SELECTORS = [
        '.product-description', '.description', '#description',
        '[data-testid="product-description"]', '.pdp-description',
        '.product-details', '.product-info', '.overview',
        '[class*="description"]', '[id*="description"]'
    ]

    SPECIFICATIONS_SELECTORS = [
        '.specifications', '.specs', '#specifications', '#specs',
        '.product-specifications', '.technical-specs', '.tech-specs',
        'table.specifications', 'table.specs', '.spec-table',
        '[data-testid="specifications"]', '[class*="specification"]',
        '.product-attributes', '.attributes'
    ]

    IMAGE_SELECTORS = [
        '.product-image img', '.product-gallery img', '.pdp-image img',
        '[data-testid="product-image"]', '.product-media img',
        'img[class*="product"]', 'img[alt*="product"]'
    ]

    def __init__(
        self,
        timeout: int = 30,
        delay_between_requests: float = 1.5,
        headless: bool = True
    ):
        """
        Initialize the page analyzer.

        Args:
            timeout: Page load timeout in seconds
            delay_between_requests: Delay between page loads
            headless: Run browser in headless mode
        """
        self.timeout = timeout
        self.delay_between_requests = delay_between_requests
        self.headless = headless
        self._driver = None

    def _create_driver(self) -> webdriver.Chrome:
        """Create and configure Chrome WebDriver."""
        options = Options()

        if self.headless:
            options.add_argument('--headless=new')

        # Performance and stability options
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')  # Speed up by not loading images for analysis
        options.add_argument('--blink-settings=imagesEnabled=false')

        # User agent
        options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # Reduce memory usage
        options.add_argument('--disable-browser-side-navigation')
        options.add_argument('--disable-infobars')

        # Page load strategy - wait for DOM only, not all resources
        options.page_load_strategy = 'eager'

        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(self.timeout)
            return driver
        except WebDriverException as e:
            logger.error(f"Failed to create WebDriver: {e}")
            raise

    @contextmanager
    def get_driver(self):
        """Context manager for WebDriver lifecycle."""
        if self._driver is None:
            self._driver = self._create_driver()
        try:
            yield self._driver
        except Exception:
            # On error, recreate driver next time
            if self._driver:
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None
            raise

    def close(self):
        """Close the browser instance."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def analyze_page(self, url: str) -> PageMetrics:
        """
        Analyze a single page and extract metrics.

        Args:
            url: URL to analyze

        Returns:
            PageMetrics object with extracted data
        """
        metrics = PageMetrics(url=url)

        try:
            with self.get_driver() as driver:
                # Load page
                logger.debug(f"Loading page: {url}")
                driver.get(url)

                # Wait for JavaScript rendering
                self._wait_for_content(driver)

                # Get page source after JS rendering
                page_source = driver.page_source

                # Parse with BeautifulSoup
                soup = BeautifulSoup(page_source, 'lxml')

                # Extract metrics
                metrics.raw_title = self._extract_title(driver, soup)
                metrics.page_title = metrics.raw_title
                metrics.word_count = self._count_content_words(soup)
                metrics.has_description, metrics.description_text = self._check_description(soup)
                metrics.has_specifications, metrics.specifications_text = self._check_specifications(soup)
                metrics.image_count = self._count_product_images(soup)
                metrics.content_sections = self._find_content_sections(soup)

        except TimeoutException:
            metrics.error = "Page load timeout"
            logger.warning(f"Timeout loading page: {url}")
        except WebDriverException as e:
            metrics.error = f"WebDriver error: {str(e)[:100]}"
            logger.warning(f"WebDriver error for {url}: {e}")
        except Exception as e:
            metrics.error = f"Analysis error: {str(e)[:100]}"
            logger.error(f"Error analyzing page {url}: {e}")

        # Apply delay before next request
        time.sleep(self.delay_between_requests)

        return metrics

    def _wait_for_content(self, driver: webdriver.Chrome):
        """Wait for JavaScript content to render."""
        try:
            # Wait for body to be present
            WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Wait for common product elements
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
                )
            except TimeoutException:
                pass  # H1 might not exist

            # Additional wait for JS rendering
            time.sleep(2)

        except TimeoutException:
            logger.warning("Timeout waiting for page content")

    def _extract_title(self, driver: webdriver.Chrome, soup: BeautifulSoup) -> str:
        """Extract the page/product title."""
        # Try multiple methods to get the title

        # Method 1: Look for H1 or product title elements
        for selector in self.PRODUCT_TITLE_SELECTORS:
            try:
                elements = soup.select(selector)
                for elem in elements:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 2:
                        return text
            except Exception:
                continue

        # Method 2: Use the HTML title tag
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        # Method 3: Use driver title
        try:
            return driver.title or ""
        except Exception:
            return ""

    def _count_content_words(self, soup: BeautifulSoup) -> int:
        """
        Count words in the main content area, excluding navigation/headers/footers.
        """
        # Clone soup to avoid modifying original
        soup_copy = BeautifulSoup(str(soup), 'lxml')

        # Remove excluded elements
        for selector in self.EXCLUDE_SELECTORS:
            for element in soup_copy.select(selector):
                element.decompose()

        # Get text content
        text = soup_copy.get_text(separator=' ', strip=True)

        # Clean up text
        text = re.sub(r'\s+', ' ', text)

        # Count words
        words = text.split()

        # Filter out very short "words" (likely artifacts)
        words = [w for w in words if len(w) > 1]

        return len(words)

    def _check_description(self, soup: BeautifulSoup) -> tuple[bool, str]:
        """
        Check if page has a product description.

        Returns:
            Tuple of (has_description, description_text)
        """
        for selector in self.DESCRIPTION_SELECTORS:
            try:
                elements = soup.select(selector)
                for elem in elements:
                    text = elem.get_text(strip=True)
                    # Description should have meaningful content (at least a sentence)
                    if text and len(text) > 50:
                        return True, text[:500]  # Truncate for storage
            except Exception:
                continue

        # Also check for paragraphs with substantial content
        paragraphs = soup.find_all('p')
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 100:  # Substantial paragraph
                return True, text[:500]

        return False, ""

    def _check_specifications(self, soup: BeautifulSoup) -> tuple[bool, str]:
        """
        Check if page has technical specifications.

        Returns:
            Tuple of (has_specifications, specifications_text)
        """
        # Check for specification sections
        for selector in self.SPECIFICATIONS_SELECTORS:
            try:
                elements = soup.select(selector)
                for elem in elements:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:
                        return True, text[:500]
            except Exception:
                continue

        # Check for definition lists (often used for specs)
        dl_elements = soup.find_all('dl')
        for dl in dl_elements:
            text = dl.get_text(strip=True)
            if len(text) > 30:
                return True, text[:500]

        # Check for tables with spec-like content
        tables = soup.find_all('table')
        for table in tables:
            # Look for tables with technical content
            text = table.get_text(strip=True).lower()
            spec_keywords = ['dimension', 'weight', 'size', 'voltage', 'power',
                           'material', 'specification', 'technical', 'model']
            if any(kw in text for kw in spec_keywords):
                return True, table.get_text(strip=True)[:500]

        # Check for bullet lists with technical content
        lists = soup.find_all(['ul', 'ol'])
        for lst in lists:
            items = lst.find_all('li')
            if len(items) >= 3:  # At least 3 items
                text = lst.get_text(strip=True)
                if len(text) > 50:
                    return True, text[:500]

        return False, ""

    def _count_product_images(self, soup: BeautifulSoup) -> int:
        """Count product images on the page."""
        count = 0

        # Try specific product image selectors
        for selector in self.IMAGE_SELECTORS:
            try:
                images = soup.select(selector)
                count += len(images)
            except Exception:
                continue

        # If no specific product images found, count all meaningful images
        if count == 0:
            all_images = soup.find_all('img')
            for img in all_images:
                src = img.get('src', '') or img.get('data-src', '')
                alt = img.get('alt', '')

                # Filter out icons, logos, and tiny images
                if src and not any(x in src.lower() for x in ['icon', 'logo', 'sprite', 'pixel']):
                    # Check if it's likely a product image
                    if 'product' in src.lower() or 'product' in alt.lower():
                        count += 1
                    elif img.get('width') and img.get('height'):
                        try:
                            w = int(img.get('width', 0))
                            h = int(img.get('height', 0))
                            if w > 100 and h > 100:
                                count += 1
                        except ValueError:
                            pass

        return count

    def _find_content_sections(self, soup: BeautifulSoup) -> List[str]:
        """Find content section headings on the page."""
        sections = []

        # Look for section headings
        headings = soup.find_all(['h2', 'h3', 'h4'])
        for h in headings:
            text = h.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 100:
                sections.append(text)

        return sections[:10]  # Limit to first 10 sections


class BatchPageAnalyzer:
    """Analyzes multiple pages with progress tracking."""

    def __init__(
        self,
        timeout: int = 30,
        delay_between_requests: float = 1.5,
        max_retries: int = 3,
        headless: bool = True
    ):
        """
        Initialize the batch analyzer.

        Args:
            timeout: Page load timeout in seconds
            delay_between_requests: Delay between page loads
            max_retries: Maximum retries for failed pages
            headless: Run browser in headless mode
        """
        self.timeout = timeout
        self.delay_between_requests = delay_between_requests
        self.max_retries = max_retries
        self.headless = headless

    def analyze_urls(
        self,
        urls: List[str],
        progress_callback: Optional[callable] = None
    ) -> List[PageMetrics]:
        """
        Analyze multiple URLs.

        Args:
            urls: List of URLs to analyze
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            List of PageMetrics for each URL
        """
        results = []
        total = len(urls)

        analyzer = PageAnalyzer(
            timeout=self.timeout,
            delay_between_requests=self.delay_between_requests,
            headless=self.headless
        )

        try:
            for i, url in enumerate(urls):
                if progress_callback:
                    progress_callback(i + 1, total)

                # Analyze with retries
                metrics = self._analyze_with_retry(analyzer, url)
                results.append(metrics)

        finally:
            analyzer.close()

        return results

    def _analyze_with_retry(
        self,
        analyzer: PageAnalyzer,
        url: str
    ) -> PageMetrics:
        """Analyze a URL with retry logic."""
        last_error = None

        for attempt in range(self.max_retries):
            metrics = analyzer.analyze_page(url)

            if metrics.error is None:
                return metrics

            last_error = metrics.error
            logger.warning(
                f"Attempt {attempt + 1}/{self.max_retries} failed for {url}: {last_error}"
            )

            # Exponential backoff
            if attempt < self.max_retries - 1:
                time.sleep(2 ** (attempt + 1))

        # Return last failed metrics
        return PageMetrics(url=url, error=f"Failed after {self.max_retries} attempts: {last_error}")
