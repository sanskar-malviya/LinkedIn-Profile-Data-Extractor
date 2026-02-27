import urllib.parse
from bs4 import BeautifulSoup
import json
import logging
from playwright.sync_api import Page
from scraper.utils import scroll_to_bottom, random_delay
from scraper.models import BasicProfile, Experience, Education, Skill, Certification, Project, ProfileData

logger = logging.getLogger(__name__)

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
                
        # We can intercept graphQL responses here to capture structured data
        graphql_data = []
        
        def handle_response(response):
            if "graphql" in response.url:
                try:
                    # Capture the data
                    data = response.json()
                    graphql_data.append(data)
                except Exception:
                    pass

        self.page.on("response", handle_response)
        
        self.page.goto(url, wait_until="domcontentloaded")
        random_delay(2, 4)
        
        # Ensure we are not on a 404 or auth wall
        if "404" in self.page.title() or "authwall" in self.page.url:
            raise Exception("Profile not found or blocked by authwall.")
            
        # Scroll to load everything
        logger.info("Scrolling profile to trigger lazy loading...")
        scroll_to_bottom(self.page)
        
        # For simplicity and robust parsing without full GraphQL schema reverse engineering, 
        # we parse the DOM for basic sections and use the fallback. 
        # A full production system would deeply analyze the `graphql_data`.
        
        html_content = self.page.content()
        soup = BeautifulSoup(html_content, "html.parser")
        
        profile_data = self._parse_dom(soup, url)
        
        # Now dynamically grab contact info by opening the overlay
        profile_data.contact_info = self._extract_contacts(url)
        
        # Cleanup listener
        self.page.remove_listener("response", handle_response)
        
        return profile_data.model_dump()
        
    def _parse_dom(self, soup: BeautifulSoup, url: str) -> ProfileData:
        # Basic Profile extraction
        name_elem = soup.find("h1", class_="text-heading-xlarge")
        if not name_elem:
             name_elem = soup.find("h1")

        headline_elem = soup.find("div", class_="text-body-medium")
        location_elem = soup.find("span", class_="text-body-small inline t-black--light break-words")
        
        full_name = name_elem.text.strip() if name_elem else "Unknown"
        headline = headline_elem.text.strip() if headline_elem else None
        location = location_elem.text.strip() if location_elem else None
        
        # Open to work detection mimicking linkedin-scraper
        open_to_work = False
        img_elem = soup.select_one(".pv-top-card-profile-picture img")
        if img_elem and img_elem.has_attr("title"):
             if "#OPEN_TO_WORK" in img_elem["title"].upper():
                 open_to_work = True
        if open_to_work and headline:
             headline = f"[OPEN TO WORK] {headline}"
        
        # Very rough extraction for followers/connections
        connections = None
        followers = None
        conn_elem = soup.find("span", class_="t-bold", string=lambda text: text and "connection" in text.lower())
        if conn_elem:
           try:
               connections = int(''.join(filter(str.isdigit, conn_elem.text)))
           except: pass

        basic = BasicProfile(
            profile_url=url,
            full_name=full_name,
            headline=headline,
            location=location,
            connection_count=connections,
            follower_count=followers
        )

        return ProfileData(
            profile_url=url,
            basic=basic,
            about=self._extract_about(soup),
            experience=self._extract_experience(soup),
            education=self._extract_education(soup),
            skills=self._extract_skills(soup),
            certifications=self._extract_certifications(soup),
            projects=self._extract_projects(soup),
            contact_info=None # Populated dynamically later
        )

    def _extract_about(self, soup: BeautifulSoup) -> str:
        about_section = soup.find("div", {"id": "about"})
        if about_section:
            parent = about_section.find_parent("section")
            if parent:
                text_elem = parent.find("div", class_="display-flex ph5 pv3")
                if text_elem:
                    return text_elem.text.strip()
        return None

    def _extract_experience(self, soup: BeautifulSoup) -> list:
        experiences = []
        exp_section = soup.find("div", {"id": "experience"})
        if exp_section:
             parent = exp_section.find_parent("section")
             if parent:
                 items = parent.find_all("li", class_="artdeco-list__item")
                 for item in items:
                     try:
                         # LinkedIn stores visible text in spans with aria-hidden="true" to avoid screen reader duplication
                         spans = item.find_all("span", {"aria-hidden": "true"})
                         texts = [s.text.strip() for s in spans if s.text.strip()]
                         
                         if len(texts) >= 3:
                             # Very rough heuristic: role, company, dates
                             exp = Experience(
                                 role=texts[0],
                                 company=texts[1],
                                 duration=texts[2] if len(texts) > 2 else None,
                                 description=" ".join(texts[3:]) if len(texts) > 3 else None
                             )
                             experiences.append(exp)
                     except Exception as e:
                         pass
        return experiences
        
    def _extract_education(self, soup: BeautifulSoup) -> list:
        education = []
        edu_section = soup.find("div", {"id": "education"})
        if edu_section:
             parent = edu_section.find_parent("section")
             if parent:
                 items = parent.find_all("li", class_="artdeco-list__item")
                 for item in items:
                     try:
                         spans = item.find_all("span", {"aria-hidden": "true"})
                         texts = [s.text.strip() for s in spans if s.text.strip()]
                         
                         if len(texts) >= 1:
                             edu = Education(
                                 institute=texts[0],
                                 degree=texts[1] if len(texts) > 1 else None,
                                 start_year=texts[2] if len(texts) > 2 else None
                             )
                             education.append(edu)
                     except Exception as e:
                         pass
        return education

    def _extract_skills(self, soup: BeautifulSoup) -> list:
        skills = []
        skills_section = soup.find("div", {"id": "skills"})
        if skills_section:
             parent = skills_section.find_parent("section")
             if parent:
                 items = parent.find_all("li", class_="artdeco-list__item")
                 for item in items:
                     try:
                         spans = item.find_all("span", {"aria-hidden": "true"})
                         texts = [s.text.strip() for s in spans if s.text.strip()]
                         if texts:
                             skills.append(Skill(name=texts[0]))
                     except Exception:
                         pass
        return skills

    def _extract_certifications(self, soup: BeautifulSoup) -> list:
        certs = []
        cert_section = soup.find("div", {"id": "licenses_and_certifications"})
        if cert_section:
             parent = cert_section.find_parent("section")
             if parent:
                 items = parent.find_all("li", class_="artdeco-list__item")
                 for item in items:
                     try:
                         spans = item.find_all("span", {"aria-hidden": "true"})
                         texts = [s.text.strip() for s in spans if s.text.strip()]
                         if len(texts) >= 1:
                             certs.append(Certification(
                                 name=texts[0],
                                 issuer=texts[1] if len(texts) > 1 else None,
                                 issue_date=texts[2] if len(texts) > 2 else None
                             ))
                     except Exception:
                         pass
        return certs

    def _extract_projects(self, soup: BeautifulSoup) -> list:
        projects = []
        proj_section = soup.find("div", {"id": "projects"})
        if proj_section:
             parent = proj_section.find_parent("section")
             if parent:
                 items = parent.find_all("li", class_="artdeco-list__item")
                 for item in items:
                     try:
                         spans = item.find_all("span", {"aria-hidden": "true"})
                         texts = [s.text.strip() for s in spans if s.text.strip()]
                         if len(texts) >= 1:
                             projects.append(Project(
                                 name=texts[0],
                                 description=" ".join(texts[1:]) if len(texts) > 1 else None
                             ))
                     except Exception:
                         pass
        return projects

    def _extract_contacts(self, base_url: str):
        from scraper.models import ContactInfo
        
        email = None
        phone = None
        websites = []
        social_links = []
        
        try:
             # Strip trailing slash if present
             if base_url.endswith("/"):
                 base_url = base_url[:-1]
             contact_url = f"{base_url}/overlay/contact-info/"
             logger.info(f"Navigating to contact info: {contact_url}")
             
             self.page.goto(contact_url, wait_until="domcontentloaded")
             random_delay(1, 2)
             
             # Locate the dialog
             dialog = self.page.locator('dialog, [role="dialog"]').first
             if dialog.count() == 0:
                 logger.warning("Contact info dialog not found")
                 return ContactInfo()
                 
             # Wait for the sections to load
             self.page.wait_for_selector('h3', timeout=5000)
             
             html_content = self.page.content()
             soup = BeautifulSoup(html_content, "html.parser")
             
             # Parse email
             email_section = soup.find("h3", string=lambda text: text and "Email" in text)
             if email_section:
                 email_a = email_section.find_next("a", href=lambda href: href and "mailto:" in href)
                 if email_a:
                     email = email_a.text.strip()
                     
             # Parse websites/socials (anything with a link)
             website_section = soup.find("h3", string=lambda text: text and "Website" in text)
             if website_section:
                 ul = website_section.find_next("ul")
                 if ul:
                     links = ul.find_all("a", href=True)
                     for link in links:
                         href = link["href"]
                         websites.append(href)
                         
             # Parse phone
             phone_section = soup.find("h3", string=lambda text: text and "Phone" in text)
             if phone_section:
                 span = phone_section.find_next("span", class_="t-14")
                 if span:
                     phone = span.text.strip()
                     
             # Parse birthday
             birthday = None
             birthday_section = soup.find("h3", string=lambda text: text and "Birthday" in text)
             if birthday_section:
                 parent = birthday_section.find_parent("section")
                 if parent:
                     b_text = parent.text.replace(birthday_section.text, "").strip()
                     if b_text:
                         birthday = b_text

             # Parse connected
             connected_at = None
             connected_section = soup.find("h3", string=lambda text: text and "Connected" in text)
             if connected_section:
                 parent = connected_section.find_parent("section")
                 if parent:
                     c_text = parent.text.replace(connected_section.text, "").strip()
                     if c_text:
                         connected_at = c_text
                     
             # Profile url anchor itself is usually present, we skip that or add it.
             # We can also scrape any loose unhandled links.
             contact_sections = soup.find_all("section", class_="pv-contact-info__contact-type")
             for section in contact_sections:
                 anchors = section.find_all("a", href=True)
                 for a in anchors:
                     href = a["href"]
                     # Filter out internal linkedin links
                     if "linkedin.com/in/" not in href and "mailto:" not in href and href not in websites:
                         social_links.append(href)
                         
        except Exception as e:
             logger.error(f"Error parsing contact info overlay: {e}")
             
        finally:
             # Nav back to main profile page just in case
             self.page.goto(base_url, wait_until="domcontentloaded")
             
        return ContactInfo(
            email=email,
            phone=phone,
            websites=websites,
            social_links=social_links,
            birthday=birthday,
            connected_at=connected_at
        )
