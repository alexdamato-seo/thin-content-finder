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


def run_audit(
    sitemaps: Optional[List[str]] = None,
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

    print('\n' + '=' * 60)
    print('THIN CONTENT FINDER — EVIDENT SCIENTIFIC')
    print('=' * 60)
    print(f'Sitemaps: {len(sitemap_list)}')

    # Step 1 — collect product URLs from sitemaps
    product_urls = collect_product_urls(sitemap_list, timeout=timeout, max_retries=max_retries)

    if not product_urls:
        print('No product URLs found. Exiting.')
        return []

    if limit and limit < len(product_urls):
        print(f'Limiting to first {limit} URLs (--limit flag)')
        product_urls = product_urls[:limit]

    if dry_run:
        print(f'\n[DRY RUN] Would crawl {len(product_urls):,} product URLs. Exiting.')
        return []

    # Step 2 — crawl each product page (Check B)
    page_results = crawl_pages(
        product_urls,
        timeout=timeout,
        min_delay=min_delay,
        max_delay=max_delay,
        max_retries=max_retries,
    )

    # Build page_result lookup by URL
    page_result_map = {pr.url: pr for pr in page_results}

    # Step 3 — apply Check A + Check B, build DetectionResults
    results: List[DetectionResult] = []
    for su in product_urls:
        pr = page_result_map.get(su.url)
        if pr is None:
            from .page_analyzer import PageResult
            pr = PageResult(url=su.url, error='No fetch result', check_b_skipped=True)
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
