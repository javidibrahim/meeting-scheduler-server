from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os, time, json, logging, base64
from .gemini_service import GeminiService
from datetime import datetime, timezone
from bson import ObjectId
from typing import List, Optional, Dict, Any
from db.mongo import db
from models.scheduled_events import ScheduledEventAnswer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_cookies_from_env():
    """Load cookies from base64-encoded environment variable."""
    try:
        cookie_data = os.getenv('LINKEDIN_COOKIES')
        if not cookie_data:
            logger.error("[LinkedIn Scraper] No cookies found in environment variable LINKEDIN_COOKIES")
            raise ValueError("LINKEDIN_COOKIES is not set")

        decoded = base64.b64decode(cookie_data).decode("utf-8")
        cookies = json.loads(decoded)
        print("cookies", cookies)

        logger.info(f"[LinkedIn Scraper] Successfully loaded {len(cookies)} cookies")
        return cookies

    except (json.JSONDecodeError, base64.binascii.Error) as e:
        logger.error(f"[LinkedIn Scraper] Cookie decode/parsing error: {e}")
        raise

    except Exception as e:
        logger.error(f"[LinkedIn Scraper] Unexpected error loading cookies: {e}")
        raise

def add_cookies_to_driver(driver, cookies):
    """Add cookies to selenium driver."""
    driver.get("https://www.linkedin.com")  # Must open the domain first

    for cookie in cookies:
        # Convert expirationDate to expiry if needed
        if "expiry" not in cookie and "expirationDate" in cookie:
            cookie["expiry"] = int(cookie["expirationDate"])
        
        # Drop unsupported keys
        allowed_keys = {"name", "value", "domain", "path", "secure", "httpOnly", "expiry"}
        filtered = {k: v for k, v in cookie.items() if k in allowed_keys}

        try:
            driver.add_cookie(filtered)
        except Exception as e:
            print(f"[!] Failed to add cookie {filtered.get('name')}: {e}")


def _scrape_linkedin_with_selenium(profile_url: str) -> str:
    driver = None
    try:
        logger.info("[LinkedIn Scraper] Initializing Chrome driver")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=chrome_options)

        # Step 1: Load LinkedIn main page to set domain
        logger.info("[LinkedIn Scraper] Loading LinkedIn main page")
        driver.get("https://www.linkedin.com")
        time.sleep(2)

        # Step 2: Load cookies
        try:
            logger.info("[LinkedIn Scraper] Attempting to load cookies from environment")
            cookies = load_cookies_from_env()
            add_cookies_to_driver(driver, cookies)
        except Exception as e:
            logger.warning(f"[LinkedIn Scraper] Failed to load cookies from environment: {str(e)}")

        # Step 3: Reload page to apply cookies
        logger.info("[LinkedIn Scraper] Applying cookies and checking login status")
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(3)

        # Optional: Check if login was successful
        if "login" in driver.current_url or "checkpoint" in driver.current_url:
            logger.error("[LinkedIn Scraper] Login failed - cookies may be expired")
            return "Login failed — cookies may be expired or invalid."

        # Step 4: Go to target profile
        logger.info(f"[LinkedIn Scraper] Accessing profile: {profile_url}")
        driver.get(f"{profile_url}/recent-activity/shares/")
        time.sleep(5)

        # Click all "see more" buttons
        see_more_buttons = driver.find_elements(By.CLASS_NAME, "feed-shared-inline-show-more-text__see-more-less-toggle")
        for btn in see_more_buttons:
            try:
                btn.click()
                time.sleep(0.5)
            except Exception:
                pass  # ignore if not clickable

        time.sleep(1)

        post_containers = driver.find_elements(By.CLASS_NAME, "feed-shared-update-v2__control-menu-container")
        posts = []

        for post in post_containers:
            try:
                # Skip if the post is a reshared/repost block
                if post.find_elements(By.CLASS_NAME, "update-components-header__text-view"):
                    continue

                # Extract the actual post content
                text_element = post.find_element(By.CSS_SELECTOR, ".break-words.tvm-parent-container")
                text = text_element.text.strip()

                if text:
                    posts.append(text)

            except Exception as e:
                logger.warning(f"[LinkedIn Scraper] Error processing post: {str(e)}")
                continue

        if posts:
            print("posts", posts, "\n\n---\n\n")
            return "\n\n---\n\n".join(posts)
        else:
            logger.warning(f"No posts found on profile: {profile_url}")
            return None

    except Exception as e:
        logger.error(f"[LinkedIn Scraper] Scraping failed: {str(e)}")
        return f"Could not scrape profile due to error: {str(e)}"
    finally:
        if driver:
            logger.info("[LinkedIn Scraper] Closing Chrome driver")
            driver.quit()

async def create_linkedin_summary(event_id: str, profile_url: str, questions: List[ScheduledEventAnswer], answers: List[ScheduledEventAnswer]) -> None:
    """
    Scrape LinkedIn posts, analyze them using GeminiService, and store the results in the database.
    This function runs as a background task after booking is complete.
    
    Args:
        event_id: The ID of the scheduled event to update
        profile_url: LinkedIn profile URL to scrape
        questions: List of questions asked during booking
        answers: List of answers provided during booking
    """
    try:
        logger.info(f"[LinkedIn Analysis] Starting LinkedIn analysis for event {event_id}")
        logger.info(f"[LinkedIn Analysis] Profile URL: {profile_url}")
        
        # Scrape LinkedIn posts using Selenium
        linkedin_data = _scrape_linkedin_with_selenium(profile_url)
        
        if not linkedin_data:
            logger.warning(f"[LinkedIn Analysis] No posts found for profile: {profile_url}")
            enrichment = {
                "linkedin_summary": "No posts found on profile to enrich the meeting notes.",
                "enriched_at": datetime.now(timezone.utc)
            }
            
            await db["scheduled_events"].update_one(
                {"_id": ObjectId(event_id)},
                {"$set": {"enrichment": enrichment}}
            )
            return
            
        if linkedin_data.startswith("Could not scrape profile due to error:"):
            logger.error(f"[LinkedIn Analysis] Scraping failed: {linkedin_data}")
            enrichment = {
                "linkedin_summary": "Unable to analyze LinkedIn profile at this time.",
                "enriched_at": datetime.now(timezone.utc)
            }
            
            await db["scheduled_events"].update_one(
                {"_id": ObjectId(event_id)},
                {"$set": {"enrichment": enrichment}}
            )
            return
        
        # Format questions and answers for analysis
        question_texts = "\n".join([q.question for q in questions]) if questions else ""
        answer_texts = "\n".join([f"{a.question}: {a.answer}" for a in answers]) if answers else ""
        
        # Use GeminiService to analyze the data
        logger.info("[LinkedIn Analysis] Initializing GeminiService")
        gemini_service = GeminiService()
        
        logger.info("[LinkedIn Analysis] Sending data to Gemini API")
        linkedin_summary = gemini_service.generate_linkedin_analysis(
            posts=linkedin_data,
            questions=question_texts,
            answers=answer_texts
        )
        logger.info("[LinkedIn Analysis] Gemini API analysis completed")
        
        if linkedin_summary.startswith("Error:"):
            logger.error(f"[LinkedIn Analysis] Gemini API error: {linkedin_summary}")
            return
            
        # Create enrichment object
        enrichment = {
            "linkedin_summary": linkedin_summary,
            "enriched_at": datetime.now(timezone.utc)
        }
        
        # Update the scheduled event with the enrichment data
        logger.info("[LinkedIn Analysis] Updating database with analysis")
        result = await db["scheduled_events"].update_one(
            {"_id": ObjectId(event_id)},
            {"$set": {"enrichment": enrichment}}
        )
        
        if result.modified_count > 0:
            logger.info(f"[LinkedIn Analysis] Successfully updated event {event_id}")
        else:
            logger.warning(f"[LinkedIn Analysis] Failed to update event {event_id}")
            
    except Exception as e:
        logger.error(f"[LinkedIn Analysis] Critical error for event {event_id}: {str(e)}")
        logger.exception("[LinkedIn Analysis] Full traceback:")
        raise  # Re-raise the exception after logging