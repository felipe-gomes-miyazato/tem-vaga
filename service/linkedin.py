from urllib.parse import urlencode
from typing import List, Any

from playwright.sync_api import BrowserContext, Page
from util.decorators import playwright_browser_context

from model.tracker import ScrapeJob, LinkedInScrape, JobApplication, DBOperator, ApplicationFormPage

def _get_job_links(page: Page) -> dict[str,str]:
    """
    Extracts job links from the search results page by scrolling.

    Args:
        page: The Playwright Page object.
        max_jobs: The maximum number of job links to retrieve.

    Returns:
        A list of job links (URLs).
    """
    job_links:dict[str,str] = {}
    job_cards_selector = 'li.scaffold-layout__list-item'

    # Wait for the job cards to load
    page.wait_for_selector(job_cards_selector)

    # Get all the job card elements currently in view
    job_cards = page.locator(job_cards_selector).all()

    # Extract links from the visible cards
    for card in job_cards:
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(1000) # Give the page time to load new content

        link_element = card.locator('a[data-control-id]').first
        link = link_element.get_attribute('href')
        if link and link.startswith('/jobs/view'):
            current_job_id = link.split("/")[3]
            full_link = f'https://www.linkedin.com/jobs/search/?currentJobId={current_job_id}&f_AL=true&f_WT=2'
            job_links[current_job_id] = full_link

    return job_links


class JobScraper(DBOperator):
    def __init__(self):
        super().__init__()
        print("Initialized LinkedIn Job Scraper")

    @playwright_browser_context(headless=False, slow_mo=50)
    def _job_search(self,url: str, location: str, **kwargs:Any) -> dict[str,str]:
        print("Starting job search...")
        # Create a new context and pass the storage_state to it
        # Retrieve injected context from kwargs
        context: BrowserContext = kwargs['context']
        page = context.new_page()

        print(f"Navigating to search URL: {url}")
        page.goto(url)

        # Fill in the search location
        page.get_by_role(
            "combobox",
            name="City, state, or zip code"
            ).fill(location)
        page.get_by_role("button", name="Search", exact=True).click()

        # Wait for the job list to load and scroll down to load more jobs
        # LinkedIn uses infinite scrolling, so you need to scroll to get all results
        scrolls = 5 # Number of times to scroll
        for _ in range(scrolls):
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(1000) # Wait for content to load

        return _get_job_links(page)
            
    def get_jobs(
            self,
            search_keywords:str,
            search_location:str,
            easy_apply:bool=True):
        
        scrape_job = ScrapeJob(platform="LinkedIn")
        self.db_sync(scrape_job)

        linkedin_scrape = LinkedInScrape(
            search_keywords=search_keywords,
            search_location=search_location,
            easy_apply=easy_apply,
            scrape_job=scrape_job,
            scrape_job_id=scrape_job.id
        )
        self.db_sync(linkedin_scrape)

        print("Fetching easy apply jobs from LinkedIn...")
        base_url = "https://www.linkedin.com/jobs/search/"
        query_params:dict[str,str|bool] = {
            "keywords": search_keywords,
            "f_WT": "2" # remote jobs
        }
        
        if easy_apply:
            query_params["f_AL"] = easy_apply
        
        # Convert dictionary to URL query string
        search_url = f"{base_url}?{urlencode(query_params)}"

        job_links = self._job_search(search_url, search_location)
        print(f"Found {len(job_links)} job links.")

        for job_id, job_link in job_links.items():
            print(f"Job ID: {job_id}, Link: {job_link}")
            self.db_update(
                JobApplication,
                match_keys={"job_url": job_link},
                update_data={
                    "scrape_job": scrape_job,
                    "scrape_job_id": scrape_job.id,
                    "status": "Scraped",
                    'company_name': None,
                    'job_title': None,
                    'application_date': None,
                    'job_url': job_link,
                    'job_details': None
                }
            )

        print("Job scraping completed and data saved to the database.")

class Bot(DBOperator):
    def __init__(self):
        super().__init__()
        self._page: Page
        self._current_application: JobApplication
        print("Initialized LinkedIn Apply Bot")

    @playwright_browser_context(headless=False, slow_mo=50)
    def apply_to_jobs(self, applications:List["JobApplication"], **kwargs: Any):
        print("Starting job application process...")
        context: BrowserContext = kwargs['context']
        self._page = context.new_page()

        for application in applications:
            print(f"Applying to job: {application.job_title} at {application.company_name}")
            self._current_application = application
            self._handle_job()

        print("Job application process completed.")

    def _handle_job(self):
        print(f"Navigating to job URL: {self._current_application.job_url}")
        self._page.goto(self._current_application.job_url)
        self._page.wait_for_timeout(1000) # Wait for content to load

        applied_tags_count = self._page.locator(
            '.artdeco-inline-feedback__message:has-text("Applied")').count()
        
        if not self._current_application.scrape_job.linkedin_scrapes[0].easy_apply:
            raise  ValueError("Non-Easy Apply not implemented.")

        if applied_tags_count == 0:
            print("The 'Applied' tag is not present after waiting.")

            # Extract job description from the current page
            about_elem = self._page.locator('#job-details')
            about_text = ""
            about_elem.wait_for(timeout=5000)
            about_text = about_elem.inner_text()

            self._current_application.job_details = about_text
            self.db_sync(self._current_application)

            self._page.click('#jobs-apply-button-id')
            self._form_recursion()
        
        self._current_application.status = "Applied"
        self.db_sync(self._current_application)
    
    def _form_recursion(self, depth:int=0):
        form_page_title = self._page.locator('div[data-test-modal-container] h3.t-16.t-bold').all_text_contents()
        form_page_title = form_page_title[0].replace('\n','').replace('  ','') if form_page_title else "Unknown"
        print(f"Form recursion depth {depth}, page title: {form_page_title}")

        self.db_update(
            ApplicationFormPage,
            match_keys={
                "job_application_id": self._current_application.id,
                "page_number": depth
            },
            update_data={
                "form_page_title": form_page_title
            })
        
        static_page_titles = ["Contact info", "Resume",
                                "Screening questions"]
        
        if form_page_title == "Privacy policy":
            self._page.get_by_text("I Agree Terms & Conditions").click()

        elif form_page_title not in static_page_titles:
            # Load cache from external file
            try:
                with open('question_cache.json', 'r', encoding='utf-8') as f:
                    question_cache = json.load(f)
            except FileNotFoundError:
                question_cache = {} # Use an empty cache if the file is not found
                print("Question cache file not found, continuing without cache.")

            # Extract all questions from the form
            all_form_questions = extract_form_questions(page)

            # Get responses using the cache and LLM
            all_responses = create_responses(
                all_form_questions, 
                about_text,
                applicant_data,
                "llama3",
                question_cache
            )

            # Select all label elements within the specific modal content
            raw_labels = page.locator('.jobs-easy-apply-modal__content label')
            raw_labels_count = raw_labels.count()

            dropdown_labels = page.locator('label[data-test-text-entity-list-form-title] span[aria-hidden="true"]')
            dropdown_questions = [dropdown_labels.nth(i).inner_text() for i in range(dropdown_labels.count())]

            raw_i = 0
            while raw_i < raw_labels_count:
                raw_label = raw_labels.nth(raw_i).inner_text().split('\n')[0]

                if raw_label == 'Upload':
                    raw_i += 1
                    continue

                if raw_label == 'Yes':
                    if all_responses[raw_label] == "Yes":
                        raw_labels.nth(raw_i).click()
                    elif all_responses[raw_label] == "No":
                        raw_labels.nth(raw_i + 1).click()
                    else:
                        raise ValueError(f"Invalid response for single-option question: {all_responses[raw_label]}")
                    raw_i += 2

                elif raw_label in dropdown_questions:
                    raw_labels.nth(raw_i).select_option(all_responses[raw_label])
                    raw_i += 1

                else:
                    raw_labels.nth(raw_i).fill(str(all_responses[raw_label]))
                    page.wait_for_timeout(1000) # Wait for content to load
                    page.keyboard.press('Enter')
                    raw_i += 1

        # ... (rest of your existing logic for finding and clicking buttons)
        submit_button_text = page.locator('button:has-text("Submit application")')
        if submit_button_text.count() > 0:
            print("Submit button found, clicking it.")
            submit_button_text.click()
            return True
        
        review_button_text = page.locator('button:has-text("Review")')
        if review_button_text.count() > 0:
            print("Review button found, clicking it.")
            review_button_text.click()
            page.click('button[aria-label="Submit application"]')
            return True
        
        else:
            page.click('//*[@aria-label="Continue to next step"]')
            return form_recursion(page, applicant_data, about_text, depth+1)
