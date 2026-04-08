# LinkedIn Profile & Company Data Extractor

A robust, fully automated Python-based LinkedIn scraper built with [Playwright](https://playwright.dev/python/). It logs into LinkedIn, handles 2FA, lazy-loaded content, and extracts extensive profile and company details into structured JSON and CSV formats.

## Features

### Profile Scraping
- **Human-like Authentication**: Simulates typing delays, logs in natively via Playwright, and caches sessions locally (`session.json`) to prevent repetitive 2FA challenges.
- **Smart Scrolling**: Scrolls LinkedIn's virtualized DOM container (`<main>`) incrementally to trigger lazy-loaded sections, extracting data as each section enters the viewport.
- **Comprehensive Data Extraction**:
  - **Basic Info**: Name, Headline, Location, Connections, Followers.
  - **About**: Full summary text.
  - **Experience**: Work history with company names (grouped role support), duration, and descriptions.
  - **Education**: Schools, degrees, fields of study, and years.
  - **Skills & Certifications**: Validated skills and certification details.
  - **Projects**: Descriptions and timelines.
  - **Contact Info**: Opens the Contact Info overlay to extract Email, Phone, Birthday, Connected date, Websites, and Social links.
  - **Company Links**: Extracts LinkedIn company URLs from the experience section.

### Company Scraping
- **Auto-Detection**: Pass a `/company/` URL and the scraper automatically switches to company extraction mode.
- **About Page**: Name, tagline, industry, size, headquarters, founded year, type, specialties, website, **phone**, **email**, full **address**, verified status, follower count, and associated member count.
- **Jobs Page**: Detailed job listings with title, location, and posted date — with pagination across all pages.
- **People Page**: Employee directory with names, titles, and profile URLs — clicks "Show more results" and paginates through all pages to capture maximum employees.

### General
- **Session Caching**: Saves login cookies to `session.json`. After the first login, subsequent runs bypass the login screen entirely.
- **Dual Outputs (.json & .csv)**: Pydantic-validated JSON and flattened CSV for spreadsheet imports.
- **Dual Execution Modes**: Edit config directly in `main.py` or pass CLI arguments.

## Prerequisites
- Python 3.9+
- Chrome or Chromium browser installed via Playwright

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/sanskar-malviya/LinkedIn-Profile-Data-Extractor.git
   cd LinkedIn-Profile-Data-Extractor
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
4. Set up credentials:
   ```bash
   cp .env.example .env
   # Open .env and add your LINKEDIN_USERNAME and LINKEDIN_PASSWORD
   ```

## Usage

### Method 1: Edit `main.py` Config Block
```python
# ⚙️ CONFIG BLOCK ⚙️
CONFIG_URLS = []
CONFIG_CSV = "profiles.csv"
CONFIG_MODE = "fast"
```
Then run:
```bash
python main.py
```

### Method 2: CLI Arguments

**Single Profile:**
```bash
python main.py --url linkedin.com/in/sanskar-malviya
```

**Single Company:**
```bash
python main.py --url "https://www.linkedin.com/company/anaxee-digital-runners-private-limited"
```

**Multiple URLs via CSV** (mix of profiles and companies):
```bash
python main.py --csv profiles.csv
```

**Headless Mode:**
```bash
python main.py --csv profiles.csv --headless
```

The scraper auto-detects whether each URL is a person (`/in/`) or company (`/company/`) and extracts accordingly.

### CLI Options
| Flag | Description |
|------|-------------|
| `--url` | Single LinkedIn URL to scrape |
| `--csv` | CSV file with URLs (one per line) |
| `--username` | LinkedIn email (overrides `.env`) |
| `--password` | LinkedIn password (overrides `.env`) |
| `--headless` | Run browser without UI |
| `--mode` | `fast` or `stealth` (human-like delays) |
| `--proxy` | Proxy URL (`http://user:pass@host:port`) |

## Output

### Files
- **`output_raw.json`** — Structured, Pydantic-validated JSON.
- **`output_raw.csv`** — Flattened CSV for Excel/Airtable.

### Profile JSON Schema
```json
{
  "profile_url": "https://linkedin.com/in/sanskar-malviya",
  "basic": {
    "full_name": "Sanskar Malviya",
    "headline": "Data Analyst | AI Engineer | ...",
    "location": "Indore, Madhya Pradesh, India",
    "connection_count": 500,
    "follower_count": 1142
  },
  "about": "I am a Computer Science Engineer...",
  "experience": [
    {
      "company": "Anaxee Digital Runners Private Limited",
      "role": "Data Analyst",
      "duration": "Jul 2024 - Present · 1 yr 10 mos"
    }
  ],
  "education": [...],
  "skills": [{"name": "Python"}, ...],
  "contact_info": {
    "email": "example@gmail.com",
    "phone": null,
    "websites": ["https://portfolio.com"],
    "birthday": "May 17",
    "connected_at": "Oct 27, 2025"
  },
  "company_links": ["https://www.linkedin.com/company/anaxee-digital-runners-private-limited"]
}
```

### Company JSON Schema
```json
{
  "company_url": "https://www.linkedin.com/company/anaxee-digital-runners-private-limited",
  "name": "Anaxee Digital Runners Private Limited",
  "tagline": "India's Reach Engine!",
  "industry": "Environmental Services",
  "company_size": "51-200 employees",
  "headquarters": "Indore, Madhya Pradesh",
  "founded": "2016",
  "website": "https://www.anaxee.com/",
  "phone": "9584132577",
  "email": "sales@anaxee.com",
  "address": "303, Right-wing, New IT Park Building 3rd floor, ..., Indore, MP 452003",
  "follower_count": 11000,
  "employee_count_on_linkedin": "247 associated members",
  "verified": "March 22, 2025",
  "jobs": [
    {"title": "Management Trainee || April 2026", "location": "Indore", "posted": "2 weeks ago"}
  ],
  "employees": [
    {"name": "Devesh Chouksey", "title": "Business Development Executive @Anaxee", "profile_url": "https://..."}
  ]
}
```

## Project Structure
```
LinkedIn-Profile-Data-Extractor/
├── main.py                     # Entry point, CLI, orchestration
├── scraper/
│   ├── extractor.py            # Profile extraction (live DOM + scrolling)
│   ├── company_extractor.py    # Company extraction (about/jobs/people)
│   ├── auth.py                 # Login, session management, 2FA handling
│   ├── browser.py              # Playwright browser setup
│   ├── models.py               # Pydantic data models
│   └── utils.py                # Delays, scrolling helpers
├── profiles.csv                # Input URLs
├── output_raw.json             # Generated JSON output
├── output_raw.csv              # Generated CSV output
├── session.json                # Cached login session
├── .env                        # Credentials (not committed)
└── requirements.txt            # Python dependencies
```

## Troubleshooting
- **2FA / Checkpoints**: On your first run, if LinkedIn asks for a verification code, the Playwright window will pause for you to enter it manually. The session is saved to `session.json` — you won't need 2FA again until the session expires.
- **Empty Fields**: LinkedIn frequently changes their DOM structure. If fields return `null`, the CSS selectors in `extractor.py` may need updating.
- **247 members but only 181 extracted**: LinkedIn limits employee visibility based on your connection degree. 3rd+ degree profiles may not be shown.
- **Logs**: Detailed execution logs are written to `execution.log`.

## Disclaimer
Scraping LinkedIn directly may violate their terms of service. This tool is for educational purposes. Handle credentials carefully and respect rate limits to avoid account suspension.
