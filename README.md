# Sitemap Thin Page Analyzer

A CLI tool that analyzes sitemaps from evidentscientific.com to identify "thin" product pages that lack substantial content. The tool crawls each URL, evaluates page quality based on objective content depth metrics, and outputs CSV/Excel reports listing pages that should be reviewed for removal from the commerce system.

## Features

- Parses 8 language-specific XML sitemaps
- Handles JavaScript-rendered content using Selenium headless browser
- Applies objective thin page detection criteria
- Generates CSV and Excel reports with detailed metrics
- Progress tracking with estimated completion time
- Graceful error handling with retry logic
- Configurable detection thresholds

## Requirements

- Python 3.9+
- Google Chrome or Chromium browser
- ChromeDriver (matching your Chrome version)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd thin-content-finder
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Ensure ChromeDriver is installed and in your PATH:
```bash
# On macOS with Homebrew:
brew install chromedriver

# On Ubuntu/Debian:
sudo apt-get install chromium-chromedriver

# Or download from: https://chromedriver.chromium.org/downloads
```

## Usage

### Basic Usage

Run analysis with default configuration:
```bash
python -m src.main
```

### Command Line Options

```bash
python -m src.main [OPTIONS]

Options:
  -c, --config PATH     Path to custom configuration JSON file
  -s, --sitemaps URLs   Specific sitemap URLs to analyze (space-separated)
  -l, --limit N         Limit analysis to first N URLs (useful for testing)
  -n, --dry-run         Preview what would be analyzed without running
  -o, --output-dir DIR  Output directory for reports
  -v, --verbose         Enable verbose logging
  -h, --help            Show help message
```

### Examples

```bash
# Run with custom config file
python -m src.main --config config/custom.json

# Analyze only English and Spanish sitemaps
python -m src.main --sitemaps https://evidentscientific.com/sitemap-en.xml https://evidentscientific.com/sitemap-es.xml

# Test with a small sample
python -m src.main --limit 50 --verbose

# Preview without analyzing
python -m src.main --dry-run

# Specify output directory
python -m src.main --output-dir ./reports
```

## Configuration

Configuration can be provided via a JSON file. See `config/sitemaps.json` for the default configuration:

```json
{
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
    "require_description": true,
    "require_specifications": true
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
```

## Thin Page Detection Criteria

A page is flagged as **THIN** if it meets the following criteria:

1. **Non-descriptive title**: Title contains only SKU/product code without descriptive text
2. **Low word count**: Less than 100 words of product-related content
3. **Missing description**: No product description paragraph or section
4. **Missing specifications**: No technical specifications table or details

### Special Considerations

- Pages with technical specifications in the title (e.g., "20X Objective NA 0.4 FN 22.0 WD 1.3 mm") are NOT considered thin, even if word count is low
- Detection focuses on content quality, not just quantity

### Reference Examples

**THIN PAGE**: `https://evidentscientific.com/en/products/n2750300/n2750300`
- Title is just the SKU
- No meaningful product description
- Minimal specifications

**NOT THIN PAGE**: `https://evidentscientific.com/en/products/n2181200/n2181200`
- Title includes technical specs: "20X Objective NA 0.4 FN 22.0 WD 1.3 mm"
- Contains meaningful product information

## Output Files

Reports are generated in the `output/` directory:

### Main Report (CSV/Excel)

| Column | Description |
|--------|-------------|
| URL | Full product page URL |
| Language | Language code (en, es, fr, de, it, ko, ja, zh) |
| SKU | Product SKU extracted from URL |
| Page Title | Actual page title |
| Word Count | Visible text word count (content only) |
| Has Description | Yes/No |
| Has Specifications | Yes/No |
| Image Count | Number of product images |
| Thin Page Flag | THIN, OK, or ERROR |
| Reason | Why flagged as thin (if applicable) |
| Timestamp | When analysis was performed |

### Excel Report Features

- **Thin Pages Report**: All analyzed pages
- **Summary**: Statistics and breakdown by language/reason
- **Thin Pages Only**: Filtered list of thin pages
- **Errors**: Pages that failed to analyze

### Error Log

Errors are logged to `logs/errors_YYYY-MM-DD_HHMMSS.log` for manual review.

## Project Structure

```
thin-content-finder/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── sitemap_parser.py       # Sitemap fetching and parsing
│   ├── page_analyzer.py        # Headless browser content analysis
│   ├── thin_detector.py        # Detection logic
│   └── report_generator.py     # CSV/Excel report generation
├── config/
│   └── sitemaps.json           # Default configuration
├── output/                     # Generated reports
├── logs/                       # Execution and error logs
├── requirements.txt
├── README.md
└── .env.example
```

## Performance Notes

- **Processing time**: Expect ~30-60 seconds per page due to JavaScript rendering
- **Memory usage**: Headless Chrome uses ~100-200MB per instance
- **Rate limiting**: Default 1.5 second delay between requests to avoid server overload
- **Resumability**: For large analyses, use `--limit` to process in batches

## Troubleshooting

### ChromeDriver Issues

If you see ChromeDriver errors:
1. Ensure Chrome/Chromium is installed
2. Ensure ChromeDriver version matches your Chrome version
3. Add ChromeDriver to your PATH

### Memory Issues

For large sitemaps:
- Increase system swap space
- Use `--limit` to process in smaller batches
- Close other applications during analysis

### Timeout Errors

If pages timeout frequently:
- Increase `timeout_seconds` in config
- Check your internet connection
- The site may be rate limiting - increase `delay_between_requests`

## License

Internal tool for SEO analysis.
