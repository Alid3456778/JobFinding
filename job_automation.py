import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote
import concurrent.futures
from dataclasses import dataclass
from typing import List, Optional
import random

@dataclass
class Job:
    title: str
    company: str
    location: str
    link: str
    source: str
    posted_date: str = ""
    salary: str = ""
    description: str = ""

class JobScraper:
    def __init__(self):
        self.session = requests.Session()
        # Rotate user agents to avoid detection
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.jobs = []
        
    def add_delay(self, min_delay=1, max_delay=3):
        """Add random delay to avoid being blocked"""
        time.sleep(random.uniform(min_delay, max_delay))
        
    def get_jobs_internshala(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Enhanced Internshala scraper with multiple selector fallbacks"""
        print(f"🔍 Searching Internshala for {title} in {location}...")
        jobs = []
        
        try:
            # Try different URL formats
            urls_to_try = [
                f"https://internshala.com/jobs/{title.replace(' ', '-')}-jobs-in-{location.replace(' ', '-')}",
                f"https://internshala.com/jobs/{title.replace(' ', '-')}-jobs",
                f"https://internshala.com/jobs/keyword-{title.replace(' ', '%20')}/location-{location.replace(' ', '%20')}"
            ]
            
            for url in urls_to_try:
                try:
                    self.session.headers['User-Agent'] = random.choice(self.user_agents)
                    response = self.session.get(url, timeout=15)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Multiple selector options
                        selectors = [
                            '.individual_internship',
                            '.internship_meta',
                            '.job-container',
                            '[class*="internship"]',
                            '.job-listing'
                        ]
                        
                        listings = []
                        for selector in selectors:
                            listings = soup.select(selector)[:max_results]
                            if listings:
                                print(f"✅ Found listings with selector: {selector}")
                                break
                        
                        if not listings:
                            print(f"⚠️ No listings found with any selector on {url}")
                            continue
                        
                        for job_elem in listings:
                            try:
                                # Multiple title selectors
                                title_selectors = [
                                    'div.heading_4_5', '.profile h3', '.job-title', 
                                    'h3', 'h2', '[class*="title"]', '.internship-title'
                                ]
                                job_title = self.extract_text_with_selectors(job_elem, title_selectors)
                                
                                # Multiple company selectors
                                company_selectors = [
                                    'a.link_display_like_text', '.company-name', 
                                    '.company', '[class*="company"]', '.employer-name'
                                ]
                                company = self.extract_text_with_selectors(job_elem, company_selectors)
                                
                                # Extract job link - try multiple approaches
                                job_link = ""
                                
                                # Method 1: Look for direct job links
                                link_selectors = [
                                    'a.view_detail_button', 'a[href*="/jobs/detail/"]',
                                    'a[href*="/internship/detail/"]', '.apply-link a', 
                                    'a[href*="/jobs/"]', 'a[href*="/job/"]'
                                ]
                                job_link = self.extract_link_with_selectors(job_elem, link_selectors, "https://internshala.com")
                                
                                # Method 2: If no direct link, try to find any link in the job element
                                if not job_link:
                                    all_links = job_elem.find_all('a', href=True)
                                    for link in all_links:
                                        href = link.get('href', '')
                                        if any(keyword in href for keyword in ['/jobs/', '/internship/', '/detail/', '/job/']):
                                            if href.startswith('/'):
                                                job_link = "https://internshala.com" + href
                                            elif href.startswith('http'):
                                                job_link = href
                                            else:
                                                job_link = "https://internshala.com/" + href
                                            break
                                
                                # Method 3: Construct link from job ID if available
                                if not job_link and job_elem.get('data-job-id'):
                                    job_id = job_elem.get('data-job-id')
                                    job_link = f"https://internshala.com/jobs/detail/{job_id}"
                                
                                # Salary and date
                                salary_selectors = ['.salary', '.stipend', '.compensation', '[class*="salary"]']
                                salary = self.extract_text_with_selectors(job_elem, salary_selectors, "Not specified")
                                
                                date_selectors = ['.status-success', '.date', '.posted-date', '[class*="date"]']
                                posted_date = self.extract_text_with_selectors(job_elem, date_selectors, "Recently")
                                
                                if job_title and company:
                                    jobs.append(Job(
                                        title=job_title,
                                        company=company,
                                        location=location.title(),
                                        link=job_link,
                                        source="Internshala",
                                        salary=salary,
                                        posted_date=posted_date
                                    ))
                            except Exception as e:
                                print(f"⚠️ Error parsing job element: {e}")
                                continue
                        
                        if jobs:
                            break  # Found jobs, no need to try other URLs
                            
                    self.add_delay()
                    
                except Exception as e:
                    print(f"⚠️ Error with URL {url}: {e}")
                    continue
                    
        except Exception as e:
            print(f"⚠️ Internshala error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Internshala")
        return jobs

    def get_jobs_indeed(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Enhanced Indeed scraper"""
        print(f"🔍 Searching Indeed for {title} in {location}...")
        jobs = []
        
        try:
            params = {
                'q': title,
                'l': location,
                'fromage': '7',
                'sort': 'date',
                'limit': str(max_results)
            }
            
            # Try different Indeed domains
            domains = [
                'https://in.indeed.com/jobs',
                'https://www.indeed.co.in/jobs',
                'https://indeed.com/jobs'
            ]
            
            for base_url in domains:
                try:
                    url = f"{base_url}?{urlencode(params)}"
                    self.session.headers['User-Agent'] = random.choice(self.user_agents)
                    response = self.session.get(url, timeout=15)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Multiple job card selectors
                        card_selectors = [
                            '[data-jk]',
                            '.job_seen_beacon',
                            '.jobsearch-SerpJobCard',
                            '.result',
                            '[class*="jobsearch"]'
                        ]
                        
                        job_cards = []
                        for selector in card_selectors:
                            job_cards = soup.select(selector)[:max_results]
                            if job_cards:
                                print(f"✅ Found job cards with selector: {selector}")
                                break
                        
                        for card in job_cards:
                            try:
                                # Title extraction
                                title_selectors = [
                                    'h2 a span[title]', '.jobTitle a span', 'h2 a', 
                                    '.jobTitle', 'h3 a', '[data-testid*="title"]'
                                ]
                                job_title = self.extract_text_with_selectors(card, title_selectors)
                                
                                # Company extraction
                                company_selectors = [
                                    '.companyName a', '.companyName span', '.companyName',
                                    '[data-testid="company-name"]', '.company'
                                ]
                                company = self.extract_text_with_selectors(card, company_selectors)
                                
                                # Enhanced link extraction for Indeed
                                job_link = ""
                                
                                # Method 1: Standard link selectors
                                link_selectors = ['h2 a', '.jobTitle a', 'a[data-jk]', '.jobTitle-color-purple a']
                                job_link = self.extract_link_with_selectors(card, link_selectors, "https://in.indeed.com")
                                
                                # Method 2: Look for data-jk attribute to construct URL
                                if not job_link:
                                    data_jk = card.get('data-jk') or (card.find('[data-jk]') and card.find('[data-jk]').get('data-jk'))
                                    if data_jk:
                                        job_link = f"https://in.indeed.com/viewjob?jk={data_jk}"
                                
                                # Method 3: Find any Indeed job link in the card
                                if not job_link:
                                    all_links = card.find_all('a', href=True)
                                    for link in all_links:
                                        href = link.get('href', '')
                                        if '/viewjob' in href or '/clk' in href:
                                            if href.startswith('/'):
                                                job_link = "https://in.indeed.com" + href
                                            elif href.startswith('http'):
                                                job_link = href
                                            break
                                
                                # Location extraction
                                location_selectors = [
                                    '[data-testid="job-location"]', '.companyLocation', 
                                    '.locationsContainer', '[class*="location"]'
                                ]
                                job_location = self.extract_text_with_selectors(card, location_selectors, location)
                                
                                # Salary and date
                                salary_selectors = ['.salary-snippet', '.metadata', '.estimated-salary']
                                salary = self.extract_text_with_selectors(card, salary_selectors, "Not specified")
                                
                                date_selectors = ['.date', '[data-testid*="date"]', '.jobsearch-JobMetadataHeader-date']
                                posted_date = self.extract_text_with_selectors(card, date_selectors, "Recently")
                                
                                if job_title and company:
                                    jobs.append(Job(
                                        title=job_title,
                                        company=company,
                                        location=job_location,
                                        link=job_link,
                                        source="Indeed",
                                        salary=salary,
                                        posted_date=posted_date
                                    ))
                            except Exception as e:
                                continue
                        
                        if jobs:
                            break
                            
                    self.add_delay()
                    
                except Exception as e:
                    print(f"⚠️ Error with Indeed domain {base_url}: {e}")
                    continue
                    
        except Exception as e:
            print(f"⚠️ Indeed error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Indeed")
        return jobs

    def get_jobs_naukri(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Enhanced Naukri scraper"""
        print(f"🔍 Searching Naukri for {title} in {location}...")
        jobs = []
        
        try:
            # Try different URL patterns
            url_patterns = [
                f"https://www.naukri.com/{title.replace(' ', '-')}-jobs-in-{location.replace(' ', '-')}",
                f"https://www.naukri.com/jobs?q={quote(title)}&l={quote(location)}",
                f"https://www.naukri.com/{title.replace(' ', '-')}-jobs"
            ]
            
            for url in url_patterns:
                try:
                    self.session.headers['User-Agent'] = random.choice(self.user_agents)
                    response = self.session.get(url, timeout=15)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Multiple job listing selectors
                        listing_selectors = [
                            '.jobTuple',
                            '.srp-jobtuple-wrapper',
                            '.jobTupleContainer',
                            '[class*="jobTuple"]',
                            '.job-tuple'
                        ]
                        
                        job_listings = []
                        for selector in listing_selectors:
                            job_listings = soup.select(selector)[:max_results]
                            if job_listings:
                                print(f"✅ Found listings with selector: {selector}")
                                break
                        
                        for job_elem in job_listings:
                            try:
                                # Title extraction
                                title_selectors = [
                                    '.jobTupleHeader a', '.title a', '.job-title a',
                                    'h3 a', 'h2 a', '[class*="title"] a'
                                ]
                                job_title = self.extract_text_with_selectors(job_elem, title_selectors)
                                
                                # Enhanced link extraction for Naukri
                                job_link = ""
                                
                                # Method 1: Extract from title element
                                title_elem = self.get_element_with_selectors(job_elem, title_selectors)
                                if title_elem and title_elem.get('href'):
                                    href = title_elem['href']
                                    if href.startswith('/'):
                                        job_link = "https://www.naukri.com" + href
                                    elif href.startswith('http'):
                                        job_link = href
                                    else:
                                        job_link = "https://www.naukri.com/" + href
                                
                                # Method 2: Look for any job detail links
                                if not job_link:
                                    all_links = job_elem.find_all('a', href=True)
                                    for link in all_links:
                                        href = link.get('href', '')
                                        if any(keyword in href for keyword in ['/job-detail/', '/jobs/', '/job/', '-detail-']):
                                            if href.startswith('/'):
                                                job_link = "https://www.naukri.com" + href
                                            elif href.startswith('http'):
                                                job_link = href
                                            else:
                                                job_link = "https://www.naukri.com/" + href
                                            break
                                
                                # Company extraction
                                company_selectors = [
                                    '.companyInfo a', '.subTitle', '.company-name',
                                    '[class*="company"]', '.recruiter-name'
                                ]
                                company = self.extract_text_with_selectors(job_elem, company_selectors)
                                
                                # Location, salary, date extraction
                                location_selectors = ['.locationContainer', '.location', '[class*="location"]']
                                job_location = self.extract_text_with_selectors(job_elem, location_selectors, location)
                                
                                salary_selectors = ['.salary', '.salaryContainer', '[class*="salary"]']
                                salary = self.extract_text_with_selectors(job_elem, salary_selectors, "Not disclosed")
                                
                                date_selectors = ['.postedBy', '.jobPostDate', '[class*="date"]']
                                posted_date = self.extract_text_with_selectors(job_elem, date_selectors, "Recently")
                                
                                if job_title and company:
                                    jobs.append(Job(
                                        title=job_title,
                                        company=company,
                                        location=job_location,
                                        link=job_link,
                                        source="Naukri",
                                        salary=salary,
                                        posted_date=posted_date
                                    ))
                            except Exception as e:
                                continue
                        
                        if jobs:
                            break
                            
                    self.add_delay()
                    
                except Exception as e:
                    print(f"⚠️ Error with Naukri URL {url}: {e}")
                    continue
                    
        except Exception as e:
            print(f"⚠️ Naukri error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Naukri")
        return jobs

    def get_jobs_linkedin(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Enhanced LinkedIn scraper"""
        print(f"🔍 Searching LinkedIn for {title} in {location}...")
        jobs = []
        
        try:
            params = {
                'keywords': title,
                'location': location,
                'f_TPR': 'r86400',
                'sortBy': 'DD'
            }
            url = f"https://www.linkedin.com/jobs/search?{urlencode(params)}"
            
            self.session.headers['User-Agent'] = random.choice(self.user_agents)
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Multiple job card selectors
                card_selectors = [
                    '.job-search-card',
                    '.jobs-search__results-list li',
                    '.base-card',
                    '[class*="job-search"]'
                ]
                
                job_cards = []
                for selector in card_selectors:
                    job_cards = soup.select(selector)[:max_results]
                    if job_cards:
                        print(f"✅ Found LinkedIn cards with selector: {selector}")
                        break
                
                for card in job_cards:
                    try:
                        # Title extraction with multiple fallbacks
                        title_selectors = [
                            '.base-search-card__title a', 'h3 a', '.job-search-card__title a',
                            'h4 a', '[class*="title"] a'
                        ]
                        job_title = self.extract_text_with_selectors(card, title_selectors)
                        
                        # Enhanced link extraction for LinkedIn
                        job_link = ""
                        
                        # Method 1: Extract from title element
                        title_elem = self.get_element_with_selectors(card, title_selectors)
                        if title_elem and title_elem.get('href'):
                            href = title_elem['href']
                            if href.startswith('http'):
                                job_link = href
                            elif href.startswith('/'):
                                job_link = "https://www.linkedin.com" + href
                        
                        # Method 2: Look for any LinkedIn job links
                        if not job_link:
                            all_links = card.find_all('a', href=True)
                            for link in all_links:
                                href = link.get('href', '')
                                if '/jobs/view/' in href or '/jobs/' in href:
                                    if href.startswith('http'):
                                        job_link = href
                                    elif href.startswith('/'):
                                        job_link = "https://www.linkedin.com" + href
                                    break
                        
                        # Company extraction
                        company_selectors = [
                            '.base-search-card__subtitle a', '.job-search-card__subtitle',
                            '.base-search-card__subtitle', 'h4', '[class*="subtitle"]'
                        ]
                        company = self.extract_text_with_selectors(card, company_selectors)
                        
                        # Location extraction
                        location_selectors = [
                            '.job-search-card__location', '.base-search-card__metadata',
                            '[class*="location"]', '.job-search-card__location-text'
                        ]
                        job_location = self.extract_text_with_selectors(card, location_selectors, location)
                        
                        # Date extraction
                        date_selectors = ['time', '.job-search-card__listdate', '[datetime]']
                        posted_date = self.extract_text_with_selectors(card, date_selectors, "Recently")
                        
                        if job_title and company:
                            jobs.append(Job(
                                title=job_title,
                                company=company,
                                location=job_location,
                                link=job_link,
                                source="LinkedIn",
                                posted_date=posted_date
                            ))
                    except Exception as e:
                        continue
                        
        except Exception as e:
            print(f"⚠️ LinkedIn error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from LinkedIn")
        return jobs

    def get_jobs_remotive(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Enhanced Remotive scraper for remote jobs"""
        print(f"🔍 Searching Remotive for {title}...")
        jobs = []
        
        try:
            url = f"https://remotive.com/remote-jobs/search?search={quote(title)}"
            self.session.headers['User-Agent'] = random.choice(self.user_agents)
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                card_selectors = [
                    "article.job-tile",
                    ".job-listing",
                    "[class*='job-tile']",
                    ".job-card"
                ]
                
                job_cards = []
                for selector in card_selectors:
                    job_cards = soup.select(selector)[:max_results]
                    if job_cards:
                        break
                
                for card in job_cards:
                    try:
                        title_selectors = ["h2.job-tile-title", ".job-title", "h3", "h2"]
                        job_title = self.extract_text_with_selectors(card, title_selectors)
                        
                        company_selectors = ["span.company", ".company-name", ".company"]
                        company = self.extract_text_with_selectors(card, company_selectors)
                        
                        # Enhanced link extraction for Remotive
                        job_link = ""
                        link_elem = card.find("a", href=True)
                        if link_elem and link_elem.get('href'):
                            href = link_elem['href']
                            if href.startswith('http'):
                                job_link = href
                            elif href.startswith('/'):
                                job_link = "https://remotive.com" + href
                            else:
                                job_link = "https://remotive.com/" + href
                        
                        salary_selectors = ['.salary', '.compensation']
                        salary = self.extract_text_with_selectors(card, salary_selectors, "Not specified")
                        
                        if job_title and company:
                            jobs.append(Job(
                                title=job_title,
                                company=company,
                                location="Remote",
                                link=job_link,
                                source="Remotive",
                                salary=salary
                            ))
                    except Exception as e:
                        continue
                        
        except Exception as e:
            print(f"⚠️ Remotive error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Remotive")
        return jobs

    def get_jobs_weworkremotely(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Enhanced WeWorkRemotely scraper"""
        print(f"🔍 Searching WeWorkRemotely for {title}...")
        jobs = []
        
        try:
            url = f"https://weworkremotely.com/remote-jobs/search?term={quote(title)}"
            self.session.headers['User-Agent'] = random.choice(self.user_agents)
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                listing_selectors = [
                    "section.jobs li",
                    ".jobs-container li",
                    ".job-listing",
                    "li[class*='job']"
                ]
                
                job_listings = []
                for selector in listing_selectors:
                    job_listings = soup.select(selector)[:max_results]
                    if job_listings:
                        break
                
                for job_elem in job_listings:
                    try:
                        # Enhanced link extraction for WeWorkRemotely
                        anchor = job_elem.find("a", href=True)
                        job_link = ""
                        if anchor and anchor.get('href'):
                            href = anchor['href']
                            if href.startswith('http'):
                                job_link = href
                            elif href.startswith('/'):
                                job_link = "https://weworkremotely.com" + href
                            else:
                                job_link = "https://weworkremotely.com/" + href
                        
                        company_selectors = [".company", ".company-name"]
                        company = self.extract_text_with_selectors(job_elem, company_selectors)
                        
                        title_selectors = [".title", ".job-title", "h3", "h2"]
                        job_title = self.extract_text_with_selectors(job_elem, title_selectors)
                        
                        if job_title and company:
                            jobs.append(Job(
                                title=job_title,
                                company=company,
                                location="Remote",
                                link=job_link,
                                source="WeWorkRemotely"
                            ))
                    except Exception as e:
                        continue
                        
        except Exception as e:
            print(f"⚠️ WeWorkRemotely error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from WeWorkRemotely")
        return jobs

    def get_element_with_selectors(self, element, selectors: List[str]):
        """Get the first element that matches any of the selectors"""
        for selector in selectors:
            try:
                found_elem = element.select_one(selector)
                if found_elem:
                    return found_elem
            except Exception:
                continue
        return None

    def extract_text_with_selectors(self, element, selectors: List[str], default: str = "Unknown") -> str:
        """Try multiple selectors to extract text"""
        for selector in selectors:
            try:
                found_elem = element.select_one(selector)
                if found_elem:
                    # Handle title attribute or text content
                    text = found_elem.get('title') or found_elem.text.strip()
                    if text:
                        return text
            except Exception:
                continue
        return default

    def extract_link_with_selectors(self, element, selectors: List[str], base_url: str = "") -> str:
        """Try multiple selectors to extract links with better URL handling"""
        for selector in selectors:
            try:
                found_elem = element.select_one(selector)
                if found_elem and found_elem.get('href'):
                    href = found_elem['href'].strip()
                    
                    # Handle different URL formats
                    if href.startswith('http://') or href.startswith('https://'):
                        return href
                    elif href.startswith('/') and base_url:
                        return base_url + href
                    elif href and base_url:
                        return base_url + '/' + href
                    elif href:
                        return href
            except Exception:
                continue
        return ""

    def scrape_all_sites(self, title: str, location: str, max_results_per_site: int = 10) -> List[Job]:
        """Scrape all job sites with better error handling"""
        print(f"\n🚀 Starting job search for '{title}' in '{location}'...")
        print("=" * 60)
        
        scrapers = [
            ("Indeed", self.get_jobs_indeed),
            ("Naukri", self.get_jobs_naukri),
            ("Internshala", self.get_jobs_internshala),
            ("LinkedIn", self.get_jobs_linkedin),
            ("Remotive", self.get_jobs_remotive),
            ("WeWorkRemotely", self.get_jobs_weworkremotely)
        ]
        
        all_jobs = []
        
        # Sequential scraping with delays to avoid being blocked
        for scraper_name, scraper_func in scrapers:
            try:
                print(f"\n🌐 Starting {scraper_name}...")
                jobs = scraper_func(title, location, max_results_per_site)
                all_jobs.extend(jobs)
                
                # Add delay between scrapers
                if jobs:
                    print(f"✅ {scraper_name}: {len(jobs)} jobs found")
                else:
                    print(f"❌ {scraper_name}: No jobs found")
                    
                self.add_delay(2, 5)  # Longer delay between different sites
                
            except Exception as e:
                print(f"⚠️ {scraper_name} failed completely: {e}")
                continue
        
        # Remove duplicates
        unique_jobs = []
        seen = set()
        for job in all_jobs:
            identifier = (job.title.lower().strip(), job.company.lower().strip())
            if identifier not in seen and job.title.strip() and job.company.strip():
                seen.add(identifier)
                unique_jobs.append(job)
        
        print(f"\n📊 Total unique jobs found: {len(unique_jobs)}")
        return unique_jobs

    def filter_latest_jobs(self, jobs: List[Job], days: int = 7) -> List[Job]:
        """Filter jobs posted in the last N days"""
        if days == 0:
            return jobs
            
        keywords_recent = ['today', 'yesterday', 'hour', 'day', 'week', 'recent', 'new', 'ago', 'posted']
        
        filtered_jobs = []
        for job in jobs:
            posted_date_lower = job.posted_date.lower()
            
            # If posting date contains recent keywords, include it
            if any(keyword in posted_date_lower for keyword in keywords_recent):
                filtered_jobs.append(job)
            # If no specific date info, include it
            elif not posted_date_lower or posted_date_lower in ['recently', '', 'not specified']:
                filtered_jobs.append(job)
        
        return filtered_jobs

    def save_to_csv(self, jobs: List[Job], title: str, location: str):
        """Save jobs to CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"jobs_{title.replace(' ', '_')}_{location.replace(' ', '_')}_{timestamp}.csv"
        
        with open(filename, "w", newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Title", "Company", "Location", "Salary", "Posted Date", "Link", "Source"])
            
            for job in jobs:
                writer.writerow([
                    job.title, job.company, job.location, job.salary,
                    job.posted_date, job.link, job.source
                ])
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

    def save_to_json(self, jobs: List[Job], title: str, location: str):
        """Save jobs to JSON"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"jobs_{title.replace(' ', '_')}_{location.replace(' ', '_')}_{timestamp}.json"
        
        jobs_data = []
        for job in jobs:
            jobs_data.append({
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "salary": job.salary,
                "posted_date": job.posted_date,
                "link": job.link,
                "source": job.source,
                "scraped_at": datetime.now().isoformat()
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(jobs_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 JSON saved to: {filename}")
        return filename

    def display_results(self, jobs: List[Job]):
        """Display jobs in a formatted way"""
        print("\n" + "="*80)
        print("📋 JOB SEARCH RESULTS")
        print("="*80)
        
        if not jobs:
            print("❌ No jobs found matching your criteria.")
            print("\n💡 Suggestions:")
            print("   • Try different job titles (developer, engineer, analyst)")
            print("   • Use broader locations (mumbai, bangalore, delhi)")
            print("   • Set filter days to 0 to see all jobs")
            print("   • Check your internet connection")
            return
        
        # Group by source
        by_source = {}
        for job in jobs:
            if job.source not in by_source:
                by_source[job.source] = []
            by_source[job.source].append(job)
        
        for source, source_jobs in by_source.items():
            print(f"\n🌐 {source} ({len(source_jobs)} jobs)")
            print("-" * 50)
            
            for i, job in enumerate(source_jobs, 1):
                print(f"\n{i}. 🧑‍💼 {job.title}")
                print(f"   🏢 {job.company}")
                print(f"   📍 {job.location}")
                if job.salary and job.salary != "Not specified":
                    print(f"   💰 {job.salary}")
                if job.posted_date:
                    print(f"   📅 Posted: {job.posted_date}")
                print(f"   🔗 {job.link}")

def main():
    print("🚀 Enhanced Multi-Platform Job Scraper")
    print("=" * 50)
    
    # Configuration with better defaults
    TITLE = input("Enter job title (e.g., 'python developer', 'data analyst'): ").strip() or "python developer"
    LOCATION = input("Enter location (e.g., 'mumbai', 'delhi', 'bangalore'): ").strip() or "mumbai"
    MAX_RESULTS = int(input("Max results per site (5-20, default 10): ").strip() or "10")
    LATEST_DAYS = int(input("Filter jobs from last N days (0 for all, default 7): ").strip() or "7")
    
    # Validate inputs
    MAX_RESULTS = max(5, min(20, MAX_RESULTS))  # Limit between 5-20
    LATEST_DAYS = max(0, LATEST_DAYS)
    
    print(f"\n🎯 Configuration:")
    print(f"   Job Title: '{TITLE}'")
    print(f"   Location: '{LOCATION}'")
    print(f"   Max Results per Site: {MAX_RESULTS}")
    print(f"   Date Filter: {'All jobs' if LATEST_DAYS == 0 else f'Last {LATEST_DAYS} days'}")
    
    print(f"\n⚠️ Important Notes:")
    print(f"   • This scraper respects rate limits with delays")
    print(f"   • Some sites may block requests - this is normal")
    print(f"   • Results depend on site availability and structure")
    print(f"   • Remote job sites (Remotive, WeWorkRemotely) ignore location")
    
    # Initialize scraper
    scraper = JobScraper()
    
    # Scrape all sites
    print(f"\n🔄 Starting scraping process...")
    all_jobs = scraper.scrape_all_sites(TITLE, LOCATION, MAX_RESULTS)
    
    if not all_jobs:
        print(f"\n❌ No jobs found from any source!")
        print(f"💡 This could be due to:")
        print(f"   • Network connectivity issues")
        print(f"   • Sites blocking the requests")
        print(f"   • No matching jobs available")
        print(f"   • Site structure changes")
        return
    
    # Filter for latest jobs if requested
    if LATEST_DAYS > 0:
        print(f"\n🔍 Filtering for jobs from last {LATEST_DAYS} days...")
        latest_jobs = scraper.filter_latest_jobs(all_jobs, LATEST_DAYS)
        
        if latest_jobs:
            print(f"✅ Found {len(latest_jobs)} recent jobs out of {len(all_jobs)} total")
            jobs_to_display = latest_jobs
        else:
            print(f"⚠️ No recent jobs found, showing all {len(all_jobs)} jobs")
            jobs_to_display = all_jobs
    else:
        jobs_to_display = all_jobs
    
    # Display results
    scraper.display_results(jobs_to_display)
    
    # Save results
    if jobs_to_display:
        print(f"\n💾 Save Options:")
        save_choice = input("Save results? (csv/json/both/no) [csv]: ").strip().lower() or "csv"
        
        if save_choice in ['csv', 'both']:
            scraper.save_to_csv(jobs_to_display, TITLE, LOCATION)
        
        if save_choice in ['json', 'both']:
            scraper.save_to_json(jobs_to_display, TITLE, LOCATION)
    
    # Summary
    print(f"\n✅ Job search completed!")
    print(f"   📊 Total jobs found: {len(all_jobs)}")
    print(f"   📋 Jobs displayed: {len(jobs_to_display)}")
    
    if all_jobs:
        sources = {}
        for job in all_jobs:
            sources[job.source] = sources.get(job.source, 0) + 1
        
        print(f"   🌐 Jobs by source:")
        for source, count in sources.items():
            print(f"      • {source}: {count}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n⚠️ Scraping interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print(f"💡 Try running the script again or check your internet connection")
