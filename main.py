import argparse
import sys
import os
import json
import csv
import logging
from datetime import datetime
from pydantic import ValidationError
from dotenv import load_dotenv

from scraper.browser import BrowserManager
from scraper.auth import AuthManager
from scraper.extractor import ProfileExtractor
from scraper.models import FinalOutput, ProfileMetadata

def setup_logger():
    # Setup basic logging
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    fh = logging.FileHandler('execution.log')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def parse_args():
    parser = argparse.ArgumentParser(description="Automated LinkedIn Profile Scraper")
    
    # Input
    parser.add_argument("--url", type=str, help="Single LinkedIn profile URL to scrape (overrides config)")
    parser.add_argument("--csv", type=str, help="Path to CSV file containing profile URLs (overrides config)")
    
    # Credentials
    parser.add_argument("--username", type=str, help="LinkedIn email/username (overrides config)")
    parser.add_argument("--password", type=str, help="LinkedIn password (overrides config)")
    
    # Configuration
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--mode", type=str, choices=["stealth", "fast"], help="Scraping mode (stealth or fast)")
    parser.add_argument("--proxy", type=str, help="Proxy URL (e.g., http://user:pass@host:port)")
    
    return parser.parse_args()

def export_to_csv(profiles, filename="output_raw.csv"):
    if not profiles:
        return
        
    flat_data = []
    for p in profiles:
        basic = p.get("basic", {})
        contact = p.get("contact_info", {}) or {}
        
        # Safe array joining
        def join_names(items):
            return ", ".join([str(i.get("name", "")) for i in items if isinstance(i, dict)])
            
        flat = {
            "Profile URL": p.get("profile_url", ""),
            "Full Name": basic.get("full_name", ""),
            "Headline": basic.get("headline", ""),
            "Location": basic.get("location", ""),
            "Connection Count": basic.get("connection_count", ""),
            "Follower Count": basic.get("follower_count", ""),
            "About": p.get("about", ""),
            "Email": contact.get("email", ""),
            "Phone": contact.get("phone", ""),
            "Birthday": contact.get("birthday", ""),
            "Connected At": contact.get("connected_at", ""),
            "Websites": ", ".join(contact.get("websites", [])),
            "Social Links": ", ".join(contact.get("social_links", [])),
            "Skills": join_names(p.get("skills", [])),
            "Certifications": join_names(p.get("certifications", [])),
            "Projects": join_names(p.get("projects", []))
        }
        
        # Flatten latest experience
        exp = p.get("experience", [])
        if exp and len(exp) > 0:
            flat["Latest Company"] = exp[0].get("company", "")
            flat["Latest Role"] = exp[0].get("role", "")
            flat["Latest Duration"] = exp[0].get("duration", "")
        else:
            flat["Latest Company"] = ""
            flat["Latest Role"] = ""
            flat["Latest Duration"] = ""
            
        # Flatten latest education
        edu = p.get("education", [])
        if edu and len(edu) > 0:
            flat["Latest Education"] = edu[0].get("institute", "")
            flat["Latest Degree"] = edu[0].get("degree", "")
        else:
            flat["Latest Education"] = ""
            flat["Latest Degree"] = ""
            
        flat_data.append(flat)
        
    keys = flat_data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(flat_data)

def main():
    setup_logger()
    args = parse_args()

    # ==========================================
    # ⚙️ CONFIG BLOCK ⚙️
    # You can change these values directly here!
    # ==========================================
    load_dotenv()
    CONFIG_USERNAME = os.getenv("LINKEDIN_USERNAME")
    CONFIG_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
    
    # Put URLs you want to scrape here, for example:
    # CONFIG_URLS = ["linkedin.com/in/sanskar-malviya", "linkedin.com/in/williamhgates"]
    # CONFIG_URLS = ["linkedin.com/in/sanskar-malviya"] 
    
    # Or read from a CSV by default if CONFIG_URLS is empty
    CONFIG_CSV = "profiles.csv"
    # CONFIG_CSV = None
    
    # Scraping Mode ("fast" for testing, "stealth" for human-like delays)
    CONFIG_MODE = "fast" 
    # ==========================================

    username = args.username if args.username else CONFIG_USERNAME
    password = args.password if args.password else CONFIG_PASSWORD

    urls_to_scrape = []
    
    # Prioritize CLI -> hardcoded CSV -> hardcoded Array
    if args.url:
        urls_to_scrape.append(args.url)
    elif args.csv or CONFIG_CSV:
        csv_file = args.csv if args.csv else CONFIG_CSV
        try:
            with open(csv_file, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        urls_to_scrape.append(row[0])
        except Exception as e:
            logging.error(f"Failed to read CSV: {e}")
            sys.exit(1)
    else:
        urls_to_scrape = CONFIG_URLS

    if not urls_to_scrape:
        logging.error("No URLs provided to scrape! Update CONFIG_URLS or pass --url.")
        sys.exit(1)

    proxy_dict = None
    if args.proxy:
        # Simple proxy parsing logic (not comprehensive)
        try:
            proto_auth, host_port = args.proxy.split('@')
            _, auth = proto_auth.split('://')
            username, password = auth.split(':')
            host, port = host_port.split(':')
            proxy_dict = {"username": username, "password": password, "host": host, "port": port}
        except Exception:
            logging.error("Invalid proxy format. Use http://user:pass@host:port")
            sys.exit(1)

    # Convert mode to a boolean indicating stealth mode
    active_mode = args.mode if args.mode else CONFIG_MODE
    is_stealth = (active_mode == "stealth")
    
    # Initialize Browser
    bm = BrowserManager(headless=args.headless, proxy=proxy_dict, stealth=is_stealth)
    context = bm.start()
    
    creds = {"username": username, "password": password}
    auth_manager = AuthManager(context, creds)
    
    try:
        # Authenticate
        logging.info("Starting authentication flow...")
        page = auth_manager.login()
        logging.info("Authentication complete. Ready to scrape.")

        # Initialize Extractor
        extractor = ProfileExtractor(page)

        # Storage
        scraped_profiles = []
        failed_profiles = []

        total_profiles = len(urls_to_scrape)
        
        # Scrape profiles
        for i, url in enumerate(urls_to_scrape):
            logging.info(f"[{i+1}/{total_profiles}] Scraping profile: {url}")
            try:
                # Assuming extractor will return a dict that matches ProfileData model
                profile_dict = extractor.extract_profile(url)
                scraped_profiles.append(profile_dict)
                logging.info(f"Successfully scraped: {url}")
                
            except Exception as e:
                logging.error(f"Failed to scrape {url}: {str(e)}")
                failed_profiles.append({"url": url, "error": str(e)})

        # Save Output
        timestamp = datetime.now().isoformat()
        metadata = ProfileMetadata(
            scraped_at=timestamp,
            total_profiles=len(scraped_profiles),
            status="completed"
        )
        
        try:
            output_model = FinalOutput(metadata=metadata, profiles=scraped_profiles)
            
            # Save RAW (the model dumps to standard JSON)
            with open('output_raw.json', 'w', encoding='utf-8') as f:
                json.dump(output_model.model_dump(), f, indent=2, ensure_ascii=False)
                
            logging.info("Data successfully saved to output_raw.json")
            
            # Save flattened CSV version
            try:
                export_to_csv(output_model.model_dump()["profiles"], "output_raw.csv")
                logging.info("Data successfully exported to output_raw.csv")
            except Exception as e:
                logging.error(f"Failed to generate CSV: {e}")
            
        except ValidationError as ve:
            logging.error(f"Output validation failed: {ve}")
            
    except Exception as e:
        logging.error(f"Critical error during execution: {e}")
        
    finally:
        bm.close()

if __name__ == "__main__":
    main()
