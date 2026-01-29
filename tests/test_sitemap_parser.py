"""Tests for sitemap_parser module."""

import pytest
from src.sitemap_parser import SitemapParser, SitemapURL


class TestSitemapParser:
    """Tests for SitemapParser class."""

    def test_product_url_pattern_matches_valid_urls(self):
        """Test that product URL pattern correctly identifies product pages."""
        parser = SitemapParser()

        valid_urls = [
            "https://evidentscientific.com/en/products/n2750300/n2750300",
            "https://evidentscientific.com/de/products/ABC123/ABC123",
            "https://evidentscientific.com/ja/products/U-B30050/U-B30050",
        ]

        for url in valid_urls:
            match = parser.PRODUCT_URL_PATTERN.search(url)
            assert match is not None, f"Should match: {url}"

    def test_product_url_pattern_rejects_non_product_urls(self):
        """Test that non-product URLs are not matched."""
        parser = SitemapParser()

        invalid_urls = [
            "https://evidentscientific.com/en/about",
            "https://evidentscientific.com/en/products",
            "https://evidentscientific.com/en/contact",
        ]

        for url in invalid_urls:
            match = parser.PRODUCT_URL_PATTERN.search(url)
            assert match is None, f"Should not match: {url}"

    def test_language_extraction(self):
        """Test language code extraction from URLs."""
        parser = SitemapParser()

        test_cases = [
            ("https://evidentscientific.com/en/products/test/test", "en"),
            ("https://evidentscientific.com/de/products/test/test", "de"),
            ("https://evidentscientific.com/ja/products/test/test", "ja"),
        ]

        for url, expected_lang in test_cases:
            match = parser.LANGUAGE_PATTERN.search(url)
            assert match is not None
            assert match.group(1) == expected_lang

    def test_filter_product_urls(self):
        """Test URL filtering to product pages only."""
        parser = SitemapParser()

        urls = [
            "https://evidentscientific.com/en/products/n2750300/n2750300",
            "https://evidentscientific.com/en/about",
            "https://evidentscientific.com/de/products/ABC123/ABC123",
            "https://evidentscientific.com/contact",
        ]

        filtered = parser.filter_product_urls(urls)

        assert len(filtered) == 2
        assert all(isinstance(u, SitemapURL) for u in filtered)
        assert filtered[0].sku == "n2750300"
        assert filtered[1].sku == "ABC123"


class TestSitemapURL:
    """Tests for SitemapURL dataclass."""

    def test_sitemap_url_creation(self):
        """Test SitemapURL dataclass creation."""
        url = SitemapURL(
            url="https://evidentscientific.com/en/products/test/test",
            language="en",
            sku="test"
        )

        assert url.url == "https://evidentscientific.com/en/products/test/test"
        assert url.language == "en"
        assert url.sku == "test"
        assert url.lastmod is None
