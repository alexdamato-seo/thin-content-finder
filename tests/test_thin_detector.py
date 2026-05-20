"""Tests for thin_detector module."""

import pytest
from src.thin_detector import (
    check_a_sku_url,
    check_b_sku_title_h1,
    build_result,
    DetectionResult,
    _is_sku_only,
)
from src.sitemap_parser import SitemapURL
from src.page_analyzer import PageResult


class TestCheckA:
    """Check A — SKU-style URL slug detection."""

    def test_known_thin_urls_flagged(self):
        assert check_a_sku_url('https://evidentscientific.com/ja/products/we402458/we402458') is True
        assert check_a_sku_url('https://evidentscientific.com/ja/products/ax0003/ax0003') is True
        assert check_a_sku_url('https://evidentscientific.com/ja/products/e9701832/e9701832') is True

    def test_descriptive_category_url_not_flagged(self):
        # Has category words (microscopes, stereo-microscopes) → NOT flagged
        assert check_a_sku_url(
            'https://evidentscientific.com/en/products/microscopes/stereo-microscopes/szx16'
        ) is False

    def test_single_sku_segment_flagged(self):
        assert check_a_sku_url('https://evidentscientific.com/en/products/ax0003') is True

    def test_category_with_sku_not_flagged(self):
        # 'microscopes' has no digits → breaks the all-SKU condition
        assert check_a_sku_url('https://evidentscientific.com/en/products/microscopes/ax0003') is False

    def test_non_product_url_not_flagged(self):
        assert check_a_sku_url('https://evidentscientific.com/en/about') is False

    def test_empty_products_path_not_flagged(self):
        assert check_a_sku_url('https://evidentscientific.com/en/products/') is False


class TestCheckB:
    """Check B — bare SKU in title or H1."""

    def test_sku_only_title_flagged(self):
        assert check_b_sku_title_h1('ax0003', '') is True
        assert check_b_sku_title_h1('we402458', '') is True
        assert check_b_sku_title_h1('e9701832', '') is True

    def test_sku_only_h1_flagged(self):
        assert check_b_sku_title_h1('', 'ax0003') is True

    def test_descriptive_title_not_flagged(self):
        assert check_b_sku_title_h1('SZX16 Stereo Microscope', '') is False
        assert check_b_sku_title_h1('20X Objective NA 0.4 FN 22.0 WD 1.3 mm', '') is False

    def test_title_with_site_suffix_still_flagged(self):
        assert check_b_sku_title_h1('ax0003 | Evident Scientific', '') is True
        assert check_b_sku_title_h1('we402458 - Evident Scientific', '') is True

    def test_empty_title_and_h1_not_flagged(self):
        assert check_b_sku_title_h1('', '') is False


class TestIsSkuOnly:
    def test_sku_matches(self):
        assert _is_sku_only('ax0003') is True
        assert _is_sku_only('we402458') is True
        assert _is_sku_only('e9701832') is True

    def test_descriptive_does_not_match(self):
        assert _is_sku_only('SZX16 Stereo Microscope') is False
        assert _is_sku_only('Stereo Microscope') is False

    def test_empty_string_does_not_match(self):
        assert _is_sku_only('') is False

    def test_site_suffix_stripped(self):
        assert _is_sku_only('ax0003 | Evident Scientific') is True


class TestBuildResult:
    def _make_su(self, url, locale='en'):
        return SitemapURL(url=url, locale=locale)

    def _make_pr(self, url, status=200, title='', h1='', error=None, skipped=False):
        return PageResult(url=url, http_status=status, page_title=title, h1=h1,
                          error=error, check_b_skipped=skipped)

    def test_flagged_by_both(self):
        url = 'https://evidentscientific.com/ja/products/ax0003/ax0003'
        result = build_result(
            self._make_su(url, 'ja'),
            self._make_pr(url, title='ax0003', h1='ax0003'),
        )
        assert result.flagged is True
        assert result.check_a_sku_url is True
        assert result.check_b_sku_title_h1 is True
        assert 'SKU-style URL slug' in result.flag_reasons
        assert 'Title/H1 is bare SKU' in result.flag_reasons

    def test_flagged_by_check_a_only(self):
        url = 'https://evidentscientific.com/en/products/ax0003/ax0003'
        result = build_result(
            self._make_su(url),
            self._make_pr(url, title='AX0003 Compact Camera Adapter', h1='AX0003 Adapter'),
        )
        assert result.flagged is True
        assert result.check_a_sku_url is True
        assert result.check_b_sku_title_h1 is False

    def test_flagged_by_check_b_only(self):
        url = 'https://evidentscientific.com/en/products/microscopes/stereo/szx16'
        result = build_result(
            self._make_su(url),
            self._make_pr(url, title='szx16', h1='szx16'),
        )
        assert result.flagged is True
        assert result.check_a_sku_url is False
        assert result.check_b_sku_title_h1 is True

    def test_clean_page_not_flagged(self):
        url = 'https://evidentscientific.com/en/products/microscopes/stereo-microscopes/szx16'
        result = build_result(
            self._make_su(url),
            self._make_pr(url, title='SZX16 Stereo Microscope', h1='SZX16 Stereo Microscope'),
        )
        assert result.flagged is False
        assert result.flag_reasons == ''

    def test_fetch_error_sets_check_b_skipped(self):
        url = 'https://evidentscientific.com/en/products/ax0003/ax0003'
        result = build_result(
            self._make_su(url),
            self._make_pr(url, error='Timeout', skipped=True),
        )
        assert result.check_b_skipped is True
        assert result.check_b_sku_title_h1 is False
        assert 'Fetch error' in result.flag_reasons

    def test_http_status_recorded(self):
        url = 'https://evidentscientific.com/en/products/ax0003/ax0003'
        result = build_result(
            self._make_su(url),
            self._make_pr(url, status=404, title='ax0003'),
        )
        assert result.http_status == 404

    def test_locale_preserved(self):
        url = 'https://evidentscientific.com/ko/products/ax0003/ax0003'
        result = build_result(
            self._make_su(url, 'ko'),
            self._make_pr(url),
        )
        assert result.locale == 'ko'
