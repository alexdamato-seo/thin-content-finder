"""
Report Generator — writes CSV output files and prints the summary.

Produces two files:
  thin_content_report.csv  — flagged pages only (flagged = TRUE)
  all_pages_report.csv     — every product page processed
"""

import csv
import logging
from pathlib import Path
from typing import List

from .thin_detector import DetectionResult

logger = logging.getLogger(__name__)

COLUMNS = [
    'url',
    'locale',
    'flagged',
    'check_a_sku_url',
    'check_b_sku_title_h1',
    'page_title',
    'h1',
    'flag_reasons',
    'http_status',
    'check_b_skipped',
]


def _to_row(r: DetectionResult) -> dict:
    return {
        'url': r.url,
        'locale': r.locale,
        'flagged': 'TRUE' if r.flagged else 'FALSE',
        'check_a_sku_url': 'TRUE' if r.check_a_sku_url else 'FALSE',
        'check_b_sku_title_h1': 'TRUE' if r.check_b_sku_title_h1 else 'FALSE',
        'page_title': r.page_title,
        'h1': r.h1,
        'flag_reasons': r.flag_reasons,
        'http_status': r.http_status if r.http_status is not None else 'N/A',
        'check_b_skipped': 'TRUE' if r.check_b_skipped else 'FALSE',
    }


def _write_csv(results: List[DetectionResult], filepath: Path) -> None:
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for r in results:
            writer.writerow(_to_row(r))
    logger.info(f"Wrote {len(results)} rows → {filepath}")


def generate_reports(
    results: List[DetectionResult],
    output_dir: str = './output',
) -> tuple[str, str]:
    """
    Write thin_content_report.csv and all_pages_report.csv to output_dir.

    Returns (thin_report_path, all_pages_report_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    thin_path = out / 'thin_content_report.csv'
    all_path = out / 'all_pages_report.csv'

    _write_csv([r for r in results if r.flagged], thin_path)
    _write_csv(results, all_path)

    return str(thin_path), str(all_path)


def print_summary(
    results: List[DetectionResult],
    total_product_urls: int = 0,
) -> None:
    """Print the audit summary in the format specified by the task."""
    total = total_product_urls or len(results)
    crawled = sum(1 for r in results if not r.check_b_skipped)

    flagged = [r for r in results if r.flagged]
    a_only = sum(1 for r in flagged if r.check_a_sku_url and not r.check_b_sku_title_h1)
    b_only = sum(1 for r in flagged if r.check_b_sku_title_h1 and not r.check_a_sku_url)
    both   = sum(1 for r in flagged if r.check_a_sku_url and r.check_b_sku_title_h1)

    locale_stats: dict = {}
    for r in results:
        entry = locale_stats.setdefault(r.locale, {'total': 0, 'thin': 0})
        entry['total'] += 1
        if r.flagged:
            entry['thin'] += 1

    print('\n=== Thin Content Audit Complete ===')
    print(f'Total product URLs found:     {total}')
    print(f'Total pages crawled:          {crawled}')
    print(f'Total thin pages flagged:     {len(flagged)}')
    print(f'Flagged by URL pattern only:  {a_only}')
    print(f'Flagged by title/H1 only:     {b_only}')
    print(f'Flagged by both:              {both}')
    print('Breakdown by locale:')
    for locale in ['en', 'es', 'fr', 'de', 'it', 'ko', 'ja', 'zh']:
        stats = locale_stats.get(locale, {'thin': 0, 'total': 0})
        print(f'  {locale}: {stats["thin"]} thin / {stats["total"]} total')
    print('Output files:')
    print('  thin_content_report.csv   — flagged pages only')
    print('  all_pages_report.csv      — all product pages')
