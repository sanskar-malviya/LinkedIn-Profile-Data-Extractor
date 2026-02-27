# LinkedIn Profile Data Extractor

A robust, fully automated Python-based LinkedIn profile scraper built with [Playwright](https://playwright.dev/python/) and `BeautifulSoup4`. It seamlessly logs into LinkedIn, supports 2FA challenges dynamically, handles lazy-loaded content, and extracts extensive profile details into structured JSON format. 

## Features
- **Human-like Authentication**: Simulates typing delays, logs in natively via Playwright, and saves sessions locally (`session.json`) to prevent repetitive challenges/bans.
- **Dynamic Content Loading**: Intercepts background GraphQL requests and scrolls precisely to trigger lazy-loaded sections.
- **Comprehensive Data Extraction**: 
  - **Basic Info**: Name, Location, Headline, Connections.
  - **About**: Full summary text.
  - **Experience**: Complete work history including descriptions, tenure, and location.
  - **Education**: Schools, degrees, fields of study, and years.
  - **Skills & Certifications**: Extracts validated skills and certification references.
  - **Projects**: Extracts descriptions and timelines for linked projects.
  - **Contact Info**: Clicks the 'Contact Info' overlay dynamically to snag Emails, Phone numbers, Birthdays, Connected dates, Websites, and Social Hubs (e.g. GitHub/Twitter links).
- **Session Caching**: The script saves login cookies to a local `session.json` file. This means **you only log in once**. After the first run, the scraper bypasses the login screen entirely resulting in lightning-fast, stealthy execution without triggering 2FA or CAPTCHAs.
- **Dual Outputs (.json & .csv)**: The scraper simultaneously exports raw nested profile data into a rigorous Pydantic-validated JSON file, and a flattened CSV table perfect for Excel or Airtable imports.
- **Dual Execution Modes**: 
  - Edit hardcoded configuration directly within `main.py` OR pass Command Line Arguments (CLI).

## Prerequisites
- Python 3.9+
- Chrome or Chromium browser installed via Playwright

## Installation
1. Clone the repository / Open the project directory.
2. Create and activate a Virtual Environment.
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```
3. Install the required Python packages (assuming standard structure).
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
4. Copy the environment variables example and add your credentials:
   ```bash
   cp .env.example .env
   # Open .env and add your LINKEDIN_USERNAME and LINKEDIN_PASSWORD
   ```

## Configuration & Usage
This script was designed to be easily plug-and-play. You can configure it by editing the `CONFIG BLOCK` at the top of `main.py` or by passing command-line arguments.

### Method 1: Editing `main.py` (Recommended for ease of use)
Ensure your `.env` file has your credentials loaded.
Then, open `main.py` and modify lines ~50-65 to match what you want to scrape:
```python
# ==========================================
# ⚙️ CONFIG BLOCK ⚙️
# You can change these values directly here!
# ==========================================

# Specify a list of URLs directly:
# CONFIG_URLS = ["linkedin.com/in/sanskar-malviya", "linkedin.com/in/williamhgates"]
CONFIG_URLS = [] 

# Or specify a CSV file containing a list of URLs (one per line):
CONFIG_CSV = "profiles.csv"

# Scraping Mode ("fast" for testing, "stealth" for human-like delays)
CONFIG_MODE = "fast" 
```
Once your config block is set up, simply run:
```bash
python main.py
```

### Method 2: Command Line Interface (CLI)
CLI arguments will **override** whatever is saved in the `main.py` Config Block. This is useful for automated chron jobs or quick single tests.

**Single Profile:**
```bash
python main.py --username your_email@domain.com --password YourPassword --url linkedin.com/in/sanskar-malviya
```

**Multiple Profiles via CSV:**
```bash
python main.py --username your_email@domain.com --password YourPassword --csv profiles.csv
```

**Run in the background (Headless Mode):**
```bash
python main.py --username your_email@domain.com --password YourPassword --csv profiles.csv --headless
```

## Output Formats
The scraper exports the extracted data in two formats upon successful completion:

1. **`output_raw.json`**: A highly structured, rigorous array enforcing Pydantic schema validation. Perfect for databases or API bridging.
2. **`output_raw.csv`**: A flattened, spreadsheet-ready CSV table. It intelligently maps nested arrays (like the top skills, projects, and the most recent job/education) into single columns for easy review.

Example JSON Output Schema:
```json
{
  "metadata": {
    "scraped_at": "2026-02-27T15:00:00",
    "total_profiles": 1,
    "status": "completed"
  },
  "profiles": [
    {
      "profile_url": "https://linkedin.com/in/sanskar-malviya",
      "basic": {
        "full_name": "Sanskar Malviya",
        "headline": "...",
        "location": "..."
      },
      "experience": [ ... ],
      "education": [ ... ],
      "skills": [ {"name": "Python"}, ... ],
      "contact_info": {
        "email": "example@gmail.com",
        "websites": ["https://portfolio.com"]
      }
    }
  ]
}
```

## Troubleshooting
- **2FA or Checkpoints**: On your **very first run**, if LinkedIn asks for a verification code, the Playwright window will pause and safely wait for you to type the code in manually. Once completed, the session is saved entirely to `session.json`. You will not have to type a 2FA code again unless your session naturally expires months later.
- **Empty Fields**: If the DOM parser suddenly starts returning `null` for specific fields, LinkedIn may have updated their CSS structure. You can easily update the BeautifulSoup targeted classes inside `scraper/extractor.py`.
- **Logs**: Detailed execution logs are appended to `execution.log` for debugging and history tracking.

## Disclaimer
Scraping LinkedIn's platform directly violates their generic terms of service. This code was created for educational purposes or for use strictly where compliant with local automated scraping laws. Be cautious handling login credentials and respect rate limits to prevent account suspension.
