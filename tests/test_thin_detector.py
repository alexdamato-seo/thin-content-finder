"""Tests for thin_detector module."""

import pytest
from src.page_analyzer import PageMetrics
from src.thin_detector import (
    ThinPageDetector,
    DetectionThresholds,
    DetectionResult,
    ThinPageStatus,
)


class TestThinPageDetector:
    """Tests for ThinPageDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a detector with default thresholds."""
        return ThinPageDetector()

    def test_sku_only_title_is_non_descriptive(self, detector):
        """Test that titles with only SKU are detected as non-descriptive."""
        assert detector._is_title_non_descriptive("N2750300", "N2750300") is True
        assert detector._is_title_non_descriptive("U-B30050", "U-B30050") is True

    def test_descriptive_title_is_not_non_descriptive(self, detector):
        """Test that titles with descriptions are not flagged."""
        title = "20X Objective NA 0.4 FN 22.0 WD 1.3 mm"
        assert detector._is_title_non_descriptive(title, "n2181200") is False

    def test_technical_specs_in_title(self, detector):
        """Test detection of technical specifications in titles."""
        titles_with_specs = [
            "20X Objective NA 0.4",
            "Lens FN 22.0 WD 1.3 mm",
            "LED Light Source 550nm",
            "10X magnification",
        ]

        for title in titles_with_specs:
            assert detector._title_has_technical_specs(title) is True

    def test_thin_page_detection(self, detector):
        """Test thin page is correctly detected."""
        # Simulate a thin page (like n2750300)
        metrics = PageMetrics(
            url="https://evidentscientific.com/en/products/n2750300/n2750300",
            page_title="N2750300",
            word_count=50,
            has_description=False,
            has_specifications=False,
            image_count=1
        )

        result = detector.detect(metrics, "en", "n2750300")

        assert result.status == ThinPageStatus.THIN
        assert result.is_thin is True
        assert len(result.reasons) > 0

    def test_non_thin_page_with_tech_specs_title(self, detector):
        """Test page with technical title is not flagged as thin."""
        # Simulate a good page (like n2181200)
        metrics = PageMetrics(
            url="https://evidentscientific.com/en/products/n2181200/n2181200",
            page_title="20X Objective NA 0.4 FN 22.0 WD 1.3 mm",
            word_count=80,  # Below threshold but title has specs
            has_description=False,
            has_specifications=True,
            image_count=2
        )

        result = detector.detect(metrics, "en", "n2181200")

        assert result.status == ThinPageStatus.OK
        assert result.is_thin is False

    def test_error_page_detection(self, detector):
        """Test that error pages are classified correctly."""
        metrics = PageMetrics(
            url="https://evidentscientific.com/en/products/test/test",
            error="Page load timeout"
        )

        result = detector.detect(metrics, "en", "test")

        assert result.status == ThinPageStatus.ERROR
        assert result.error == "Page load timeout"


class TestDetectionThresholds:
    """Tests for DetectionThresholds configuration."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = DetectionThresholds()

        assert thresholds.min_word_count == 100
        assert thresholds.require_description is True
        assert thresholds.require_specifications is True

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = DetectionThresholds(
            min_word_count=50,
            require_description=False,
            require_specifications=False
        )

        assert thresholds.min_word_count == 50
        assert thresholds.require_description is False
        assert thresholds.require_specifications is False

    def test_custom_thresholds_affect_detection(self):
        """Test that custom thresholds change detection behavior."""
        strict_detector = ThinPageDetector(DetectionThresholds(min_word_count=200))
        lenient_detector = ThinPageDetector(DetectionThresholds(min_word_count=50))

        metrics = PageMetrics(
            url="https://example.com/products/test/test",
            page_title="Product Description Here",
            word_count=100,
            has_description=True,
            has_specifications=True,
            image_count=1
        )

        strict_result = strict_detector.detect(metrics, "en", "test")
        lenient_result = lenient_detector.detect(metrics, "en", "test")

        # Strict should flag as thin (100 < 200)
        # Lenient should pass (100 > 50)
        assert strict_result.status == ThinPageStatus.THIN or len(strict_result.reasons) > 0
        assert lenient_result.status == ThinPageStatus.OK
