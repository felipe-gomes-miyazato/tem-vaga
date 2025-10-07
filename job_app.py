# python my_cli_app.py --help
#     * **Run a basic command:**
# ```bash
# python my_cli_app.py greet John -c London
# # Output: Hello, John from London!
#     * **Run a command with a boolean flag:**
# ```bash
# python my_cli_app.py greet Jane --formal
# # Output: Good day, Jane from World. It is a pleasure to meet you.
#     * **Run the second command:**
# ```bash
# python my_cli_app.py area --length 10 --width 5
# # Output: The area of a 10x5 rectangle is: 50

import typer
import logging
from typing_extensions import Annotated

from model.tracker import group_scraped_applications_by_platform
from service.linkedin import Bot as LinkedInBot

# --- Logging Setup ---

# Initialize a logger instance
log = logging.getLogger(__name__)


def configure_logging(verbose: int):
    """Configures the standard Python logging based on verbosity count."""
    
    # Calculate the desired integer log level
    # 0 (no flags) = WARNING (30)
    # 1 (-v)       = INFO (20)
    # 2 (-vv)      = DEBUG (10)
    log_level = logging.WARNING - (verbose * 10)
    log_level = max(log_level, logging.DEBUG) # Ensure level is not below DEBUG
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # --- THE FIX (Removing the warning) ---
    # The string name of the level you set
    level_name = logging.getLevelName(log_level)
    
    # Now use the string name in the log message
    log.info(f"Logging initialized at level: {level_name}")
    
# Create the main Typer application instance
app = typer.Typer(help="A simple CLI tool for scaling job research.")

# Define a global callback to run before any command (used for global options like --verbose)
@app.callback()
def main(
    verbose: Annotated[int, typer.Option(
        "--verbose", "-v", count=True,
        help="Specify verbosity level. Use -vv or -vvv for more detail (DEBUG)."
    )] = 0,
):
    """
    Handles global application options and configures logging.
    """
    configure_logging(verbose)
    # Add a DEBUG log entry to demonstrate the highest level
    log.debug("Global options processed successfully.")


# --- Command 1: Greet ---
# Define a function decorated as a command.
# Typer automatically converts function parameters (with type hints and defaults)
# into CLI arguments and options.
@app.command()
def greet(
    # Arguments are defined by required parameters without defaults.
    name: Annotated[str, typer.Argument(help="The name of the user to greet.")],

    # Options are defined by parameters with defaults or special wrappers.
    # The default value of True makes this a flag that can be disabled with --no-formal.
    formal: Annotated[bool, typer.Option(
        "--formal/--no-formal", 
        help="Say hi formally."
    )] = False,

    # Options with short flags can be defined here:
    city: Annotated[str, typer.Option("-c", "--city", help="The user's city.")] = "World"):
    """
    Greets the user, optionally with a formal salutation.
    """
    log.info(f"Executing 'greet' command for user {name} in {city}, formal={formal}.")
    
    if formal:
        message = f"Good day, {name} from {city}. It is a pleasure to meet you."
    else:
        message = f"Hello, {name} from {city}!"
        
    typer.echo(message)

# --- Command 2: Scrape jobs ---
@app.command()
def scrape(
    platform: Annotated[
        str,
        typer.Option("-p", "--platform", help="The job platform to scrape from.")
    ] = "LinkedIn",
    search_keywords: Annotated[
        str,
        typer.Option("-kw", "--search_keywords", help="Keywords to search for.")
    ] = "Data engineer",
    search_location: Annotated[
        str, 
        typer.Option("-l", "--search_location", help="Job location.")
    ] = "Remote",
    easy_apply: Annotated[
        bool, 
        typer.Option("--easy-apply/--no-easy-apply", 
                     help="Filter for easy apply jobs.")
    ] = True):
    """
    Scrapes job listings from the specified platform.
    """
    log.info(f"Executing 'scrape' command for {platform}.")
    
    if platform.lower() == "linkedin":
        typer.echo("Scraping jobs from LinkedIn...")
        
        from service.linkedin import JobScraper
        scraper = JobScraper()
        scraper.get_jobs(
            search_keywords=search_keywords,
            search_location=search_location,
            easy_apply=easy_apply)
        
# --- Command 3: Drown location and scrape ---
@app.command(name="drown-location-scrape")
def drown_location_scrape(
    platform: Annotated[
        str,
        typer.Option("-p", "--platform", help="The job platform to scrape from.")
    ] = "LinkedIn",
    search_keywords: Annotated[
        str,
        typer.Option("-kw", "--search_keywords", help="Keywords to search for.")
    ] = "Data engineer",
    easy_apply: Annotated[
        bool, 
        typer.Option("--easy-apply/--no-easy-apply", 
                     help="Filter for easy apply jobs.")
    ] = True):
    """
    Drowns location and then scrapes job listings.
    """

    locations = {
        "Brazil",
        "USA",
        "Spain",
        "Portugal",
        "United Kingdom",
        "Netherlands",
        "Amsterdam",
        "Canada",
        "Australia",
        "Remote"
    }
    location = locations.pop()
    log.info(f"Drowning location: {location} and scraping from {platform}.")
    
    # Call the scrape function
    scrape(
        platform=platform,
        search_keywords=search_keywords,
        search_location=location,
        easy_apply=easy_apply
    )

# --- Command 4: Apply scraped jobs ---
@app.command(name="apply-scraped-jobs")
def apply_scraped_jobs():
    """
    Applies to scraped job listings.
    """
    log.info(f"Executing 'apply-scraped-jobs' command.")

    grouped_applications = group_scraped_applications_by_platform()

    linkedin_bot = LinkedInBot()
    linkedin_bot.apply_to_jobs(grouped_applications["LinkedIn"])

# This block is necessary for the application to run when executed from the command line.
if __name__ == "__main__":
    # Diagnostic print to confirm initialization
    print("Typer app initializing...")
    app()