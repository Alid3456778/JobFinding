import os 
from flask import Flask, render_template, request
from job_automation import JobScraper

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    jobs = []
    message = ""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        location = request.form.get('location', '').strip()
        max_results = int(request.form.get('max_results', 10))
        latest_days = int(request.form.get('latest_days', 7))

        if title and location:
            scraper = JobScraper()
            all_jobs = scraper.scrape_all_sites(title, location, max_results)
            filtered_jobs = scraper.filter_latest_jobs(all_jobs, latest_days)
            jobs = filtered_jobs if filtered_jobs else all_jobs
            message = f"Found {len(jobs)} jobs for '{title}' in '{location}'"

    return render_template('index.html', jobs=jobs, message=message)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

