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
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.jobs = []
        
    def get_jobs_internshala(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Scrape jobs from Internshala"""
        print(f"🔍 Searching Internshala for {title} in {location}...")
        jobs = []
        
        try:
            url = f"https://internshala.com/jobs/{title.replace(' ', '-')}-jobs-in-{location.replace(' ', '-')}"
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            listings = soup.select('.individual_internship')[:max_results]
            
            for job_elem in listings:
                try:
                    job_title = job_elem.select_one('div.heading_4_5, .profile h3').text.strip()
                    company = job_elem.select_one('a.link_display_like_text, .company-name').text.strip()
                    job_link = "https://internshala.com" + job_elem.select_one('a.view_detail_button, a[href*="/jobs/detail/"]')['href']
                    
                    # Try to extract salary and posting date
                    salary_elem = job_elem.select_one('.salary, .stipend')
                    salary = salary_elem.text.strip() if salary_elem else "Not specified"
                    
                    posted_elem = job_elem.select_one('.status-success, .date')
                    posted_date = posted_elem.text.strip() if posted_elem else "Recently"
                    
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
                    continue
                    
        except Exception as e:
            print(f"⚠️ Internshala error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Internshala")
        return jobs

    def get_jobs_indeed(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Scrape jobs from Indeed"""
        print(f"🔍 Searching Indeed for {title} in {location}...")
        jobs = []
        
        try:
            params = {
                'q': title,
                'l': location,
                'fromage': '7',  # Last 7 days
                'sort': 'date'
            }
            url = f"https://in.indeed.com/jobs?{urlencode(params)}"
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            job_cards = soup.select('[data-jk], .job_seen_beacon')[:max_results]
            
            for card in job_cards:
                try:
                    title_elem = card.select_one('h2 a span, .jobTitle a span')
                    if not title_elem:
                        continue
                        
                    job_title = title_elem.get('title', title_elem.text.strip())
                    
                    company_elem = card.select_one('.companyName a, .companyName span')
                    company = company_elem.text.strip() if company_elem else "Unknown"
                    
                    link_elem = card.select_one('h2 a, .jobTitle a')
                    job_link = "https://in.indeed.com" + link_elem['href'] if link_elem else ""
                    
                    location_elem = card.select_one('[data-testid="job-location"], .companyLocation')
                    job_location = location_elem.text.strip() if location_elem else location
                    
                    salary_elem = card.select_one('.salary-snippet, .metadata')
                    salary = salary_elem.text.strip() if salary_elem else "Not specified"
                    
                    date_elem = card.select_one('.date, [data-testid="myJobsStateDate"]')
                    posted_date = date_elem.text.strip() if date_elem else "Recently"
                    
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
                    
        except Exception as e:
            print(f"⚠️ Indeed error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Indeed")
        return jobs

    def get_jobs_naukri(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Scrape jobs from Naukri.com"""
        print(f"🔍 Searching Naukri for {title} in {location}...")
        jobs = []
        
        try:
            params = {
                'k': title,
                'l': location,
                'experience': '0',
                'sort': '1'  # Sort by relevance
            }
            url = f"https://www.naukri.com/jobs-in-{location.lower().replace(' ', '-')}?{urlencode({'k': title})}"
            
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            job_listings = soup.select('.jobTuple, .srp-jobtuple-wrapper')[:max_results]
            
            for job_elem in job_listings:
                try:
                    title_elem = job_elem.select_one('.jobTupleHeader a, .title')
                    if not title_elem:
                        continue
                        
                    job_title = title_elem.get('title', title_elem.text.strip())
                    job_link = title_elem.get('href', '')
                    if job_link and not job_link.startswith('http'):
                        job_link = 'https://www.naukri.com' + job_link
                    
                    company_elem = job_elem.select_one('.companyInfo a, .subTitle')
                    company = company_elem.text.strip() if company_elem else "Unknown"
                    
                    location_elem = job_elem.select_one('.locationContainer, .location')
                    job_location = location_elem.text.strip() if location_elem else location
                    
                    salary_elem = job_elem.select_one('.salary, .salaryContainer')
                    salary = salary_elem.text.strip() if salary_elem else "Not disclosed"
                    
                    date_elem = job_elem.select_one('.postedBy, .jobPostDate')
                    posted_date = date_elem.text.strip() if date_elem else "Recently"
                    
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
                    
        except Exception as e:
            print(f"⚠️ Naukri error: {e}")
        
        print(f"✅ Found {len(jobs)} jobs from Naukri")
        return jobs

    def get_jobs_linkedin(self, title: str, location: str, max_results: int = 10) -> List[Job]:
        """Scrape jobs from LinkedIn (public job search)"""
        print(f"🔍 Searching LinkedIn for {title} in {location}...")
        jobs = []
        
        try:
            # LinkedIn public job search URL
            params = {
                'keywords': title,
                'location': location,
                'f_TPR': 'r86400',  # Past 24 hours
                'sortBy': 'DD'  # Most recent
            }
            url = f"https://www.linkedin.com/jobs/search?{urlencode(params)}"
            
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            job_cards = soup.select('.job-search-card, .jobs-search__results-list li')[:max_results]
            
            for card in job_cards:
                try:
                    title_elem = card.select_one('.base-search-card__title, h3 a')
                    if not title_elem:
                        continue
                        
                    job_title = title_elem.text.strip()
                    job_link = title_elem.get('href', '') if title_elem.name == 'a' else card.select_one('a')['href']
                    
                    company_elem = card.select_one('.base-search-card__subtitle, .job-search-card__subtitle')
                    company = company_elem.text.strip() if company_elem else "Unknown"
                    
                    location_elem = card.select_one('.job-search-card__location, .base-search-card__metadata')
                    job_location = location_elem.text.strip() if location_elem else location
                    
                    date_elem = card.select_one('time, .job-search-card__listdate')
                    posted_date = date_elem.get('datetime', date_elem.text.strip()) if date_elem else "Recently"
                    
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
        """Enhanced Remotive scraper"""
        print(f"🔍 Searching Remotive for {title}...")
        jobs = []
        
        try:
            url = f"https://remotive.com/remote-jobs/search?search={quote(title)}"
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            job_cards = soup.select("article.job-tile")[:max_results]
            
            for card in job_cards:
                try:
                    title_elem = card.select_one("h2.job-tile-title, .job-title")
                    job_title = title_elem.text.strip() if title_elem else "Unknown"
                    
                    company_elem = card.select_one("span.company, .company-name")
                    company = company_elem.text.strip() if company_elem else "Unknown"
                    
                    link_elem = card.find("a")
                    job_link = "https://remotive.com" + link_elem["href"] if link_elem else ""
                    
                    salary_elem = card.select_one('.salary, .compensation')
                    salary = salary_elem.text.strip() if salary_elem else "Not specified"
                    
                    # Check if location matches or it's remote
                    description = card.text.lower()
                    is_relevant = location.lower() in description or "remote" in description
                    
                    if is_relevant:
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
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            job_listings = soup.select("section.jobs li, .jobs-container li")[:max_results]
            
            for job_elem in job_listings:
                try:
                    anchor = job_elem.find("a", href=True)
                    if not anchor:
                        continue
                        
                    job_link = "https://weworkremotely.com" + anchor["href"]
                    
                    company_elem = job_elem.select_one(".company")
                    company = company_elem.text.strip() if company_elem else "Unknown"
                    
                    title_elem = job_elem.select_one(".title")
                    job_title = title_elem.text.strip() if title_elem else "Unknown"
                    
                    # Check relevance
                    description = job_elem.text.lower()
                    is_relevant = location.lower() in description or any(keyword in title.lower() for keyword in title.lower().split())
                    
                    if is_relevant:
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

    def scrape_all_sites(self, title: str, location: str, max_results_per_site: int = 10) -> List[Job]:
        """Scrape all job sites concurrently"""
        print(f"\n🚀 Starting job search for '{title}' in '{location}'...")
        print("=" * 60)
        
        scrapers = [
            self.get_jobs_indeed,
            self.get_jobs_naukri,
            self.get_jobs_internshala,
            self.get_jobs_linkedin,
            self.get_jobs_remotive,
            self.get_jobs_weworkremotely
        ]
        
        all_jobs = []
        
        # Use ThreadPoolExecutor for concurrent scraping
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_scraper = {
                executor.submit(scraper, title, location, max_results_per_site): scraper.__name__ 
                for scraper in scrapers
            }
            
            for future in concurrent.futures.as_completed(future_to_scraper):
                try:
                    jobs = future.result(timeout=30)
                    all_jobs.extend(jobs)
                except Exception as e:
                    scraper_name = future_to_scraper[future]
                    print(f"⚠️ {scraper_name} failed: {e}")
        
        # Remove duplicates based on title and company
        unique_jobs = []
        seen = set()
        for job in all_jobs:
            identifier = (job.title.lower(), job.company.lower())
            if identifier not in seen:
                seen.add(identifier)
                unique_jobs.append(job)
        
        print(f"\n📊 Total unique jobs found: {len(unique_jobs)}")
        return unique_jobs

    def filter_latest_jobs(self, jobs: List[Job], days: int = 7) -> List[Job]:
        """Filter jobs posted in the last N days"""
        keywords_recent = ['today', 'yesterday', 'hour', 'day', 'week', 'recent', 'new', 'ago', 'posted']
        
        filtered_jobs = []
        for job in jobs:
            posted_date_lower = job.posted_date.lower()
            
            # Debug: Print what we're filtering
            print(f"🔍 Checking job: {job.title[:30]}... | Posted: '{job.posted_date}' | Source: {job.source}")
            
            # If posting date contains recent keywords, include it
            if any(keyword in posted_date_lower for keyword in keywords_recent):
                print(f"✅ Included (recent keyword found)")
                filtered_jobs.append(job)
            # If no specific date info, include it (better to have false positives)
            elif not posted_date_lower or posted_date_lower in ['recently', '', 'not specified']:
                print(f"✅ Included (no date info)")
                filtered_jobs.append(job)
            # If days filter is disabled (0), include all jobs
            elif days == 0:
                print(f"✅ Included (no date filter)")
                filtered_jobs.append(job)
            else:
                print(f"❌ Excluded")
        
        return filtered_jobs

    def save_to_csv(self, jobs: List[Job], title: str, location: str):
        """Save jobs to CSV with enhanced format"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"jobs_{title.replace(' ', '_')}_{location.replace(' ', '_')}_{timestamp}.csv"
        
        with open(filename, "w", newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Title", "Company", "Location", "Salary", "Posted Date", "Link", "Source"])
            
            for job in jobs:
                writer.writerow([
                    job.title, 
                    job.company, 
                    job.location, 
                    job.salary,
                    job.posted_date,
                    job.link, 
                    job.source
                ])
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

    def save_to_json(self, jobs: List[Job], title: str, location: str):
        """Save jobs to JSON format"""
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
            print("\n💡 Try:")
            print("   • Set filter days to 0 to see all jobs")
            print("   • Check spelling of job title")
            print("   • Try different location (bangalore, mumbai, delhi)")
            print("   • Use broader job title (developer, engineer)")
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
    # Configuration
    TITLE = input("Enter job title (e.g., 'frontend developer', 'python developer'): ").strip() or "frontend developer"
    LOCATION = input("Enter location (e.g., 'mumbai', 'delhi', 'bangalore'): ").strip() or "mumbai"
    MAX_RESULTS = int(input("Max results per site (default 10): ").strip() or "10")
    LATEST_DAYS = int(input("Filter jobs from last N days (0 for all jobs, default 7): ").strip() or "7")
    
    print(f"\n🎯 Searching for: '{TITLE}' in '{LOCATION}'")
    print(f"📊 Max results per site: {MAX_RESULTS}")
    if LATEST_DAYS == 0:
        print(f"📅 Showing ALL jobs (no date filter)")
    else:
        print(f"📅 Latest jobs from last {LATEST_DAYS} days")
    
    # Initialize scraper
    scraper = JobScraper()
    
    # Scrape all sites
    all_jobs = scraper.scrape_all_sites(TITLE, LOCATION, MAX_RESULTS)
    
    # Show all jobs first for debugging
    print(f"\n📋 All jobs found (before filtering): {len(all_jobs)}")
    if all_jobs and LATEST_DAYS > 0:
        print("🔍 Filtering for latest jobs...")
        
    # Filter for latest jobs
    latest_jobs = scraper.filter_latest_jobs(all_jobs, LATEST_DAYS)
    
    if LATEST_DAYS == 0:
        print(f"\n📊 Total jobs (no filter): {len(latest_jobs)}")
    else:
        print(f"\n🔥 Latest jobs (last {LATEST_DAYS} days): {len(latest_jobs)}")
    
    # If no latest jobs found but we have all jobs, show all jobs
    jobs_to_display = latest_jobs if latest_jobs else all_jobs
    
    if not latest_jobs and all_jobs:
        print(f"\n⚠️ No jobs matched date filter, showing all {len(all_jobs)} jobs found:")
        jobs_to_display = all_jobs
    
    # Display results
    scraper.display_results(jobs_to_display)
    
    # Save results
    if jobs_to_display:
        save_choice = input("\n💾 Save results? (csv/json/both/no) [csv]: ").strip().lower() or "csv"
        
        if save_choice in ['csv', 'both']:
            scraper.save_to_csv(jobs_to_display, TITLE, LOCATION)
        
        if save_choice in ['json', 'both']:
            scraper.save_to_json(jobs_to_display, TITLE, LOCATION)
    
    print(f"\n✅ Job search completed! Displayed {len(jobs_to_display)} jobs.")

if __name__ == "__main__":
    main()
