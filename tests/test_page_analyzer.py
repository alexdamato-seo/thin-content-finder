"""Tests for page_analyzer module."""

import pytest
from src.page_analyzer import PageMetrics, PageAnalyzer


class TestPageMetrics:
    """Tests for PageMetrics dataclass."""

    def test_page_metrics_defaults(self):
        """Test PageMetrics default values."""
        metrics = PageMetrics(url="https://example.com")

        assert metrics.url == "https://example.com"
        assert metrics.page_title == ""
        assert metrics.word_count == 0
        assert metrics.has_description is False
        assert metrics.has_specifications is False
        assert metrics.image_count == 0
        assert metrics.error is None

    def test_page_metrics_with_values(self):
        """Test PageMetrics with custom values."""
        metrics = PageMetrics(
            url="https://example.com/product",
            page_title="Test Product",
            word_count=150,
            has_description=True,
            has_specifications=True,
            image_count=5,
            description_text="This is a test description."
        )

        assert metrics.page_title == "Test Product"
        assert metrics.word_count == 150
        assert metrics.has_description is True
        assert metrics.image_count == 5


class TestPageAnalyzer:
    """Tests for PageAnalyzer class (unit tests only, no browser)."""

    def test_exclude_selectors_defined(self):
        """Test that exclude selectors are properly defined."""
        assert len(PageAnalyzer.EXCLUDE_SELECTORS) > 0
        assert 'nav' in PageAnalyzer.EXCLUDE_SELECTORS
        assert 'header' in PageAnalyzer.EXCLUDE_SELECTORS
        assert 'footer' in PageAnalyzer.EXCLUDE_SELECTORS

    def test_product_title_selectors_defined(self):
        """Test that product title selectors are defined."""
        assert len(PageAnalyzer.PRODUCT_TITLE_SELECTORS) > 0
        assert 'h1' in PageAnalyzer.PRODUCT_TITLE_SELECTORS

    def test_description_selectors_defined(self):
        """Test that description selectors are defined."""
        assert len(PageAnalyzer.DESCRIPTION_SELECTORS) > 0
        assert '.product-description' in PageAnalyzer.DESCRIPTION_SELECTORS

    def test_specifications_selectors_defined(self):
        """Test that specifications selectors are defined."""
        assert len(PageAnalyzer.SPECIFICATIONS_SELECTORS) > 0
        assert '.specifications' in PageAnalyzer.SPECIFICATIONS_SELECTORS


# Integration tests would require Selenium and a browser
# These are marked to skip if browser not available

@pytest.mark.skip(reason="Requires browser setup")
class TestPageAnalyzerIntegration:
    """Integration tests for PageAnalyzer (requires browser)."""

    def test_analyze_thin_page(self):
        """Test analysis of known thin page."""
        analyzer = PageAnalyzer(timeout=30, headless=True)
        try:
            metrics = analyzer.analyze_page(
                "https://evidentscientific.com/en/products/n2750300/n2750300"
            )
            assert metrics.error is None
            # Thin page characteristics
            assert metrics.word_count < 100
        finally:
            analyzer.close()

    def test_analyze_non_thin_page(self):
        """Test analysis of known non-thin page."""
        analyzer = PageAnalyzer(timeout=30, headless=True)
        try:
            metrics = analyzer.analyze_page(
                "https://evidentscientific.com/en/products/n2181200/n2181200"
            )
            assert metrics.error is None
            # Non-thin page should have meaningful title
            assert "objective" in metrics.page_title.lower() or "NA" in metrics.page_title
        finally:
            analyzer.close()
