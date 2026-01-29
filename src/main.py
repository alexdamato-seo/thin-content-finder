#!/usr/bin/env python3
"""
Sitemap Thin Page Analyzer

A tool that analyzes sitemaps to identify "thin" product pages
that lack substantial content.

Usage:
    python -m src.main [options]
    python src/main.py [options]
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

from .sitemap_parser import SitemapParser, SitemapURL
from .page_analyzer import PageAnalyzer, PageMetrics
from .thin_detector import ThinPageDetector, DetectionThresholds, DetectionResult
from .report_generator import ReportGenerator, print_summary

# Default configuration
DEFAULT_CONFIG = {
    "sitemaps": [
        "https://evidentscientific.com/sitemap-en.xml",
        "https://evidentscientific.com/sitemap-es.xml",
        "https://evidentscientific.com/sitemap-fr.xml",
        "https://evidentscientific.com/sitemap-de.xml",
        "https://evidentscientific.com/sitemap-it.xml",
        "https://evidentscientific.com/sitemap-ko.xml",
        "https://evidentscientific.com/sitemap-ja.xml",
        "https://evidentscientific.com/sitemap-zh.xml"
    ],
    "detection_thresholds": {
        "min_word_count": 100,
        "require_description": True,
        "require_specifications": True
    },
    "performance": {
        "delay_between_requests": 1.5,
        "max_retries": 3,
        "timeout_seconds": 30,
        "parallel_workers": 1
    },
    "output": {
        "directory": "./output",
        "format": ["csv", "xlsx"]
    }
}


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create logs directory
    logs_dir = Path('./logs')
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Log file with timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    log_file = logs_dir / f"analysis_{timestamp}.log"

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Reduce noise from libraries
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from file or use defaults."""
    config = DEFAULT_CONFIG.copy()

    if config_path:
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # Deep merge user config into default
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in config:
                        config[key].update(value)
                    else:
                        config[key] = value
            logging.info(f"Loaded configuration from {config_path}")
        except FileNotFoundError:
            logging.warning(f"Config file not found: {config_path}, using defaults")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in config file: {e}")
            sys.exit(1)

    return config


def collect_product_urls(
    sitemap_parser: SitemapParser,
    sitemap_urls: List[str]
) -> List[SitemapURL]:
    """Collect all product URLs from sitemaps."""
    all_urls = []

    print("\nFetching sitemaps...")
    for sitemap_url in tqdm(sitemap_urls, desc="Parsing sitemaps"):
        product_urls = sitemap_parser.process_sitemap(sitemap_url)
        all_urls.extend(product_urls)
        logging.info(f"Found {len(product_urls)} product URLs in {sitemap_url}")

    print(f"\nTotal product URLs found: {len(all_urls):,}")
    return all_urls


def analyze_pages(
    urls: List[SitemapURL],
    config: dict
) -> List[tuple[SitemapURL, PageMetrics]]:
    """Analyze all product pages."""
    results = []

    perf_config = config.get('performance', {})
    timeout = perf_config.get('timeout_seconds', 30)
    delay = perf_config.get('delay_between_requests', 1.5)
    max_retries = perf_config.get('max_retries', 3)

    analyzer = PageAnalyzer(
        timeout=timeout,
        delay_between_requests=delay,
        headless=True
    )

    print(f"\nAnalyzing {len(urls):,} pages (this may take a while)...")

    try:
        with tqdm(total=len(urls), desc="Analyzing pages", unit="page") as pbar:
            for sitemap_url in urls:
                metrics = None
                last_error = None

                # Retry logic
                for attempt in range(max_retries):
                    metrics = analyzer.analyze_page(sitemap_url.url)

                    if metrics.error is None:
                        break

                    last_error = metrics.error
                    if attempt < max_retries - 1:
                        time.sleep(2 ** (attempt + 1))

                if metrics is None:
                    metrics = PageMetrics(
                        url=sitemap_url.url,
                        error=f"Failed after {max_retries} attempts: {last_error}"
                    )

                results.append((sitemap_url, metrics))
                pbar.update(1)

    finally:
        analyzer.close()

    return results


def detect_thin_pages(
    analysis_results: List[tuple[SitemapURL, PageMetrics]],
    config: dict
) -> List[DetectionResult]:
    """Apply thin page detection to analyzed pages."""
    threshold_config = config.get('detection_thresholds', {})
    thresholds = DetectionThresholds(
        min_word_count=threshold_config.get('min_word_count', 100),
        require_description=threshold_config.get('require_description', True),
        require_specifications=threshold_config.get('require_specifications', True)
    )

    detector = ThinPageDetector(thresholds=thresholds)
    results = []

    print("\nDetecting thin pages...")
    for sitemap_url, metrics in tqdm(analysis_results, desc="Detecting"):
        result = detector.detect(
            metrics=metrics,
            language=sitemap_url.language,
            sku=sitemap_url.sku
        )
        results.append(result)

    return results


def generate_reports(
    results: List[DetectionResult],
    config: dict
) -> dict:
    """Generate output reports."""
    output_config = config.get('output', {})
    output_dir = output_config.get('directory', './output')
    formats = output_config.get('format', ['csv', 'xlsx'])

    generator = ReportGenerator(output_dir=output_dir)

    print("\nGenerating reports...")
    report_files = {}

    if 'csv' in formats:
        report_files['csv'] = generator.generate_csv(results)
        print(f"  CSV report: {report_files['csv']}")

    if 'xlsx' in formats:
        report_files['excel'] = generator.generate_excel(results)
        print(f"  Excel report: {report_files['excel']}")

    # Always generate error log
    error_results = [r for r in results if r.error]
    if error_results:
        report_files['error_log'] = generator.generate_error_log(results)
        print(f"  Error log: {report_files['error_log']}")

    return report_files


def run_analysis(
    config: dict,
    sitemaps: Optional[List[str]] = None,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> List[DetectionResult]:
    """Run the complete analysis workflow."""
    logger = logging.getLogger(__name__)
    start_time = time.time()

    # Use provided sitemaps or config default
    sitemap_urls = sitemaps or config.get('sitemaps', DEFAULT_CONFIG['sitemaps'])

    print("\n" + "=" * 60)
    print("SITEMAP THIN PAGE ANALYZER")
    print("=" * 60)
    print(f"Sitemaps to process: {len(sitemap_urls)}")

    # Step 1: Collect URLs from sitemaps
    perf_config = config.get('performance', {})
    sitemap_parser = SitemapParser(
        timeout=perf_config.get('timeout_seconds', 30),
        max_retries=perf_config.get('max_retries', 3)
    )

    all_urls = collect_product_urls(sitemap_parser, sitemap_urls)

    if not all_urls:
        print("No product URLs found in sitemaps. Exiting.")
        return []

    # Apply limit if specified
    if limit and limit < len(all_urls):
        print(f"Limiting analysis to first {limit} URLs")
        all_urls = all_urls[:limit]

    # Dry run - just report what would be analyzed
    if dry_run:
        print("\n[DRY RUN] Would analyze the following:")
        print(f"  - Total URLs: {len(all_urls):,}")
        for sitemap_url in sitemap_urls:
            count = sum(1 for u in all_urls if sitemap_url.replace('.xml', '') in u.url)
            print(f"  - {sitemap_url}: ~{count} URLs")
        return []

    # Step 2: Analyze pages
    analysis_results = analyze_pages(all_urls, config)

    # Step 3: Detect thin pages
    detection_results = detect_thin_pages(analysis_results, config)

    # Step 4: Generate reports
    report_files = generate_reports(detection_results, config)

    # Print summary
    print_summary(detection_results)

    elapsed_time = time.time() - start_time
    hours, remainder = divmod(int(elapsed_time), 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"Processing time: {hours}h {minutes}m {seconds}s")
    print(f"Output: {report_files.get('excel', report_files.get('csv', 'N/A'))}")

    return detection_results


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Analyze sitemaps to identify thin product pages',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                    # Run with default config
  python -m src.main --config custom.json  # Use custom config file
  python -m src.main --limit 100        # Analyze only first 100 URLs
  python -m src.main --dry-run          # Preview without analyzing
  python -m src.main --sitemaps sitemap-en.xml sitemap-es.xml
        """
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        help='Path to configuration JSON file'
    )

    parser.add_argument(
        '--sitemaps', '-s',
        nargs='+',
        type=str,
        help='Specific sitemap URLs to analyze (overrides config)'
    )

    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Preview what would be analyzed without actually running'
    )

    parser.add_argument(
        '--limit', '-l',
        type=int,
        help='Limit number of URLs to analyze (useful for testing)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        help='Output directory for reports (overrides config)'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    # Load configuration
    config = load_config(args.config)

    # Override config with command line arguments
    if args.output_dir:
        config['output']['directory'] = args.output_dir

    try:
        # Run analysis
        results = run_analysis(
            config=config,
            sitemaps=args.sitemaps,
            dry_run=args.dry_run,
            limit=args.limit
        )

        if results:
            thin_count = sum(1 for r in results if r.is_thin)
            print(f"\nAnalysis complete! Found {thin_count:,} thin pages.")
            sys.exit(0)
        elif args.dry_run:
            print("\nDry run complete.")
            sys.exit(0)
        else:
            print("\nNo results generated.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nAnalysis interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logging.exception(f"Analysis failed: {e}")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
