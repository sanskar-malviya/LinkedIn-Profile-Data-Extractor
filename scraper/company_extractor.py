import re
import random
import logging
from playwright.sync_api import Page
from scraper.utils import random_delay
from scraper.models import CompanyData, CompanyEmployee, CompanyJob

logger = logging.getLogger(__name__)


def _scroll_main(page: Page, delta: int):
    page.evaluate(f"""(() => {{
        const el = document.querySelector('main') || document.documentElement;
        el.scrollBy(0, {delta});
    }})()""")


def _scroll_main_to(page: Page, position: int):
    page.evaluate(f"""(() => {{
        const el = document.querySelector('main') || document.documentElement;
        el.scrollTo(0, {position});
    }})()""")


def _get_scroll_info(page: Page) -> tuple:
    return page.evaluate("""(() => {
        const el = document.querySelector('main') || document.documentElement;
        return [el.scrollTop, el.scrollHeight, el.clientHeight];
    })()""")


class CompanyExtractor:
    def __init__(self, page: Page):
        self.page = page

    def extract_company(self, url: str) -> dict:
        """Navigate to a LinkedIn company page and extract all details."""
        logger.info(f"Scraping company: {url}")

        if not url.startswith("http"):
            url = f"https://{url}"

        base_url = url.rstrip('/')

        # Set up API response interception for faster data capture
        self._api_data = []

        def _capture_api(response):
            try:
                if 'voyager/api' in response.url or 'graphql' in response.url:
                    data = response.json()
                    self._api_data.append({
                        'url': response.url,
                        'data': data
                    })
            except Exception:
                pass

        self.page.on("response", _capture_api)

        # 1. About page — company details, phone, email, address
        about_data = self._scrape_about_page(base_url)

        # 2. Jobs page — detailed job listings
        jobs = self._scrape_jobs_page(base_url)
        about_data['jobs'] = [j.model_dump() for j in jobs]
        about_data['jobs_count'] = f"{len(jobs)} jobs"

        # 3. People page — employee listings via DOM + API
        employees = self._scrape_people_page(base_url)

        # Enrich with any API-captured employee data
        api_employees = self._extract_employees_from_api()
        if api_employees:
            logger.info(f"API captured {len(api_employees)} additional employees")
            existing_urls = {e.profile_url for e in employees if e.profile_url}
            for emp in api_employees:
                if emp.profile_url and emp.profile_url not in existing_urls:
                    employees.append(emp)
                    existing_urls.add(emp.profile_url)

        about_data['employees'] = [e.model_dump() for e in employees]

        # Cleanup
        self.page.remove_listener("response", _capture_api)
        self._api_data = []

        logger.info(f"Company '{about_data.get('name', 'Unknown')}': "
                     f"{len(employees)} employees, {len(jobs)} jobs")

        return about_data

    def _extract_employees_from_api(self) -> list:
        """Parse employee data from captured LinkedIn API responses."""
        employees = []
        seen = set()

        for entry in self._api_data:
            try:
                data = entry['data']
                # LinkedIn API responses have various structures
                # Look for profile data in included/elements arrays
                elements = None
                if isinstance(data, dict):
                    elements = data.get('included') or data.get('elements') or []
                    # Also check nested data
                    if 'data' in data and isinstance(data['data'], dict):
                        nested = data['data']
                        elements = (elements or []) + (nested.get('included') or
                                                        nested.get('elements') or [])

                if not elements:
                    continue

                for item in elements:
                    if not isinstance(item, dict):
                        continue

                    # Look for miniProfile or profile objects
                    mini = item.get('miniProfile') or item.get('profile')
                    if not mini and item.get('$type', '').endswith('MiniProfile'):
                        mini = item

                    if not mini or not isinstance(mini, dict):
                        continue

                    first = mini.get('firstName', '')
                    last = mini.get('lastName', '')
                    occupation = mini.get('occupation', '')
                    public_id = mini.get('publicIdentifier', '')

                    if not first or not public_id:
                        continue

                    name = f"{first} {last}".strip()
                    profile_url = f"https://www.linkedin.com/in/{public_id}"

                    if profile_url in seen:
                        continue
                    seen.add(profile_url)

                    employees.append(CompanyEmployee(
                        name=name,
                        title=occupation or None,
                        profile_url=profile_url
                    ))

            except Exception:
                continue

        return employees

    def _scroll_page(self, max_scrolls=20):
        _scroll_main_to(self.page, 0)
        random_delay(0.5, 1.0)

        last_height = _get_scroll_info(self.page)[1]
        stale = 0

        for i in range(max_scrolls):
            _scroll_main(self.page, random.randint(400, 600))
            random_delay(1.0, 1.5)

            top, height, client = _get_scroll_info(self.page)
            at_bottom = (top + client) >= height - 100

            if height == last_height and at_bottom:
                stale += 1
                if stale >= 3:
                    break
            else:
                stale = 0
            last_height = height

    # ──────────────────────────────────────────────
    #  ABOUT PAGE
    # ──────────────────────────────────────────────
    def _scrape_about_page(self, base_url: str) -> dict:
        about_url = f"{base_url}/about"
        self.page.goto(about_url, wait_until="domcontentloaded")
        random_delay(3, 5)

        try:
            self.page.wait_for_selector('main', timeout=10000)
        except Exception:
            pass

        self._scroll_page()

        try:
            main_text = self.page.locator('main').inner_text(timeout=5000)
            lines = [l.strip() for l in main_text.split('\n') if l.strip()]
        except Exception:
            lines = []

        if not lines:
            return CompanyData(company_url=base_url).model_dump()

        # Company name
        name = None
        try:
            h1 = self.page.locator('h1').first
            if h1.count() > 0:
                name = h1.inner_text().strip()
        except Exception:
            pass
        if not name and lines:
            name = lines[0]

        # Parse all labeled fields from the about page
        tagline = None
        industry = None
        company_size = None
        headquarters = None
        founded = None
        company_type = None
        specialties = None
        website = None
        phone = None
        email = None
        follower_count = None
        employee_count = None
        verified = None
        about = None
        address = None
        locations = []

        # Simple label→value fields (label on one line, value on the next)
        field_map = {
            'industry': 'industry',
            'company size': 'company_size',
            'headquarters': 'headquarters',
            'founded': 'founded',
            'type': 'company_type',
            'specialties': 'specialties',
            'website': 'website',
            'phone': 'phone',
        }

        for idx, line in enumerate(lines):
            lower = line.lower().strip()

            # Labeled fields
            if lower in field_map and idx + 1 < len(lines):
                value = lines[idx + 1]
                field = field_map[lower]
                if field == 'industry':
                    industry = value
                elif field == 'company_size':
                    company_size = value
                elif field == 'headquarters':
                    headquarters = value
                elif field == 'founded':
                    founded = value
                elif field == 'company_type':
                    company_type = value
                elif field == 'specialties':
                    specialties = value
                elif field == 'website':
                    website = value
                elif field == 'phone':
                    phone = value

            # Follower count
            if 'followers' in lower and not follower_count:
                match = re.search(r'([\d,]+[KMB]?)\s*followers?', line, re.I)
                if match:
                    raw = match.group(1).replace(',', '')
                    if 'K' in raw:
                        follower_count = int(float(raw.replace('K', '')) * 1000)
                    elif 'M' in raw:
                        follower_count = int(float(raw.replace('M', '')) * 1000000)
                    else:
                        follower_count = int(raw)

            # Employee count on LinkedIn
            if 'associated members' in lower:
                match = re.search(r'([\d,]+)\s*associated', lower)
                if match:
                    employee_count = f"{match.group(1)} associated members"

            # Verified page
            if lower == 'verified page' and idx + 1 < len(lines):
                verified = lines[idx + 1]

            # Locations section
            if lower.startswith('locations'):
                j = idx + 1
                while j < len(lines):
                    loc = lines[j]
                    loc_lower = loc.lower()
                    if loc_lower.startswith('get directions'):
                        j += 1
                        continue
                    if loc_lower in field_map or loc_lower in (
                        'affiliated pages', 'similar pages', 'overview',
                        'about') or loc_lower.startswith('get directions to'):
                        break
                    if loc == 'Primary':
                        j += 1
                        continue
                    if len(loc) > 5:
                        locations.append(loc)
                        # First location is the full address
                        if not address:
                            address = loc
                    j += 1

        # Extract email from the about text (often in the overview)
        for line in lines:
            email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', line)
            if email_match:
                email = email_match.group(0)
                break

        # Tagline: short descriptive line near top, after company name
        skip_words = {'followers', 'employees', 'industry', 'company size',
                      'headquarters', 'founded', 'type', 'website', 'specialties',
                      'overview', 'about', 'on linkedin', 'follow', 'message',
                      'visit', 'home', 'subscribed', 'notification', 'click to',
                      'services', 'posts', 'jobs', 'people', 'phone', 'verified'}
        for idx, line in enumerate(lines[:10]):
            if line == name:
                continue
            lower = line.lower()
            if len(line) > 10 and len(line) < 200:
                if not any(kw in lower for kw in skip_words):
                    tagline = line
                    break

        # About/Overview text
        try:
            _scroll_main_to(self.page, 0)
            random_delay(0.5, 1.0)

            sections = self.page.locator('main section')
            for i in range(sections.count()):
                sec = sections.nth(i)
                try:
                    sec_text = sec.inner_text(timeout=2000).strip()
                    if 'Overview' in sec_text[:50] or 'About' in sec_text[:50]:
                        sec_lines = [l.strip() for l in sec_text.split('\n') if l.strip()]
                        content_lines = []
                        past_header = False
                        for sl in sec_lines:
                            if sl.lower() in ('overview', 'about'):
                                past_header = True
                                continue
                            if past_header and sl.lower() not in ('see more', 'show more'):
                                if sl.lower() in field_map:
                                    break
                                content_lines.append(sl)
                        if content_lines:
                            about = '\n'.join(content_lines)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        return CompanyData(
            company_url=base_url,
            name=name,
            tagline=tagline,
            industry=industry,
            company_size=company_size,
            headquarters=headquarters,
            founded=founded,
            company_type=company_type,
            specialties=specialties,
            website=website,
            phone=phone,
            email=email,
            follower_count=follower_count,
            employee_count_on_linkedin=employee_count,
            verified=verified,
            about=about,
            address=address,
            locations=locations,
        ).model_dump()

    # ──────────────────────────────────────────────
    #  JOBS PAGE
    # ──────────────────────────────────────────────
    def _scrape_jobs_page(self, base_url: str) -> list:
        """Scrape detailed job listings from /jobs with pagination."""
        jobs_url = f"{base_url}/jobs"
        self.page.goto(jobs_url, wait_until="domcontentloaded")
        random_delay(3, 5)

        try:
            self.page.wait_for_selector('main', timeout=10000)
        except Exception:
            pass

        all_jobs = []
        max_pages = 5

        for page_num in range(max_pages):
            self._scroll_page(max_scrolls=8)

            try:
                main_text = self.page.locator('main').inner_text(timeout=5000)
                lines = [l.strip() for l in main_text.split('\n') if l.strip()]
            except Exception:
                break

            # Parse job cards from text
            # Structure: "Job Title" label, title, title(dup), "Company Name" label,
            #            company, location, "Posted" label, time, "Save"
            page_jobs = []
            i = 0
            while i < len(lines):
                if lines[i] == 'Job Title' and i + 1 < len(lines):
                    title = lines[i + 1]
                    location = None
                    posted = None

                    # Scan forward for location and posted date
                    j = i + 2
                    while j < len(lines) and lines[j] != 'Job Title':
                        if lines[j] == 'Posted' and j + 1 < len(lines):
                            posted = lines[j + 1]
                            j += 2
                        elif lines[j] == 'Company Name':
                            j += 2  # skip company name (we already know it)
                        elif lines[j] == 'Save' or lines[j] == title:
                            j += 1
                        elif not location:
                            # Short non-label line is likely the location
                            if len(lines[j]) < 80 and lines[j] not in (
                                'Job Title', 'Company Name', 'Posted', 'Save',
                                'Show all jobs'):
                                location = lines[j]
                            j += 1
                        else:
                            j += 1

                    page_jobs.append(CompanyJob(
                        title=title,
                        location=location,
                        posted=posted
                    ))
                    i = j
                else:
                    i += 1

            all_jobs.extend(page_jobs)
            logger.info(f"Jobs page {page_num + 1}: found {len(page_jobs)} jobs")

            if not page_jobs:
                break

            # Try next page
            try:
                next_btn = self.page.locator('button:has-text("Next"), [aria-label="Next"]').first
                if next_btn.count() > 0 and next_btn.is_enabled():
                    next_btn.click()
                    random_delay(2, 4)
                else:
                    break
            except Exception:
                break

        # Deduplicate by title
        seen = set()
        unique = []
        for j in all_jobs:
            if j.title not in seen:
                seen.add(j.title)
                unique.append(j)

        logger.info(f"Total unique jobs: {len(unique)}")
        return unique

    # ──────────────────────────────────────────────
    #  PEOPLE PAGE
    # ──────────────────────────────────────────────
    def _scrape_people_page(self, base_url: str) -> list:
        """Scrape the /people page with 'Show more results' and pagination."""
        people_url = f"{base_url}/people"
        self.page.goto(people_url, wait_until="domcontentloaded")
        random_delay(3, 5)

        try:
            self.page.wait_for_selector('main', timeout=10000)
        except Exception:
            pass

        all_employees = []
        existing_urls = set()
        no_new_streak = 0

        # Phase 1: Click "Show more results" until it disappears
        for click_i in range(30):
            self._scroll_page(max_scrolls=10)

            page_employees = self._extract_people_cards()
            new_count = self._merge_employees(page_employees, all_employees, existing_urls)

            logger.info(f"Show more [{click_i + 1}]: {new_count} new, {len(all_employees)} total")

            if new_count == 0:
                no_new_streak += 1
                if no_new_streak >= 2:
                    break
            else:
                no_new_streak = 0

            try:
                show_more = self.page.locator('button:has-text("Show more results")').first
                if show_more.count() > 0 and show_more.is_visible():
                    show_more.click()
                    random_delay(2, 3)
                else:
                    break
            except Exception:
                break

        # Phase 2: Paginate with "Next" button for remaining pages
        for page_i in range(30):
            try:
                next_btn = self.page.locator('button:has-text("Next"), [aria-label="Next"]').first
                if next_btn.count() == 0 or not next_btn.is_enabled():
                    break
                next_btn.click()
                random_delay(2, 4)
            except Exception:
                break

            self._scroll_page(max_scrolls=10)

            # Click all "Show more results" on this new page too
            for _ in range(10):
                page_employees = self._extract_people_cards()
                new_count = self._merge_employees(page_employees, all_employees, existing_urls)

                logger.info(f"Page {page_i + 2}, {new_count} new, {len(all_employees)} total")

                if new_count == 0:
                    break

                try:
                    show_more = self.page.locator('button:has-text("Show more results")').first
                    if show_more.count() > 0 and show_more.is_visible():
                        show_more.click()
                        random_delay(2, 3)
                        self._scroll_page(max_scrolls=5)
                    else:
                        break
                except Exception:
                    break

        logger.info(f"Extracted {len(all_employees)} employees total")
        return all_employees

    def _merge_employees(self, new_emps: list, all_emps: list, seen_urls: set) -> int:
        """Merge new employees into the master list, deduplicating by URL."""
        added = 0
        for emp in new_emps:
            if emp.profile_url and emp.profile_url not in seen_urls:
                all_emps.append(emp)
                seen_urls.add(emp.profile_url)
                added += 1
        return added
        return all_employees

    def _extract_people_cards(self) -> list:
        """Extract employee name+title from the current people page view."""
        employees = []
        try:
            main_text = self.page.locator('main').inner_text(timeout=5000)
            all_lines = [l.strip() for l in main_text.split('\n') if l.strip()]

            # Build profile URL map
            profile_links = {}
            anchors = self.page.locator('main a[href*="/in/"]')
            for i in range(anchors.count()):
                try:
                    a = anchors.nth(i)
                    href = a.get_attribute('href', timeout=1000)
                    if href and '/in/' in href:
                        url = href.split('?')[0].rstrip('/')
                        if not url.startswith('http'):
                            url = f"https://www.linkedin.com{url}"
                        text = a.inner_text(timeout=1000).strip()
                        if text and 2 < len(text) < 60:
                            profile_links[text] = url
                except Exception:
                    continue

            if not profile_links:
                return employees

            # Find start of employee cards (first profile link name in the text)
            start_idx = 0
            for idx, line in enumerate(all_lines):
                if line in profile_links:
                    start_idx = idx
                    break

            # Find end
            end_idx = len(all_lines)
            for idx in range(start_idx, len(all_lines)):
                if all_lines[idx].lower() in ('show more results', 'no results found'):
                    end_idx = idx
                    break

            employee_lines = all_lines[start_idx:end_idx]

            # Parse cards
            skip_patterns = re.compile(
                r'^(\d+(st|nd|rd|th)\s+degree\s+connection|'
                r'·\s*\d+(st|nd|rd|th)|'
                r'.+mutual connections?$|'
                r'Provides services\s*-|'
                r'Page \d+ of \d+)',
                re.I)
            noise = {'connect', 'message', 'follow', 'following', 'pending',
                     'view profile', 'see all', 'show more', 'add', 'next',
                     'previous', 'show more results'}

            i = 0
            while i < len(employee_lines):
                line = employee_lines[i]
                lower = line.lower()

                if lower in noise or len(line) < 2 or skip_patterns.match(line):
                    i += 1
                    continue

                if line in profile_links:
                    name = line
                    title = None
                    profile_url = profile_links[name]

                    j = i + 1
                    while j < len(employee_lines):
                        next_line = employee_lines[j]
                        next_lower = next_line.lower()

                        if (next_lower in noise or skip_patterns.match(next_line)
                                or len(next_line) < 2):
                            j += 1
                            continue
                        if next_line in profile_links:
                            break
                        if len(next_line) > 3:
                            title = next_line
                        break

                    employees.append(CompanyEmployee(
                        name=name,
                        title=title,
                        profile_url=profile_url
                    ))
                    i = j + 1 if title else i + 1
                    continue

                i += 1

        except Exception as e:
            logger.error(f"People card extraction error: {e}")

        return employees
