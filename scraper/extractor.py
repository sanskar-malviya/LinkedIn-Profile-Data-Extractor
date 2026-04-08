import urllib.parse
from bs4 import BeautifulSoup
import json
import logging
import re
import random
from playwright.sync_api import Page
from scraper.utils import random_delay, scroll_to_element
from scraper.models import BasicProfile, Experience, Education, Skill, Certification, Project, ProfileData

logger = logging.getLogger(__name__)


def _scroll_main(page: Page, delta: int):
    """Scroll the main container by delta pixels."""
    page.evaluate(f"""(() => {{
        const el = document.querySelector('main') || document.documentElement;
        el.scrollBy(0, {delta});
    }})()""")


def _scroll_main_to(page: Page, position: int):
    """Scroll the main container to an absolute position."""
    page.evaluate(f"""(() => {{
        const el = document.querySelector('main') || document.documentElement;
        el.scrollTo(0, {position});
    }})()""")


def _get_scroll_info(page: Page) -> tuple:
    """Returns (scrollTop, scrollHeight, clientHeight) of the main container."""
    return page.evaluate("""(() => {
        const el = document.querySelector('main') || document.documentElement;
        return [el.scrollTop, el.scrollHeight, el.clientHeight];
    })()""")


class ProfileExtractor:
    def __init__(self, page: Page):
        self.page = page

    def extract_profile(self, url: str) -> dict:
        """Navigates to the profile and extracts data."""
        logger.info(f"Navigating to {url}")

        # Ensure URL has proper scheme
        if not url.startswith("http"):
            if "linkedin.com/in/" not in url:
                if "linkedin.com" not in url:
                    url = f"https://www.linkedin.com/in/{url.strip('/')}"
                else:
                    url = f"https://{url}"
            else:
                url = f"https://{url}"

        self.page.goto(url, wait_until="domcontentloaded")
        random_delay(3, 5)

        try:
            self.page.wait_for_selector('main', timeout=10000)
        except Exception:
            pass

        if "404" in self.page.title() or "authwall" in self.page.url:
            raise Exception("Profile not found or blocked by authwall.")

        # 1. Extract top card (always visible at load)
        basic = self._extract_basic_live(url)
        about = self._extract_about_live()

        # 2. Scroll to bottom to let LinkedIn discover all sections
        logger.info("Scrolling to load all sections...")
        self._scroll_full_page()

        # 3. Now scroll back to each section individually and extract
        logger.info("Extracting sections...")
        extracted = self._extract_all_sections()

        experience = [Experience(**e) for e in extracted.get("experience", [])]
        education = [Education(**e) for e in extracted.get("education", [])]
        skills = [Skill(name=s) for s in extracted.get("skills", [])]
        certifications = [Certification(**c) for c in extracted.get("certifications", [])]
        projects = [Project(**p) for p in extracted.get("projects", [])]

        profile_data = ProfileData(
            profile_url=url,
            basic=basic,
            about=about,
            experience=experience,
            education=education,
            skills=skills,
            certifications=certifications,
            projects=projects,
            contact_info=None
        )

        # 4. Extract company links from the experience section
        profile_data.company_links = self._extract_company_links()

        # 5. Extract contact info via overlay
        profile_data.contact_info = self._extract_contacts(url)

        return profile_data.model_dump()

    def _scroll_full_page(self):
        """Scroll the main container from top to bottom slowly."""
        _scroll_main_to(self.page, 0)
        random_delay(1, 2)

        last_height = _get_scroll_info(self.page)[1]
        stale = 0

        for i in range(50):
            _scroll_main(self.page, random.randint(300, 500))
            random_delay(1.2, 2.0)

            top, height, client = _get_scroll_info(self.page)
            at_bottom = (top + client) >= height - 100

            if height == last_height and at_bottom:
                stale += 1
                if stale >= 4:
                    break
            else:
                stale = 0
            last_height = height

        logger.info(f"Scroll complete. Page height: {last_height}")

    def _extract_all_sections(self) -> dict:
        """Scroll to each target section and extract its data."""
        extracted = {}

        # Define sections to look for and the scroll position to try
        # We'll scroll from top to bottom, checking for sections at each position
        _scroll_main_to(self.page, 0)
        random_delay(1, 2)

        _, total_height, client_height = _get_scroll_info(self.page)
        position = 0
        seen_sections = set()

        while position < total_height:
            _scroll_main_to(self.page, position)
            random_delay(0.8, 1.2)

            # Check what sections are visible now
            try:
                sections = self.page.locator('[data-testid="lazy-column"] section')
                for i in range(sections.count()):
                    try:
                        section = sections.nth(i)
                        h2 = section.locator('h2')
                        if h2.count() == 0:
                            continue
                        h2_text = h2.first.inner_text(timeout=1000).strip()
                        section_key = self._match_section_name(h2_text)
                        if not section_key or section_key in seen_sections:
                            continue

                        # Found a new target section! Scroll to it and extract.
                        logger.info(f"Found section '{h2_text}'")
                        seen_sections.add(section_key)

                        # Scroll the section into view
                        try:
                            section.scroll_into_view_if_needed(timeout=3000)
                        except Exception:
                            pass
                        random_delay(1.0, 1.5)

                        # Extract data
                        data = self._extract_section_data(section, section_key)
                        if data:
                            extracted[section_key] = data
                            logger.info(f"  Extracted {len(data)} items from '{section_key}'")
                        else:
                            logger.info(f"  No items found in '{section_key}'")

                    except Exception:
                        continue
            except Exception:
                pass

            position += int(client_height * 0.6)

        logger.info(f"Sections extracted: {list(extracted.keys())}")
        return extracted

    def _match_section_name(self, h2_text: str) -> str:
        lower = h2_text.lower()
        if "experience" in lower:
            return "experience"
        if "education" in lower:
            return "education"
        if "skill" in lower:
            return "skills"
        if "certif" in lower or "licens" in lower:
            return "certifications"
        if "project" in lower:
            return "projects"
        if "volunteer" in lower:
            return "volunteering"
        if "honor" in lower or "award" in lower:
            return "honors"
        if "publication" in lower:
            return "publications"
        if "course" in lower:
            return "courses"
        if "language" in lower:
            return "languages"
        return None

    def _extract_section_data(self, section, section_key: str) -> list:
        """Extract structured data from a section that's currently in the viewport."""
        items = []

        # First try <li> elements
        li_els = section.locator('li')
        li_count = li_els.count()

        if li_count > 0:
            # For experience: extract company name from the section text
            # LinkedIn groups multiple roles under one company
            group_company = None
            if section_key == "experience":
                try:
                    sec_text = section.inner_text(timeout=3000)
                    sec_lines = [l.strip() for l in sec_text.split('\n') if l.strip()]
                    emp_types = {'full-time', 'part-time', 'internship', 'contract',
                                 'freelance', 'self-employed'}
                    for line in sec_lines:
                        if self._match_section_name(line):
                            continue
                        if line.lower() in emp_types or self._is_date_line(line):
                            continue
                        if len(line) < 80 and not re.search(r'\d{4}', line):
                            group_company = line
                            logger.info(f"  Experience group company: {group_company}")
                            break
                except Exception:
                    pass

            for i in range(li_count):
                try:
                    text = li_els.nth(i).inner_text(timeout=2000).strip()
                    if not text or len(text) < 3:
                        continue
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if not lines:
                        continue
                    item = self._parse_item(lines, section_key)
                    if item:
                        # Fill in company from group header if the item has no company
                        if section_key == "experience" and isinstance(item, dict):
                            if not item.get("company") and group_company:
                                item["company"] = group_company
                        items.append(item)
                except Exception:
                    continue
            return items

        # No <li> found — parse from section's full text
        try:
            full_text = section.inner_text(timeout=3000).strip()
            if full_text:
                logger.info(f"  No <li> in '{section_key}', parsing from text ({len(full_text)} chars)")
                items = self._parse_section_text(full_text, section_key)
        except Exception as e:
            logger.debug(f"  Error reading section text: {e}")

        return items

    def _parse_item(self, lines: list, section_key: str):
        """Parse a single item from its text lines based on section type."""
        if section_key == "experience":
            return self._parse_experience_item(lines)
        elif section_key == "education":
            return self._parse_education_item(lines)
        elif section_key == "skills":
            # Return first meaningful line, skip button text like "Endorse"
            for line in lines:
                if line.lower() not in ('endorse', 'show all', 'see more') and len(line) > 1:
                    return line
            return None
        elif section_key == "certifications":
            return self._parse_certification_item(lines)
        elif section_key == "projects":
            return self._parse_project_item(lines)
        return None

    def _parse_section_text(self, full_text: str, section_key: str) -> list:
        """Parse section data from raw text when no list items are found.

        LinkedIn renders each field on a separate line. We flatten to lines,
        remove noise, then group into entries using content-based heuristics.
        """
        all_lines = [l.strip() for l in full_text.split('\n') if l.strip()]
        if not all_lines:
            return []

        # Remove header line (section title)
        if all_lines and self._match_section_name(all_lines[0]):
            all_lines = all_lines[1:]

        # Remove noise lines
        noise = {'show all', 'see more', 'endorse', '… more', '· more', 'show credential'}
        all_lines = [l for l in all_lines if l.lower().rstrip('.') not in noise
                     and not l.lower().startswith('show all')]

        if section_key == "skills":
            seen = set()
            items = []
            for line in all_lines:
                if line not in seen and len(line) > 1:
                    seen.add(line)
                    items.append(line)
            return items

        if section_key == "education":
            return self._parse_education_from_lines(all_lines)

        if section_key == "certifications":
            return self._parse_certifications_from_lines(all_lines)

        if section_key == "projects":
            return self._parse_projects_from_lines(all_lines)

        # Generic: just return non-empty lines
        return all_lines

    def _is_date_line(self, line: str) -> bool:
        """Check if a line looks like a date range."""
        return bool(re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}|^\d{4}\s*[-–]', line))

    def _parse_education_from_lines(self, lines: list) -> list:
        """Parse education entries from flat text lines.

        Pattern per entry:
          Institute Name
          Degree, Field of Study
          Date Range
          [bullet details / activities]
        """
        items = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip bullets, dates, and "Activities" lines that aren't entry starts
            if line.startswith('·') or line.startswith('•') or self._is_date_line(line):
                i += 1
                continue
            if line.startswith('Activities and societies'):
                i += 1
                continue

            # This line should be an institute name
            institute = line
            degree = None
            start_year = None
            i += 1

            # Consume subsequent detail lines for this entry
            while i < len(lines):
                next_line = lines[i]

                if self._is_date_line(next_line):
                    start_year = next_line
                    i += 1
                elif next_line.startswith('·') or next_line.startswith('•') or next_line.startswith('Activities'):
                    i += 1  # skip detail lines
                elif degree is None and not self._is_date_line(next_line):
                    # This could be the degree line, or next entry
                    # Degree lines usually contain keywords like Bachelor, Master, etc.
                    # or are the field of study
                    if any(kw in next_line for kw in ['Bachelor', 'Master', 'Doctor', 'PhD', 'MBA',
                                                       'Diploma', 'Certificate', 'Program',
                                                       'B.Tech', 'BTech', 'M.Tech', 'B.Sc', 'M.Sc',
                                                       'Engineering', 'Science', 'Arts']):
                        degree = next_line
                        i += 1
                    elif ',' in next_line and len(next_line) < 100:
                        # Likely "Program Name, Field" format
                        degree = next_line
                        i += 1
                    else:
                        # Next entry starts here
                        break
                else:
                    break

            items.append({
                "institute": institute,
                "degree": degree,
                "start_year": start_year
            })

        return items

    def _parse_certifications_from_lines(self, lines: list) -> list:
        """Parse certification entries from flat text lines.

        Pattern per entry:
          Certification Name
          Issuer
          Issued Date [· Expires Date]
          [Credential ID ...]
          [image/badge text]
        """
        items = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip metadata lines that aren't entry starts
            if line.startswith('Issued') or line.startswith('Credential ID'):
                i += 1
                continue
            if 'certificate' in line.lower() and i > 0:
                # Likely an image alt-text, skip
                i += 1
                continue

            name = line
            issuer = None
            issue_date = None
            i += 1

            # Consume detail lines
            while i < len(lines):
                next_line = lines[i]

                if next_line.startswith('Issued'):
                    issue_date = next_line
                    i += 1
                elif next_line.startswith('Credential ID'):
                    i += 1  # skip
                elif 'certificate' in next_line.lower():
                    i += 1  # skip badge/image text
                elif issuer is None:
                    # Could be issuer or next cert name
                    # Issuer is usually a short org name
                    if not self._is_date_line(next_line) and len(next_line) < 80:
                        issuer = next_line
                        i += 1
                    else:
                        break
                else:
                    break

            items.append({
                "name": name,
                "issuer": issuer,
                "issue_date": issue_date
            })

        return items

    def _parse_projects_from_lines(self, lines: list) -> list:
        """Parse project entries from flat text lines.

        Pattern per entry:
          Project Name
          Date Range
          Associated with ...
          Description
          Skills
          [image alt-text - usually project name repeated]
          [Other contributors]
        """
        items = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip metadata lines
            if (line.startswith('Associated with') or
                line.startswith('Other contributors') or
                self._is_date_line(line) or
                'skill' in line.lower() and '+' in line):
                i += 1
                continue

            # Check if this line looks like a project name (not too long, not a description)
            if len(line) > 200:
                i += 1
                continue

            name = line
            description_parts = []
            i += 1

            # Consume detail lines
            while i < len(lines):
                next_line = lines[i]

                if self._is_date_line(next_line):
                    i += 1  # skip date line
                elif next_line.startswith('Associated with'):
                    i += 1
                elif next_line.startswith('Other contributors'):
                    i += 1
                elif 'skill' in next_line.lower() and ('+' in next_line or 'skill' in next_line.lower()):
                    i += 1  # skip skills line
                elif next_line == name:
                    i += 1  # skip duplicate (image alt text)
                elif len(next_line) > 30:
                    # Likely a description
                    description_parts.append(next_line)
                    i += 1
                else:
                    # Short line could be next project name
                    break

            desc = ' '.join(description_parts) if description_parts else None
            items.append({"name": name, "description": desc})

        return items

    def _extract_basic_live(self, url: str) -> BasicProfile:
        _scroll_main_to(self.page, 0)
        random_delay(1, 2)

        full_name = "Unknown"
        headline = None
        location = None
        connections = None
        followers = None

        try:
            name_el = self.page.locator('[data-testid="lazy-column"] section h2').first
            if name_el.count() > 0:
                text = name_el.inner_text().strip()
                section_words = {"about", "experience", "education", "activity", "skills",
                                 "featured", "interests", "notification", "more profiles",
                                 "explore premium", "certifications", "projects", "highlights"}
                if text and not any(w in text.lower() for w in section_words):
                    full_name = text
                    logger.info(f"Extracted name: {full_name}")
        except Exception as e:
            logger.debug(f"Name extraction error: {e}")

        # Extract headline, location from profile card
        try:
            card_section = self.page.locator('[data-testid="lazy-column"] section').first
            if card_section.count() > 0:
                card_text = card_section.inner_text()
                card_lines = [l.strip() for l in card_text.split('\n') if l.strip()]

                # Find headline: first long line after name that isn't metadata
                for line in card_lines:
                    if line == full_name:
                        continue
                    if len(line) < 5:
                        continue
                    if any(kw in line.lower() for kw in ['follower', 'connection', 'contact info', 'mutual']):
                        continue
                    if line in ('· 1st', '· 2nd', '· 3rd', '·'):
                        continue

                    if headline is None:
                        headline = line
                        logger.info(f"Extracted headline: {headline[:60]}")
                        continue

                    # Location: look for geographic patterns after headline
                    if location is None and line != headline:
                        # Location usually has commas (city, state) or known country names
                        if ',' in line or any(geo in line for geo in
                            ['India', 'United States', 'United Kingdom', 'Canada', 'Germany',
                             'France', 'Australia', 'Singapore', 'Area', 'Metropolitan']):
                            location = line
                            logger.info(f"Extracted location: {location}")
                            break
        except Exception as e:
            logger.debug(f"Headline/location extraction error: {e}")

        # Followers / Connections
        try:
            card_section = self.page.locator('[data-testid="lazy-column"] section').first
            if card_section.count() > 0:
                text = card_section.inner_text()
                followers_match = re.search(r'([\d,]+)\s*followers?', text)
                if followers_match:
                    followers = int(followers_match.group(1).replace(',', ''))
                conn_match = re.search(r'([\d,+]+)\s*connections?', text)
                if conn_match:
                    conn_str = conn_match.group(1).replace(',', '').replace('+', '')
                    connections = int(conn_str)
        except Exception as e:
            logger.debug(f"Followers/connections extraction error: {e}")

        return BasicProfile(
            profile_url=url,
            full_name=full_name,
            headline=headline,
            location=location,
            connection_count=connections,
            follower_count=followers
        )

    def _extract_about_live(self) -> str:
        try:
            sections = self.page.locator('[data-testid="lazy-column"] section')
            for i in range(sections.count()):
                section = sections.nth(i)
                h2 = section.locator('h2')
                if h2.count() > 0 and 'About' in h2.first.inner_text():
                    try:
                        section.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        pass
                    random_delay(0.5, 1.0)
                    spans = section.locator('span')
                    for j in range(spans.count()):
                        text = spans.nth(j).inner_text().strip()
                        if text and len(text) > 50 and 'About' not in text[:10]:
                            logger.info(f"Extracted about ({len(text)} chars)")
                            return text
        except Exception as e:
            logger.debug(f"About extraction error: {e}")
        return None

    def _parse_experience_item(self, lines: list) -> dict:
        """Parse experience item from text lines.

        LinkedIn experience format varies:
        - Simple: [Role, Company, Duration, Location, Description...]
        - Grouped: [Role, Employment Type, Duration, Location, Description...]
          (company name is in the parent group header)
        """
        role = lines[0] if lines else "Unknown"
        company = None
        employment_type = None
        duration = None
        location = None
        description = None

        emp_types = {'full-time', 'part-time', 'internship', 'contract', 'freelance',
                     'self-employed', 'seasonal', 'apprenticeship', 'volunteer'}

        for j, line in enumerate(lines[1:], start=1):
            lower = line.lower().strip()

            if lower in emp_types:
                employment_type = line
            elif re.search(r'\d{4}\s*[-–]', line) or 'Present' in line:
                duration = line
            elif company is None and lower not in emp_types and not self._is_date_line(line):
                # First non-type, non-date line after role is the company
                if 'skill' not in lower and '…' not in line[:5]:
                    company = line
            elif duration and not description:
                # Lines after duration that aren't skills are description
                remaining = [l for l in lines[j:] if not re.match(r'^Skills:', l, re.I)
                             and 'skill' not in l.lower()[:10]]
                if remaining:
                    description = ' '.join(remaining)
                break

        return {"role": role, "company": company, "duration": duration, "description": description}

    def _parse_education_item(self, lines: list) -> dict:
        institute = lines[0] if lines else "Unknown"
        degree = lines[1] if len(lines) > 1 else None
        start_year = None

        for line in lines:
            if re.search(r'\d{4}\s*[-–]', line):
                start_year = line
                break

        return {"institute": institute, "degree": degree, "start_year": start_year}

    def _parse_certification_item(self, lines: list) -> dict:
        return {
            "name": lines[0] if lines else "Unknown",
            "issuer": lines[1] if len(lines) > 1 else None,
            "issue_date": lines[2] if len(lines) > 2 else None
        }

    def _parse_project_item(self, lines: list) -> dict:
        return {
            "name": lines[0] if lines else "Unknown",
            "description": ' '.join(lines[1:]) if len(lines) > 1 else None
        }

    def _extract_company_links(self) -> list:
        """Extract company LinkedIn URLs from the Experience section only.

        Finds company links by looking for anchors within the experience section
        that point to /company/ URLs.
        """
        links = set()
        try:
            # Find the experience section
            sections = self.page.locator('[data-testid="lazy-column"] section')
            exp_section = None
            for i in range(sections.count()):
                h2 = sections.nth(i).locator('h2')
                if h2.count() > 0 and 'experience' in h2.first.inner_text(timeout=1000).lower():
                    exp_section = sections.nth(i)
                    break

            if exp_section:
                # Scroll to it to make sure it's in the DOM
                try:
                    exp_section.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                random_delay(0.5, 1.0)

                anchors = exp_section.locator('a[href*="/company/"]')
                count = anchors.count()
                for i in range(count):
                    try:
                        href = anchors.nth(i).get_attribute('href', timeout=1000)
                        if href and '/company/' in href:
                            url = href.split('?')[0].rstrip('/')
                            if not url.startswith('http'):
                                url = f"https://www.linkedin.com{url}"
                            links.add(url)
                    except Exception:
                        continue

            if not links:
                # Fallback: try to find company links anywhere on the page
                # but only the first few (likely from the profile card / experience)
                anchors = self.page.locator('a[href*="/company/"]')
                count = min(anchors.count(), 5)
                for i in range(count):
                    try:
                        href = anchors.nth(i).get_attribute('href', timeout=1000)
                        if href and '/company/' in href:
                            url = href.split('?')[0].rstrip('/')
                            if not url.startswith('http'):
                                url = f"https://www.linkedin.com{url}"
                            links.add(url)
                    except Exception:
                        continue

        except Exception:
            pass

        if links:
            logger.info(f"Found {len(links)} experience company links: {list(links)}")
        return list(links)

    def _extract_contacts(self, base_url: str):
        from scraper.models import ContactInfo

        email = None
        phone = None
        websites = []
        social_links = []
        birthday = None
        connected_at = None

        try:
             if base_url.endswith("/"):
                 base_url = base_url[:-1]
             contact_url = f"{base_url}/overlay/contact-info/"
             logger.info(f"Navigating to contact info: {contact_url}")

             self.page.goto(contact_url, wait_until="domcontentloaded")
             random_delay(1, 2)

             try:
                 self.page.wait_for_selector('dialog, [role="dialog"]', timeout=5000)
             except Exception:
                 pass
             random_delay(1, 2)

             html_content = self.page.content()
             soup = BeautifulSoup(html_content, "html.parser")

             # Parse contact info from the dialog's visible text
             # LinkedIn 2026 renders contacts as plain text, not structured HTML
             dialog = soup.find("dialog") or soup.find(attrs={"role": "dialog"})
             if dialog:
                 dialog_text = dialog.get_text(separator='\n', strip=True)
                 dialog_lines = [l.strip() for l in dialog_text.split('\n') if l.strip()]

                 # Parse by looking for section labels and their following values
                 for idx, line in enumerate(dialog_lines):
                     lower = line.lower()

                     if lower == 'email' and idx + 1 < len(dialog_lines):
                         email = dialog_lines[idx + 1]

                     elif lower == 'phone' and idx + 1 < len(dialog_lines):
                         phone = dialog_lines[idx + 1]

                     elif lower == 'website' and idx + 1 < len(dialog_lines):
                         # Website may have URL on next line, and type in parentheses after
                         url_line = dialog_lines[idx + 1]
                         if not url_line.startswith('('):
                             websites.append(url_line)
                         # Check for more websites
                         j = idx + 2
                         while j < len(dialog_lines):
                             if dialog_lines[j].startswith('('):
                                 j += 1  # skip type label
                                 continue
                             # If it's another URL-like value before the next section
                             if dialog_lines[j].lower() in ('email', 'phone', 'birthday',
                                                             'connected since', 'twitter',
                                                             'im', 'address'):
                                 break
                             if '.' in dialog_lines[j] and len(dialog_lines[j]) < 100:
                                 websites.append(dialog_lines[j])
                             j += 1

                     elif lower == 'birthday' and idx + 1 < len(dialog_lines):
                         birthday = dialog_lines[idx + 1]

                     elif lower == 'connected since' and idx + 1 < len(dialog_lines):
                         connected_at = dialog_lines[idx + 1]

                     elif lower == 'twitter' and idx + 1 < len(dialog_lines):
                         social_links.append(dialog_lines[idx + 1])

                     elif lower == 'address' and idx + 1 < len(dialog_lines):
                         pass  # could store if needed

             # Also try to extract email from mailto links as fallback
             if not email:
                 for a in soup.find_all("a", href=True):
                     if "mailto:" in a["href"]:
                         email = a.text.strip() or a["href"].replace("mailto:", "")
                         break

        except Exception as e:
             logger.error(f"Error parsing contact info overlay: {e}")

        finally:
             self.page.goto(base_url, wait_until="domcontentloaded")

        return ContactInfo(
            email=email,
            phone=phone,
            websites=websites,
            social_links=social_links,
            birthday=birthday,
            connected_at=connected_at
        )
