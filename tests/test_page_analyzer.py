"""Tests for page_analyzer module."""

import pytest
from src.page_analyzer import PageResult, PageFetcher


class TestPageResult:
    def test_defaults(self):
        r = PageResult(url='https://example.com')
        assert r.url == 'https://example.com'
        assert r.http_status is None
        assert r.page_title == ''
        assert r.h1 == ''
        assert r.error is None
        assert r.check_b_skipped is False

    def test_with_values(self):
        r = PageResult(
            url='https://example.com/product',
            http_status=200,
            page_title='Great Product',
            h1='Great Product',
        )
        assert r.http_status == 200
        assert r.page_title == 'Great Product'
        assert r.h1 == 'Great Product'

    def test_error_state(self):
        r = PageResult(url='https://example.com', error='Timeout', check_b_skipped=True)
        assert r.error == 'Timeout'
        assert r.check_b_skipped is True


class TestPageFetcher:
    def test_fetcher_created_with_defaults(self):
        fetcher = PageFetcher()
        assert fetcher.timeout == 30
        assert fetcher.min_delay == 0.5
        assert fetcher.max_delay == 1.0

    def test_fetcher_custom_params(self):
        fetcher = PageFetcher(timeout=10, min_delay=0.1, max_delay=0.2)
        assert fetcher.timeout == 10
        assert fetcher.min_delay == 0.1
        assert fetcher.max_delay == 0.2

    def test_fetch_unreachable_url_returns_error(self):
        fetcher = PageFetcher(timeout=3, min_delay=0, max_delay=0, max_retries=0)
        result = fetcher.fetch('http://localhost:19999/no-such-host')
        assert result.check_b_skipped is True
        assert result.error is not None
        assert result.http_status is None

    def test_fetch_parses_html(self, monkeypatch):
        """Test HTML parsing logic via a monkeypatched session."""
        from unittest.mock import MagicMock
        import requests

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.text = """
        <html>
          <head><title>ax0003 | Evident Scientific</title></head>
          <body><h1>ax0003</h1></body>
        </html>"""
        fake_response.raise_for_status = MagicMock()

        fetcher = PageFetcher(min_delay=0, max_delay=0)
        monkeypatch.setattr(fetcher.session, 'get', lambda *a, **kw: fake_response)

        result = fetcher.fetch('https://evidentscientific.com/en/products/ax0003/ax0003')
        assert result.http_status == 200
        assert result.page_title == 'ax0003 | Evident Scientific'
        assert result.h1 == 'ax0003'
        assert result.check_b_skipped is False
        assert result.error is None
