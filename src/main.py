#!/usr/bin/env python3
"""
Thin Content Finder — Evident Scientific

Crawls 8 locale-specific sitemaps, identifies product URLs that are likely
"thin content" via SKU URL patterns and page title/H1 checks, and outputs
two CSV reports.

Usage:
    python -m src.main [options]
    python src/main.py  [options]
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

from .sitemap_parser import SitemapParser, SitemapURL
from .page_analyzer import PageFetcher, PageResult
from .thin_detector import build_result, DetectionResult
from .report_generator import generate_reports, print_summary

SITEMAP_URLS = [
    'https://evidentscientific.com/sitemap-en.xml',
    'https://evidentscientific.com/sitemap-es.xml',
    'https://evidentscientific.com/sitemap-fr.xml',
    'https://evidentscientific.com/sitemap-de.xml',
    'https://evidentscientific.com/sitemap-it.xml',
    'https://evidentscientific.com/sitemap-ko.xml',
    'https://evidentscientific.com/sitemap-ja.xml',
    'https://evidentscientific.com/sitemap-zh.xml',
]

BASE_URL = 'https://evidentscientific.com'


def setup_logging(verbose: bool = False) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    logs_dir = Path('./logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    log_file = logs_dir / f'audit_{timestamp}.log'
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s — %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('charset_normalizer').setLevel(logging.WARNING)


def collect_product_urls(
    sitemaps: List[str],
    timeout: int = 30,
    max_retries: int = 3,
) -> List[SitemapURL]:
    parser = SitemapParser(timeout=timeout, max_retries=max_retries)
    parser.load_robots(BASE_URL)

    all_urls: List[SitemapURL] = []
    print(f'\nFetching {len(sitemaps)} sitemaps...')
    for sitemap_url in tqdm(sitemaps, desc='Parsing sitemaps'):
        urls = parser.process_sitemap(sitemap_url)
        all_urls.extend(urls)

    print(f'Total product URLs found: {len(all_urls):,}')
    return all_urls


def crawl_pages(
    urls: List[SitemapURL],
    timeout: int = 30,
    min_delay: float = 0.5,
    max_delay: float = 1.0,
    max_retries: int = 3,
) -> List[PageResult]:
    fetcher = PageFetcher(
        timeout=timeout,
        min_delay=min_delay,
        max_delay=max_delay,
        max_retries=max_retries,
    )
    results: List[PageResult] = []
    print(f'\nCrawling {len(urls):,} product pages for title/H1 (Check B)...')
    for sitemap_url in tqdm(urls, desc='Crawling pages', unit='page'):
        result = fetcher.fetch(sitemap_url.url)
        if result.error:
            logging.getLogger(__name__).warning(
                f"HTTP {result.http_status or 'ERR'} — {sitemap_url.url} — {result.error}"
            )
        results.append(result)
    return results


def load_urls_from_file(path: str) -> List[SitemapURL]:
    """
    Load product URLs from a plain-text file (one URL per line).

    Skips blank lines and comment lines starting with #.
    Locale is extracted from each URL path; falls back to 'en'.
    """
    from .sitemap_parser import _locale_from_url, _locale_from_sitemap_url
    urls: List[SitemapURL] = []
    with open(path, 'r', encoding='utf-8') as f:
        for raw in f:
            url = raw.strip()
            if not url or url.startswith('#'):
                continue
            if '/products/' not in url:
                continue
            locale = _locale_from_url(url) or 'en'
            urls.append(SitemapURL(url=url, locale=locale))
    print(f'Loaded {len(urls):,} product URLs from {path}')
    return urls


def run_audit(
    sitemaps: Optional[List[str]] = None,
    urls_file: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    output_dir: str = './output',
    timeout: int = 30,
    min_delay: float = 0.5,
    max_delay: float = 1.0,
    max_retries: int = 3,
) -> List[DetectionResult]:
    start = time.time()
    sitemap_list = sitemaps or SITEMAP_URLS

    url_only_mode = urls_file is not None

    print('\n' + '=' * 60)
    print('THIN CONTENT FINDER — EVIDENT SCIENTIFIC')
    print('=' * 60)
    if url_only_mode:
        print('Mode: URL-pattern only (Check A, no page fetching)')
    else:
        print(f'Sitemaps: {len(sitemap_list)}')

    # Step 1 — collect product URLs
    if url_only_mode:
        product_urls = load_urls_from_file(urls_file)
    else:
        product_urls = collect_product_urls(sitemap_list, timeout=timeout, max_retries=max_retries)

    if not product_urls:
        print('No product URLs found. Exiting.')
        return []

    if limit and limit < len(product_urls):
        print(f'Limiting to first {limit} URLs (--limit flag)')
        product_urls = product_urls[:limit]

    if dry_run:
        print(f'\n[DRY RUN] {len(product_urls):,} product URLs found. Exiting.')
        return []

    # Step 2 — Check B (fetch pages for title/H1), or skip in URL-only mode
    from .page_analyzer import PageResult
    if url_only_mode:
        print(f'\nURL-only mode: applying Check A to {len(product_urls):,} URLs (Check B skipped)...')
        page_result_map = {
            su.url: PageResult(url=su.url, check_b_skipped=True)
            for su in product_urls
        }
    else:
        page_results = crawl_pages(
            product_urls,
            timeout=timeout,
            min_delay=min_delay,
            max_delay=max_delay,
            max_retries=max_retries,
        )
        page_result_map = {pr.url: pr for pr in page_results}

    # Step 3 — apply Check A + Check B, build DetectionResults
    results: List[DetectionResult] = []
    for su in product_urls:
        pr = page_result_map.get(su.url) or PageResult(url=su.url, check_b_skipped=True)
        results.append(build_result(su, pr))

    # Step 4 — generate reports
    print('\nGenerating reports...')
    thin_path, all_path = generate_reports(results, output_dir=output_dir)
    print(f'  {thin_path}')
    print(f'  {all_path}')

    # Step 5 — summary
    print_summary(results, total_product_urls=len(product_urls))

    elapsed = time.time() - start
    h, rem = divmod(int(elapsed), 3600)
    m, s = divmod(rem, 60)
    print(f'\nCompleted in {h}h {m}m {s}s')
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Identify thin product pages across locale sitemaps.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                      # full audit
  python -m src.main --limit 50           # test on first 50 URLs
  python -m src.main --dry-run            # preview URL count only
  python -m src.main --output-dir ./out   # custom output directory
        """,
    )
    parser.add_argument('--sitemaps', '-s', nargs='+', help='Override sitemap URLs')
    parser.add_argument(
        '--urls-file', '-u',
        type=str,
        metavar='FILE',
        help='Plain-text file of product URLs (one per line). Skips sitemap fetching '
             'and page crawling — runs Check A (URL pattern) only.',
    )
    parser.add_argument('--limit', '-l', type=int, help='Cap number of URLs to analyze')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Preview without crawling')
    parser.add_argument('--output-dir', '-o', default='./output', help='Output directory')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout (seconds)')
    parser.add_argument('--min-delay', type=float, default=0.5, help='Min delay between requests (s)')
    parser.add_argument('--max-delay', type=float, default=1.0, help='Max delay between requests (s)')
    parser.add_argument('--max-retries', type=int, default=3, help='Max retry attempts')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(verbose=args.verbose)

    try:
        results = run_audit(
            sitemaps=args.sitemaps,
            urls_file=args.urls_file,
            limit=args.limit,
            dry_run=args.dry_run,
            output_dir=args.output_dir,
            timeout=args.timeout,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            max_retries=args.max_retries,
        )
        if results or args.dry_run:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print('\n\nInterrupted.')
        sys.exit(130)
    except Exception as e:
        logging.exception(f'Audit failed: {e}')
        print(f'\nError: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
