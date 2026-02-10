"""
Reddit Data Scraper - Scrapes top monthly posts from subreddits.
Uses undetected-chromedriver with your existing Chrome profile.

IMPORTANT: Close Chrome browser before running this script!
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from scraper import RedditScraper

# ============================================================
# CONFIGURATION - Edit these values
# ============================================================

# List of subreddits to scrape (without r/ prefix)
SUBREDDITS = [
    "shopify",
]

# Optional: search tags within each subreddit
# Set to None to just get top posts, or provide a list like ["beginner", "tips"]
TAGS = None

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Dedicated scraper profile directory (avoids locking your main Chrome)
CHROME_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")

# Set to True to run Chrome in headless mode (no visible window)
HEADLESS = True

# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    if not SUBREDDITS:
        logger.error("No subreddits configured. Edit SUBREDDITS in main.py.")
        sys.exit(1)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Ensure chrome profile dir exists (uc.Chrome does this, but for safety)
    os.makedirs(CHROME_PROFILE, exist_ok=True)

    start_time = datetime.now(timezone.utc)
    start_str = start_time.strftime("%Y-%m-%d_%H-%M-%S")

    logger.info(f"Starting Reddit scraper at {start_time.isoformat()}")
    logger.info(f"Subreddits: {SUBREDDITS}")
    logger.info(f"Tags: {TAGS or 'None (top posts only)'}")

    scraper = RedditScraper(CHROME_PROFILE, headless=HEADLESS)

    try:
        results = []

        for subreddit in SUBREDDITS:
            if TAGS:
                for tag in TAGS:
                    try:
                        data = scraper.scrape_subreddit(subreddit, tag=tag)
                        results.append(data)
                    except Exception as e:
                        logger.error(f"Failed to scrape r/{subreddit} (tag: {tag}): {e}")
            else:
                try:
                    data = scraper.scrape_subreddit(subreddit)
                    results.append(data)
                except Exception as e:
                    logger.error(f"Failed to scrape r/{subreddit}: {e}")

            # Pause between subreddits
            if subreddit != SUBREDDITS[-1]:
                import random
                import time
                pause = random.uniform(3.0, 7.0)
                logger.info(f"Pausing {pause:.1f}s before next subreddit...")
                time.sleep(pause)

        # Build output
        output = {
            "scrape_start": start_time.isoformat(),
            "scrape_end": datetime.now(timezone.utc).isoformat(),
            "subreddits": results,
        }

        total_posts = sum(r["post_count"] for r in results)
        filename = f"reddit_scrape_{start_str}.json"
        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"Done! Scraped {total_posts} posts from {len(results)} subreddit(s).")
        logger.info(f"Output saved to: {filepath}")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
