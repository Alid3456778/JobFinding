"""
Multi-Platform Job Scraper
==========================
Confirmed working platforms (as of April 2025):

  API-based (most reliable — no scraping, pure JSON):
    - RemoteOK       https://remoteok.com/api
    - Arbeitnow      https://www.arbeitnow.com/api/job-board-api
    - The Muse       https://www.themuse.com/api/public/jobs
    - Himalayas      https://himalayas.app/jobs/api/search  (free, no auth)
    - Jobicy         https://jobicy.com/api/v2/remote-jobs  (free, no auth)

  Scraping-based (HTML parsing — may break if sites update their markup):
    - LinkedIn       https://www.linkedin.com/jobs/search
    - Internshala    https://internshala.com/jobs/  (updated selectors)

Platforms intentionally NOT included:
    - Indeed   — heavily blocks automated requests (CAPTCHA / 403)
    - Naukri   — JS-rendered SPA; no data in static HTML
    - Findwork — requires API key
    - Adzuna   — requires app_id + app_key registration
"""

import csv
import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from typing import Callable, Dict, List, Optional
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class JobScraper:
    # ---- Platform metadata ------------------------------------------------

    PLATFORM_LABELS: Dict[str, str] = {
        "linkedin":    "LinkedIn",
        "internshala": "Internshala",
        "remoteok":    "RemoteOK",
        "arbeitnow":   "Arbeitnow",
        "themuse":     "The Muse",
        "himalayas":   "Himalayas",
        "jobicy":      "Jobicy",
    }

    # Default set — all confirmed working, no API key required
    DEFAULT_PLATFORMS: List[str] = [
        "linkedin",
        "internshala",
        "remoteok",
        "arbeitnow",
        "themuse",
        "himalayas",
        "jobicy",
    ]

    # ---- Browser-like headers used for HTML scraping ----------------------

    _USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0",
    ]

    # ---- Construction -----------------------------------------------------

    def __init__(self) -> None:
        self.session = requests.Session()
        self._refresh_headers()
        self.platform_scrapers: Dict[str, Callable[[str, str, int], List[Job]]] = {
            "linkedin":    self.get_jobs_linkedin,
            "internshala": self.get_jobs_internshala,
            "remoteok":    self.get_jobs_remoteok,
            "arbeitnow":   self.get_jobs_arbeitnow,
            "themuse":     self.get_jobs_themuse,
            "himalayas":   self.get_jobs_himalayas,
            "jobicy":      self.get_jobs_jobicy,
        }
        self.last_run_statuses: List[Dict[str, str]] = []

    def _refresh_headers(self) -> None:
        self.session.headers.update(
            {
                "User-Agent": random.choice(self._USER_AGENTS),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    # ---- Platform options (for UI / CLI menus) ----------------------------

    @classmethod
    def get_platform_options(cls) -> List[Dict[str, str]]:
        options = [{"value": "all", "label": "All Platforms"}]
        for key in cls.DEFAULT_PLATFORMS:
            options.append({"value": key, "label": cls.PLATFORM_LABELS[key]})
        return options

    # ---- Low-level HTTP helpers -------------------------------------------

    def _add_delay(self, min_s: float = 0.8, max_s: float = 2.0) -> None:
        time.sleep(random.uniform(min_s, max_s))

    def _request_page(
        self,
        url: str,
        params: Optional[dict] = None,
        timeout: int = 15,
        extra_headers: Optional[dict] = None,
    ) -> Optional[requests.Response]:
        """GET a URL, rotating the User-Agent each call."""
        try:
            self.session.headers["User-Agent"] = random.choice(self._USER_AGENTS)
            headers = dict(self.session.headers)
            if extra_headers:
                headers.update(extra_headers)
            return self.session.get(
                url, params=params, timeout=timeout, headers=headers
            )
        except requests.RequestException as exc:
            print(f"  [warn] request failed for {url!r}: {exc}")
            return None

    def _request_json(
        self,
        url: str,
        params: Optional[dict] = None,
        timeout: int = 15,
        extra_headers: Optional[dict] = None,
    ):
        """GET a URL and parse the response as JSON. Returns None on failure."""
        resp = self._request_page(
            url, params=params, timeout=timeout, extra_headers=extra_headers
        )
        if resp is None:
            return None
        if resp.status_code >= 400:
            print(f"  [warn] {url} returned HTTP {resp.status_code}")
            return None
        try:
            return resp.json()
        except ValueError:
            print(f"  [warn] {url} did not return valid JSON")
            return None

    # ---- Text / HTML helpers ---------------------------------------------

    def _clean(self, value: str) -> str:
        """Strip HTML tags, unescape entities, collapse whitespace."""
        text = BeautifulSoup(unescape(value or ""), "html.parser").get_text(
            " ", strip=True
        )
        return re.sub(r"\s+", " ", text).strip()

    def _tokens_match(self, query: str, text: str) -> bool:
        """Return True if the first 3 meaningful query tokens appear in text."""
        tokens = [t for t in re.split(r"\W+", query.lower()) if t][:3]
        haystack = self._clean(text).lower()
        return all(tok in haystack for tok in tokens) if tokens else True

    def _location_match(self, requested: str, job_location: str) -> bool:
        if not requested:
            return True
        loc_text = self._clean(job_location).lower()
        req = self._clean(requested).lower()
        if req in {"remote", "any", "worldwide"}:
            return "remote" in loc_text or "worldwide" in loc_text
        return req in loc_text or "remote" in loc_text

    def _abs_url(self, href: str, base: str = "") -> str:
        href = (href or "").strip()
        if not href:
            return ""
        if href.startswith(("http://", "https://")):
            return href
        if href.startswith("//"):
            return f"https:{href}"
        if href.startswith("/"):
            return f"{base}{href}" if base else href
        return f"{base}/{href}" if base else href

    def _sel_text(
        self,
        elem,
        selectors: List[str],
        default: str = "",
    ) -> str:
        for sel in selectors:
            try:
                found = elem.select_one(sel)
                if not found:
                    continue
                text = (
                    found.get("title")
                    or found.get("aria-label")
                    or found.get_text(" ", strip=True)
                )
                text = self._clean(text)
                if text:
                    return text
            except Exception:
                continue
        return default

    def _sel_href(
        self,
        elem,
        selectors: List[str],
        base: str = "",
    ) -> str:
        for sel in selectors:
            try:
                found = elem.select_one(sel)
                if found and found.get("href"):
                    return self._abs_url(found["href"], base)
            except Exception:
                continue
        return ""

    # =========================================================================
    # PLATFORM SCRAPERS
    # =========================================================================

    # ---- LinkedIn -----------------------------------------------------------

    def get_jobs_linkedin(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching LinkedIn for '{title}' in '{location}'...")
        jobs: List[Job] = []

        params = {"keywords": title, "location": location, "sortBy": "DD"}
        resp = self._request_page(
            f"https://www.linkedin.com/jobs/search?{urlencode(params)}"
        )
        if not resp or resp.status_code != 200:
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = []
        for sel in [
            ".jobs-search__results-list li",
            ".job-search-card",
            ".base-card",
        ]:
            cards = soup.select(sel)
            if cards:
                break

        for card in cards[:max_results]:
            job_title = self._sel_text(
                card,
                [
                    "h3.base-search-card__title",
                    ".base-search-card__title",
                    ".job-search-card__title",
                    "h3",
                ],
            )
            company = self._sel_text(
                card,
                [
                    ".base-search-card__subtitle",
                    ".job-search-card__subtitle",
                    "h4",
                ],
            )
            job_loc = self._sel_text(
                card,
                [
                    ".job-search-card__location",
                    ".base-search-card__metadata",
                ],
                default=location,
            )
            posted = self._sel_text(
                card,
                ["time", ".job-search-card__listdate"],
                default="Recently",
            )
            link = self._sel_href(
                card,
                [
                    "a.base-card__full-link",
                    "a[href*='/jobs/view/']",
                    "a[href*='/jobs/collections/']",
                ],
                "https://www.linkedin.com",
            )

            if job_title and company:
                jobs.append(
                    Job(
                        title=job_title,
                        company=company,
                        location=job_loc,
                        link=link,
                        source=self.PLATFORM_LABELS["linkedin"],
                        posted_date=posted,
                    )
                )

        print(f"  LinkedIn → {len(jobs)} job(s)")
        return jobs

    # ---- Internshala --------------------------------------------------------
    # Internshala updated their markup in early 2025.
    # The jobs listing page renders most cards via server-side HTML, but the
    # CSS class names changed. We now try a wider range of selectors and
    # multiple URL patterns so the scraper degrades gracefully if Internshala
    # updates again.

    def get_jobs_internshala(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching Internshala for '{title}' in '{location}'...")
        jobs: List[Job] = []

        slug_title = title.lower().replace(" ", "-")
        slug_loc = location.lower().replace(" ", "-")

        # Multiple URL patterns — Internshala has changed URL format before
        urls = [
            # Pattern 1: keyword-in-city slug (most common, post-2024)
            f"https://internshala.com/jobs/{slug_title}-jobs-in-{slug_loc}",
            # Pattern 2: keyword only
            f"https://internshala.com/jobs/{slug_title}-jobs",
            # Pattern 3: fresher-jobs sub-section
            f"https://internshala.com/fresher-jobs/{slug_title}-jobs",
            # Pattern 4: query-string style (legacy)
            (
                "https://internshala.com/jobs/keyword-"
                f"{quote(title)}/location-{quote(location)}"
            ),
        ]

        # Selectors tried in order — covers old markup + 2024/2025 redesign
        card_selectors = [
            # 2024-2025 redesign
            ".individual_internship",
            "[data-internship-id]",
            "[data-job-id]",
            ".job-internship-card",
            ".internship-card",
            # older markup still seen on some listing types
            ".internship_meta",
            ".container_type .individual_internship",
            "#internship_list_container .individual_internship",
            # very broad fallback
            ".jobs_new_jobs_container article",
            "article.job",
        ]

        for url in urls:
            resp = self._request_page(
                url,
                extra_headers={
                    "Referer": "https://internshala.com/jobs/",
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/webp,*/*;q=0.8"
                    ),
                },
            )
            if not resp or resp.status_code != 200:
                self._add_delay(0.5, 1.2)
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            listings: list = []
            for sel in card_selectors:
                listings = soup.select(sel)
                if listings:
                    break

            if not listings:
                self._add_delay(0.5, 1.2)
                continue  # Try next URL pattern

            for item in listings[:max_results]:
                job_title = self._sel_text(
                    item,
                    [
                        # 2025 class names
                        ".job-title-text",
                        "h3.job-title",
                        ".title",
                        # 2024 class names
                        "div.heading_4_5",
                        ".profile h3",
                        ".job-internship-name",
                        # older
                        ".profile",
                        "h3",
                    ],
                )
                company = self._sel_text(
                    item,
                    [
                        # 2025
                        ".company-name",
                        ".company_name",
                        # 2024
                        "a.link_display_like_text",
                        ".company",
                        # generic
                        "[class*='company']",
                    ],
                )
                salary = self._sel_text(
                    item,
                    [".salary", ".stipend", ".compensation", "[class*='salary']"],
                    default="Not specified",
                )
                posted = self._sel_text(
                    item,
                    [
                        ".status-success",
                        ".posted-date",
                        ".date",
                        "time",
                        "[class*='date']",
                    ],
                    default="Recently",
                )
                link = self._sel_href(
                    item,
                    [
                        "a.view_detail_button",
                        "a[href*='/jobs/detail/']",
                        "a[href*='/internship/detail/']",
                        "a[href*='/job/']",
                        "a[href*='/internship/']",
                        "a",
                    ],
                    "https://internshala.com",
                )

                if job_title and company:
                    jobs.append(
                        Job(
                            title=job_title,
                            company=company,
                            location=location.title(),
                            link=link,
                            source=self.PLATFORM_LABELS["internshala"],
                            posted_date=posted,
                            salary=salary,
                        )
                    )

            if jobs:
                break  # Found results; no need to try the next URL pattern

            self._add_delay()

        if not jobs:
            print(
                "  [info] Internshala returned 0 results. "
                "The site may have updated its markup. "
                "Check https://internshala.com/jobs manually."
            )
        else:
            print(f"  Internshala → {len(jobs)} job(s)")
        return jobs

    # ---- RemoteOK -----------------------------------------------------------

    def get_jobs_remoteok(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching RemoteOK for '{title}'...")
        jobs: List[Job] = []

        data = self._request_json(
            "https://remoteok.com/api",
            extra_headers={"Accept": "application/json"},
        )
        if not isinstance(data, list):
            return jobs

        for item in data:
            if not isinstance(item, dict) or "position" not in item:
                continue
            job_title = self._clean(item.get("position", ""))
            company   = self._clean(item.get("company", ""))
            job_loc   = self._clean(item.get("location", "Remote")) or "Remote"

            if not self._tokens_match(title, job_title):
                continue
            if (
                location
                and location.lower() != "remote"
                and not self._location_match(location, job_loc)
            ):
                continue

            s_min = item.get("salary_min") or 0
            s_max = item.get("salary_max") or 0
            salary = f"{s_min} - {s_max}" if (s_min or s_max) else "Not specified"

            jobs.append(
                Job(
                    title=job_title,
                    company=company or "Unknown",
                    location=job_loc,
                    link=item.get("apply_url") or item.get("url") or "",
                    source=self.PLATFORM_LABELS["remoteok"],
                    posted_date=self._clean(item.get("date", "")),
                    salary=salary,
                    description=self._clean(item.get("description", "")),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"  RemoteOK → {len(jobs)} job(s)")
        return jobs

    # ---- Arbeitnow ----------------------------------------------------------

    def get_jobs_arbeitnow(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching Arbeitnow for '{title}'...")
        jobs: List[Job] = []

        data = self._request_json("https://www.arbeitnow.com/api/job-board-api")
        if not isinstance(data, dict):
            return jobs

        for item in data.get("data", []):
            job_title = self._clean(item.get("title", ""))
            company   = self._clean(item.get("company_name", ""))
            job_loc   = self._clean(item.get("location", "Remote")) or "Remote"
            is_remote = bool(item.get("remote"))

            if not self._tokens_match(title, job_title):
                continue
            if not is_remote and not self._location_match(location, job_loc):
                continue

            jobs.append(
                Job(
                    title=job_title,
                    company=company or "Unknown",
                    location="Remote" if is_remote else job_loc,
                    link=item.get("url", ""),
                    source=self.PLATFORM_LABELS["arbeitnow"],
                    posted_date=str(item.get("created_at", "")),
                    description=self._clean(item.get("description", "")),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"  Arbeitnow → {len(jobs)} job(s)")
        return jobs

    # ---- The Muse -----------------------------------------------------------

    def get_jobs_themuse(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching The Muse for '{title}'...")
        jobs: List[Job] = []

        for page in range(1, 5):
            data = self._request_json(
                "https://www.themuse.com/api/public/jobs",
                params={"page": page},
            )
            if not isinstance(data, dict):
                break

            for item in data.get("results", []):
                job_title = self._clean(item.get("name", ""))
                company   = self._clean(item.get("company", {}).get("name", ""))
                locs      = [
                    self._clean(loc.get("name", ""))
                    for loc in item.get("locations", [])
                    if loc.get("name")
                ]
                job_loc = ", ".join(locs) or "Remote"

                if not self._tokens_match(title, job_title):
                    continue
                if (
                    location
                    and location.lower() != "remote"
                    and not self._location_match(location, job_loc)
                ):
                    continue

                jobs.append(
                    Job(
                        title=job_title,
                        company=company or "Unknown",
                        location=job_loc,
                        link=item.get("refs", {}).get("landing_page", ""),
                        source=self.PLATFORM_LABELS["themuse"],
                        posted_date=self._clean(item.get("publication_date", "")),
                        description=self._clean(item.get("contents", "")),
                    )
                )
                if len(jobs) >= max_results:
                    break

            if len(jobs) >= max_results:
                break

        print(f"  The Muse → {len(jobs)} job(s)")
        return jobs

    # ---- Himalayas ----------------------------------------------------------
    # Free public JSON API — no authentication required.
    # Endpoint: https://himalayas.app/jobs/api/search
    # Docs:     https://himalayas.app/docs/remote-jobs-api

    def get_jobs_himalayas(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching Himalayas for '{title}'...")
        jobs: List[Job] = []

        params: Dict = {"q": title, "limit": min(max_results, 20)}
        # Map common location shorthands to country names the API understands
        loc_lower = location.lower().strip()
        if loc_lower not in {"remote", "any", "worldwide", ""}:
            params["country"] = location

        data = self._request_json(
            "https://himalayas.app/jobs/api/search",
            params=params,
            extra_headers={"Accept": "application/json"},
        )
        if not isinstance(data, dict):
            return jobs

        for item in data.get("jobs", []):
            job_title = self._clean(item.get("title", ""))
            company   = self._clean(item.get("companyName", ""))

            loc_restrictions = item.get("locationRestrictions") or []
            job_loc = ", ".join(loc_restrictions) if loc_restrictions else "Remote"

            s_min = item.get("minSalary")
            s_max = item.get("maxSalary")
            currency = item.get("currency", "USD")
            salary = ""
            if s_min and s_max:
                salary = f"{currency} {s_min:,} – {s_max:,}"
            elif s_min:
                salary = f"{currency} {s_min:,}+"

            jobs.append(
                Job(
                    title=job_title,
                    company=company or "Unknown",
                    location=job_loc,
                    link=item.get("applicationLink") or item.get("url") or "",
                    source=self.PLATFORM_LABELS["himalayas"],
                    posted_date=self._clean(str(item.get("publishedAt", ""))),
                    salary=salary or "Not specified",
                    description=self._clean(item.get("excerpt", "")),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"  Himalayas → {len(jobs)} job(s)")
        return jobs

    # ---- Jobicy -------------------------------------------------------------
    # Free public JSON API — no authentication required.
    # Endpoint: https://jobicy.com/api/v2/remote-jobs
    # Docs:     https://jobicy.com/jobs-rss-feed

    def get_jobs_jobicy(
        self, title: str, location: str, max_results: int = 10
    ) -> List[Job]:
        print(f"  Searching Jobicy for '{title}'...")
        jobs: List[Job] = []

        params: Dict = {
            "count": min(max_results, 50),
            "tag": title,   # searches job title + description
        }
        loc_lower = location.lower().strip()
        if loc_lower not in {"remote", "any", "worldwide", ""}:
            # Jobicy 'geo' accepts country names like 'india', 'usa', 'uk'
            params["geo"] = loc_lower

        data = self._request_json(
            "https://jobicy.com/api/v2/remote-jobs",
            params=params,
            extra_headers={"Accept": "application/json"},
        )
        if not isinstance(data, dict):
            return jobs

        for item in data.get("jobs", []):
            job_title = self._clean(item.get("jobTitle", ""))
            company   = self._clean(item.get("companyName", ""))
            job_loc   = self._clean(item.get("jobGeo", "Anywhere")) or "Remote"

            s_min      = item.get("salaryMin") or item.get("annualSalaryMin")
            s_max      = item.get("salaryMax") or item.get("annualSalaryMax")
            currency   = item.get("salaryCurrency", "USD")
            salary_period = item.get("salaryPeriod", "")
            salary = ""
            if s_min and s_max:
                salary = f"{currency} {s_min} – {s_max} / {salary_period}"
            elif s_min:
                salary = f"{currency} {s_min}+ / {salary_period}"

            jobs.append(
                Job(
                    title=job_title,
                    company=company or "Unknown",
                    location=job_loc,
                    link=item.get("url", ""),
                    source=self.PLATFORM_LABELS["jobicy"],
                    posted_date=self._clean(str(item.get("pubDate", ""))),
                    salary=salary or "Not specified",
                    description=self._clean(item.get("jobExcerpt", "")),
                )
            )
            if len(jobs) >= max_results:
                break

        print(f"  Jobicy → {len(jobs)} job(s)")
        return jobs

    # =========================================================================
    # Orchestration
    # =========================================================================

    def resolve_platforms(self, platforms: Optional[List[str]]) -> List[str]:
        if not platforms:
            return list(self.DEFAULT_PLATFORMS)
        cleaned: List[str] = []
        for p in platforms:
            key = (p or "").strip().lower()
            if key == "all":
                return list(self.DEFAULT_PLATFORMS)
            if key in self.platform_scrapers and key not in cleaned:
                cleaned.append(key)
        return cleaned or list(self.DEFAULT_PLATFORMS)

    def scrape_all_sites(
        self,
        title: str,
        location: str,
        max_results_per_site: int = 10,
        platforms: Optional[List[str]] = None,
    ) -> List[Job]:
        selected = self.resolve_platforms(platforms)
        print(f"\nJob search: '{title}' in '{location}'")
        print("=" * 60)
        print(
            "Platforms: "
            + ", ".join(self.PLATFORM_LABELS[k] for k in selected)
        )
        print("=" * 60)

        all_jobs: List[Job] = []
        self.last_run_statuses = []

        for key in selected:
            scraper_fn = self.platform_scrapers[key]
            label = self.PLATFORM_LABELS[key]
            try:
                results = scraper_fn(title, location, max_results_per_site)
                all_jobs.extend(results)
                self.last_run_statuses.append(
                    {
                        "key": key,
                        "label": label,
                        "status": "success" if results else "empty",
                        "count": str(len(results)),
                    }
                )
            except Exception as exc:
                print(f"  [error] {label} failed: {exc}")
                self.last_run_statuses.append(
                    {"key": key, "label": label, "status": "error", "count": "0"}
                )
            self._add_delay()

        # De-duplicate by (normalised title, company, location) key
        unique: List[Job] = []
        seen: set = set()
        for job in all_jobs:
            k = (
                self._clean(job.title).lower(),
                self._clean(job.company).lower(),
                self._clean(job.location).lower(),
            )
            if k[0] and k[1] and k not in seen:
                seen.add(k)
                unique.append(job)

        print(f"\nTotal unique jobs found: {len(unique)}")
        return unique

    # ---- Filtering ----------------------------------------------------------

    def filter_latest_jobs(self, jobs: List[Job], days: int = 7) -> List[Job]:
        """
        Heuristic filter: keep jobs whose posted_date string contains recency
        keywords, since date formats vary wildly across platforms.
        Pass days=0 to skip filtering entirely.
        """
        if days <= 0:
            return jobs
        recent_kw = [
            "today", "yesterday", "hour", "day", "week",
            "recent", "new", "ago", "posted", "just",
        ]
        return [
            job for job in jobs
            if not job.posted_date
            or any(kw in self._clean(job.posted_date).lower() for kw in recent_kw)
        ]

    # ---- Export helpers -----------------------------------------------------

    def save_to_csv(self, jobs: List[Job], title: str, location: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"jobs_{title.replace(' ', '_')}"
            f"_{location.replace(' ', '_')}_{ts}.csv"
        )
        with open(filename, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["Title", "Company", "Location", "Salary", "Posted Date", "Link", "Source"]
            )
            for job in jobs:
                writer.writerow(
                    [
                        job.title, job.company, job.location,
                        job.salary, job.posted_date, job.link, job.source,
                    ]
                )
        print(f"Saved CSV → {filename}")
        return filename

    def save_to_json(self, jobs: List[Job], title: str, location: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"jobs_{title.replace(' ', '_')}"
            f"_{location.replace(' ', '_')}_{ts}.json"
        )
        payload = [
            {
                "title":       job.title,
                "company":     job.company,
                "location":    job.location,
                "salary":      job.salary,
                "posted_date": job.posted_date,
                "link":        job.link,
                "source":      job.source,
                "scraped_at":  datetime.now().isoformat(),
            }
            for job in jobs
        ]
        with open(filename, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"Saved JSON → {filename}")
        return filename


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    print("Multi-Platform Job Scraper")
    print("=" * 50)

    title       = input("Enter job title (e.g. python developer): ").strip() or "python developer"
    location    = input("Enter location (e.g. India, remote):    ").strip() or "remote"
    max_results = int(input("Max results per site [default 10]: ").strip() or "10")
    latest_days = int(
        input("Filter jobs from last N days (0 = show all) [default 7]: ").strip() or "7"
    )

    scraper   = JobScraper()
    all_jobs  = scraper.scrape_all_sites(title, location, max_results)
    to_display = (
        scraper.filter_latest_jobs(all_jobs, latest_days)
        if latest_days > 0
        else all_jobs
    )

    print(f"\n{'='*60}")
    print(f"Jobs found: {len(to_display)}")
    print(f"{'='*60}")
    for job in to_display:
        salary_str = f" | {job.salary}" if job.salary and job.salary != "Not specified" else ""
        print(
            f"  [{job.source}] {job.title} @ {job.company}"
            f" | {job.location}{salary_str}"
        )

    if to_display:
        save = input("\nSave results? [csv / json / both / no]: ").strip().lower()
        if save in {"csv", "both"}:
            scraper.save_to_csv(to_display, title, location)
        if save in {"json", "both"}:
            scraper.save_to_json(to_display, title, location)

    # Print per-platform status summary
    print("\n--- Platform summary ---")
    for st in scraper.last_run_statuses:
        icon = {"success": "✓", "empty": "○", "error": "✗"}.get(st["status"], "?")
        print(f"  {icon} {st['label']:<15} {st['count']} result(s)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")