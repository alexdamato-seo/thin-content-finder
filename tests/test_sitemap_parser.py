"""Tests for sitemap_parser module."""

import pytest
from src.sitemap_parser import (
    SitemapParser,
    SitemapURL,
    _locale_from_sitemap_url,
    _locale_from_url,
)


class TestLocaleHelpers:
    def test_locale_from_sitemap_url(self):
        assert _locale_from_sitemap_url('https://evidentscientific.com/sitemap-ja.xml') == 'ja'
        assert _locale_from_sitemap_url('https://evidentscientific.com/sitemap-en.xml') == 'en'
        assert _locale_from_sitemap_url('https://evidentscientific.com/sitemap-zh.xml') == 'zh'
        assert _locale_from_sitemap_url('https://evidentscientific.com/sitemap-en-1.xml') == 'en'

    def test_locale_from_url_with_prefix(self):
        assert _locale_from_url('https://evidentscientific.com/ja/products/ax0003/ax0003') == 'ja'
        assert _locale_from_url('https://evidentscientific.com/de/products/test/test') == 'de'

    def test_locale_from_url_no_prefix(self):
        assert _locale_from_url('https://evidentscientific.com/products/ax0003/ax0003') is None


class TestSitemapParser:
    def test_fetch_xml_returns_none_on_bad_url(self):
        parser = SitemapParser(timeout=5)
        result = parser.fetch_xml('http://localhost:1/nonexistent.xml')
        assert result is None

    def test_parse_xml_urlset(self):
        parser = SitemapParser()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://evidentscientific.com/en/products/ax0003/ax0003</loc></url>
          <url><loc>https://evidentscientific.com/en/about</loc></url>
          <url><loc>https://evidentscientific.com/ja/products/we402458/we402458</loc><lastmod>2024-01-01</lastmod></url>
        </urlset>"""
        entries = parser._parse_xml(xml, 'test-sitemap.xml')
        assert len(entries) == 3
        urls = [e['url'] for e in entries]
        assert 'https://evidentscientific.com/en/products/ax0003/ax0003' in urls
        assert 'https://evidentscientific.com/en/about' in urls

    def test_process_sitemap_filters_to_products(self, monkeypatch):
        parser = SitemapParser()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://evidentscientific.com/en/products/ax0003/ax0003</loc></url>
          <url><loc>https://evidentscientific.com/en/about</loc></url>
        </urlset>"""
        monkeypatch.setattr(parser, 'fetch_xml', lambda url: xml)
        results = parser.process_sitemap('https://evidentscientific.com/sitemap-en.xml')
        assert len(results) == 1
        assert results[0].url == 'https://evidentscientific.com/en/products/ax0003/ax0003'
        assert results[0].locale == 'en'

    def test_process_sitemap_returns_empty_on_fetch_failure(self, monkeypatch):
        parser = SitemapParser()
        monkeypatch.setattr(parser, 'fetch_xml', lambda url: None)
        results = parser.process_sitemap('https://evidentscientific.com/sitemap-en.xml')
        assert results == []

    def test_sitemap_url_dataclass(self):
        su = SitemapURL(url='https://example.com/products/ax0003/ax0003', locale='en')
        assert su.url == 'https://example.com/products/ax0003/ax0003'
        assert su.locale == 'en'
        assert su.lastmod is None

    def test_robots_disallowed_urls_skipped(self, monkeypatch):
        parser = SitemapParser()
        monkeypatch.setattr(parser, 'is_allowed', lambda url: False)
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://evidentscientific.com/en/products/ax0003/ax0003</loc></url>
        </urlset>"""
        monkeypatch.setattr(parser, 'fetch_xml', lambda url: xml)
        results = parser.process_sitemap('https://evidentscientific.com/sitemap-en.xml')
        assert results == []
