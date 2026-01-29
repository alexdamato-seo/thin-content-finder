"""
Thin Page Detector Module

Applies detection logic to identify thin pages based on content metrics.
"""

import re
import logging
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

from .page_analyzer import PageMetrics

logger = logging.getLogger(__name__)


class ThinPageStatus(Enum):
    """Status classification for a page."""
    THIN = "THIN"
    OK = "OK"
    ERROR = "ERROR"


@dataclass
class DetectionResult:
    """Result of thin page detection."""
    url: str
    language: str
    sku: str
    page_title: str
    word_count: int
    has_description: bool
    has_specifications: bool
    image_count: int
    status: ThinPageStatus
    reasons: List[str]
    error: Optional[str] = None

    @property
    def is_thin(self) -> bool:
        return self.status == ThinPageStatus.THIN


@dataclass
class DetectionThresholds:
    """Configuration thresholds for thin page detection."""
    min_word_count: int = 100
    require_description: bool = True
    require_specifications: bool = True
    min_title_words: int = 2  # Titles with only SKU typically have 1 "word"


class ThinPageDetector:
    """Detects thin pages based on content metrics."""

    # Pattern to identify SKU-only titles
    # SKUs are typically alphanumeric codes like "N2750300", "U-B30050"
    SKU_PATTERN = re.compile(r'^[A-Z]{0,3}[-]?[A-Z0-9]{4,}$', re.IGNORECASE)

    # Technical specification patterns in titles
    TECH_SPEC_PATTERNS = [
        r'\d+[xX]\s*(?:objective|magnification)',  # "20X Objective"
        r'NA\s*[\d.]+',  # "NA 0.4"
        r'FN\s*[\d.]+',  # "FN 22.0"
        r'WD\s*[\d.]+',  # "WD 1.3"
        r'\d+\s*mm',  # "1.3 mm"
        r'\d+\s*[μu]m',  # "10 μm"
        r'\d+\s*nm',  # "550 nm"
        r'(?:LED|UV|IR|NIR)',  # Light types
        r'\d+\s*V(?:olt)?',  # Voltage
        r'\d+\s*W(?:att)?',  # Wattage
        r'\d+\s*°',  # Degrees
        r'\d+\.\d+',  # Decimal numbers (often technical specs)
    ]

    def __init__(self, thresholds: Optional[DetectionThresholds] = None):
        """
        Initialize the detector.

        Args:
            thresholds: Detection thresholds configuration
        """
        self.thresholds = thresholds or DetectionThresholds()

    def detect(
        self,
        metrics: PageMetrics,
        language: str,
        sku: str
    ) -> DetectionResult:
        """
        Detect if a page is thin based on its metrics.

        Args:
            metrics: Page metrics extracted from analysis
            language: Language code
            sku: Product SKU

        Returns:
            DetectionResult with classification and reasons
        """
        # Handle error cases
        if metrics.error:
            return DetectionResult(
                url=metrics.url,
                language=language,
                sku=sku,
                page_title=metrics.page_title,
                word_count=metrics.word_count,
                has_description=metrics.has_description,
                has_specifications=metrics.has_specifications,
                image_count=metrics.image_count,
                status=ThinPageStatus.ERROR,
                reasons=[],
                error=metrics.error
            )

        reasons = []
        is_thin = False

        # Check 1: Non-descriptive title (just SKU)
        title_is_non_descriptive = self._is_title_non_descriptive(
            metrics.page_title, sku
        )
        if title_is_non_descriptive:
            reasons.append("Title contains only SKU without descriptive text")

        # Check 2: Low word count
        low_word_count = metrics.word_count < self.thresholds.min_word_count
        if low_word_count:
            reasons.append(
                f"Low word count ({metrics.word_count} < {self.thresholds.min_word_count})"
            )

        # Check 3: Missing description
        missing_description = (
            self.thresholds.require_description and not metrics.has_description
        )
        if missing_description:
            reasons.append("No product description found")

        # Check 4: Missing specifications
        missing_specs = (
            self.thresholds.require_specifications and not metrics.has_specifications
        )
        if missing_specs:
            reasons.append("No technical specifications found")

        # Determine if page is thin based on combined criteria
        # A page is THIN if:
        # - Title is non-descriptive AND (low word count OR missing description)
        # OR
        # - Multiple content issues present (low words + no description + no specs)

        if title_is_non_descriptive:
            if low_word_count or missing_description:
                is_thin = True
        elif low_word_count and missing_description and missing_specs:
            # Even with a descriptive title, if all content is missing, it's thin
            is_thin = True

        # Special case: Title with technical specs is NOT thin
        # even if other content is minimal
        if self._title_has_technical_specs(metrics.page_title):
            if not (low_word_count and missing_description and missing_specs):
                is_thin = False
                reasons = [r for r in reasons if "Title" not in r]

        status = ThinPageStatus.THIN if is_thin else ThinPageStatus.OK

        return DetectionResult(
            url=metrics.url,
            language=language,
            sku=sku,
            page_title=metrics.page_title,
            word_count=metrics.word_count,
            has_description=metrics.has_description,
            has_specifications=metrics.has_specifications,
            image_count=metrics.image_count,
            status=status,
            reasons=reasons if is_thin else []
        )

    def _is_title_non_descriptive(self, title: str, sku: str) -> bool:
        """
        Check if a title is non-descriptive (contains only SKU or minimal info).

        A non-descriptive title:
        - Contains only the SKU
        - Is very short with no meaningful words
        - Has no technical specifications or product description

        Examples of non-descriptive titles:
        - "N2750300" (just SKU)
        - "U-B30050" (just SKU)
        - "Product N2750300" (minimal wrapper around SKU)

        Examples of descriptive titles:
        - "20X Objective NA 0.4 FN 22.0 WD 1.3 mm" (technical specs)
        - "High-Resolution Microscope Lens 50mm" (descriptive)
        """
        if not title:
            return True

        title_clean = title.strip()

        # Check if title is exactly the SKU
        if title_clean.upper() == sku.upper():
            return True

        # Check if title matches SKU pattern (alphanumeric code only)
        if self.SKU_PATTERN.match(title_clean):
            return True

        # Check if title is just SKU with common prefixes
        sku_variations = [
            sku.upper(),
            sku.lower(),
            f"Product {sku}",
            f"Item {sku}",
            f"Model {sku}",
        ]
        if title_clean in sku_variations or title_clean.upper() in [v.upper() for v in sku_variations]:
            return True

        # Check word count in title (excluding the SKU)
        title_without_sku = re.sub(re.escape(sku), '', title_clean, flags=re.IGNORECASE)
        title_words = [w for w in title_without_sku.split() if len(w) > 2]

        if len(title_words) < self.thresholds.min_title_words:
            # Few words, but check for technical specs
            if not self._title_has_technical_specs(title_clean):
                return True

        return False

    def _title_has_technical_specs(self, title: str) -> bool:
        """
        Check if a title contains technical specifications.

        Technical specifications include:
        - Magnification (20X, 40X)
        - Numerical aperture (NA 0.4)
        - Field number (FN 22.0)
        - Working distance (WD 1.3 mm)
        - Measurements (mm, μm, nm)
        - Voltages, wattages
        - Other technical parameters
        """
        if not title:
            return False

        for pattern in self.TECH_SPEC_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return True

        return False

    def detect_batch(
        self,
        metrics_list: List[PageMetrics],
        language: str,
        skus: List[str]
    ) -> List[DetectionResult]:
        """
        Detect thin pages in a batch.

        Args:
            metrics_list: List of page metrics
            language: Language code for all pages
            skus: List of SKUs corresponding to metrics

        Returns:
            List of DetectionResult objects
        """
        results = []
        for metrics, sku in zip(metrics_list, skus):
            result = self.detect(metrics, language, sku)
            results.append(result)
        return results


def summarize_results(results: List[DetectionResult]) -> dict:
    """
    Generate summary statistics from detection results.

    Args:
        results: List of detection results

    Returns:
        Dictionary with summary statistics
    """
    total = len(results)
    thin_count = sum(1 for r in results if r.status == ThinPageStatus.THIN)
    ok_count = sum(1 for r in results if r.status == ThinPageStatus.OK)
    error_count = sum(1 for r in results if r.status == ThinPageStatus.ERROR)

    thin_percent = (thin_count / total * 100) if total > 0 else 0
    ok_percent = (ok_count / total * 100) if total > 0 else 0
    error_percent = (error_count / total * 100) if total > 0 else 0

    # Breakdown by reason
    reason_counts = {}
    for result in results:
        for reason in result.reasons:
            # Normalize reason for counting
            reason_key = reason.split('(')[0].strip()
            reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1

    # Breakdown by language
    language_stats = {}
    for result in results:
        lang = result.language
        if lang not in language_stats:
            language_stats[lang] = {'total': 0, 'thin': 0, 'ok': 0, 'error': 0}
        language_stats[lang]['total'] += 1
        if result.status == ThinPageStatus.THIN:
            language_stats[lang]['thin'] += 1
        elif result.status == ThinPageStatus.OK:
            language_stats[lang]['ok'] += 1
        else:
            language_stats[lang]['error'] += 1

    return {
        'total': total,
        'thin': thin_count,
        'ok': ok_count,
        'error': error_count,
        'thin_percent': round(thin_percent, 1),
        'ok_percent': round(ok_percent, 1),
        'error_percent': round(error_percent, 1),
        'reason_breakdown': reason_counts,
        'language_breakdown': language_stats
    }
