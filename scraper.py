import random
import time
import logging
from urllib.parse import quote_plus

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)

logger = logging.getLogger(__name__)


class RedditScraper:
    """Scrapes Reddit subreddit top/monthly posts using undetected Chrome."""

    def __init__(self, chrome_profile_path: str, profile_name: str = "Default", headless: bool = False):
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")
        options.add_argument(f"--profile-directory={profile_name}")
        
        # Explicitly disable some features that can cause issues with automation
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-dev-shm-usage")

        logger.info("Launching Chrome...")
        logger.info(f"User Data Dir: {chrome_profile_path}")
        logger.info(f"Profile Name: {profile_name}")
        
        try:
            # Note: headless in uc.Chrome sometimes causes issues on Windows
            # and might require additional options.
            self.driver = uc.Chrome(
                user_data_dir=chrome_profile_path,
                version_main=144,
                use_subprocess=True,
            )
            self.driver.implicitly_wait(10)
            self.driver.set_window_size(1920, 1080)
            logger.info("Chrome launched successfully.")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to launch Chrome. Error: {e}")
            logger.error("Possible fixes:")
            logger.error("1. Close ALL Chrome windows (including system tray icons).")
            logger.error("2. Try using a different 'OUTPUT_DIR' or a temp profile.")
            logger.error("3. Verify your Chrome version is 144.")
            raise

    def _build_url(self, subreddit: str, tag: str | None = None) -> str:
        base = f"https://www.reddit.com/r/{subreddit}"
        if tag:
            return f"{base}/search/?q={quote_plus(tag)}&t=month&sort=top"
        return f"{base}/top/?t=month"

    def _random_sleep(self, low: float, high: float):
        time.sleep(random.uniform(low, high))

    def _scroll_and_collect(self) -> list[dict]:
        """Scroll down fast and collect posts incrementally to avoid
        Reddit's DOM virtualization dropping earlier posts."""
        scroll_count = 0
        seen_permalinks = set()
        collected_posts = []
        prev_height = self.driver.execute_script("return document.body.scrollHeight")

        while True:
            # Grab all currently visible posts before scrolling past them
            self._collect_visible_posts(seen_permalinks, collected_posts)

            # Jump to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self._random_sleep(0.5, 1.0)

            scroll_count += 1

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == prev_height:
                # Collect once more before the retry wait
                self._collect_visible_posts(seen_permalinks, collected_posts)

                logger.info(
                    f"No new content at scroll {scroll_count}. "
                    f"Waiting 5s for lazy-load... ({len(collected_posts)} posts so far)"
                )
                time.sleep(5)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self._random_sleep(0.5, 1.0)

                # Collect again after retry
                self._collect_visible_posts(seen_permalinks, collected_posts)

                final_height = self.driver.execute_script("return document.body.scrollHeight")
                if final_height == prev_height:
                    logger.info(
                        f"Still no new content after retry. "
                        f"Done scrolling. Total scrolls: {scroll_count}, "
                        f"total posts collected: {len(collected_posts)}"
                    )
                    break
                else:
                    prev_height = final_height
            else:
                prev_height = new_height

            if scroll_count % 20 == 0:
                logger.info(
                    f"Scrolled {scroll_count} times, page height: {new_height}px, "
                    f"posts collected: {len(collected_posts)}"
                )

        return collected_posts

    def _collect_visible_posts(self, seen: set, posts: list):
        """Extract data from all currently visible shreddit-post elements,
        skipping any already collected (by permalink)."""
        elements = self.driver.find_elements(By.TAG_NAME, "shreddit-post")
        for elem in elements:
            try:
                permalink = elem.get_attribute("permalink") or ""
                if not permalink or permalink in seen:
                    continue
                data = self._extract_post_data(elem)
                if data:
                    seen.add(permalink)
                    posts.append(data)
            except StaleElementReferenceException:
                continue

    def _extract_post_data(self, post_element) -> dict | None:
        """Extract data from a <shreddit-post> element using its attributes."""
        try:
            title = post_element.get_attribute("post-title") or ""
            score_str = post_element.get_attribute("score") or "0"
            comment_str = post_element.get_attribute("comment-count") or "0"
            author = post_element.get_attribute("author") or ""
            permalink = post_element.get_attribute("permalink") or ""
            created = post_element.get_attribute("created-timestamp") or ""

            try:
                score = int(score_str)
            except ValueError:
                score = 0
            try:
                comment_count = int(comment_str)
            except ValueError:
                comment_count = 0

            # Extract body text from nested shreddit-post-text-body
            description = ""
            try:
                text_body = post_element.find_element(
                    By.TAG_NAME, "shreddit-post-text-body"
                )
                md_div = text_body.find_element(By.CSS_SELECTOR, "div.md, [class*=' md ']")
                description = md_div.text.strip()
            except NoSuchElementException:
                pass  # Image/link posts have no text body

            if not title:
                return None

            return {
                "title": title,
                "description": description,
                "score": score,
                "comment_count": comment_count,
                "author": author,
                "permalink": permalink,
                "created": created,
            }
        except StaleElementReferenceException:
            logger.warning("Stale element encountered, skipping post")
            return None

    def scrape_subreddit(self, subreddit: str, tag: str | None = None) -> dict:
        """Scrape all visible posts from a subreddit's top/month page."""
        url = self._build_url(subreddit, tag)
        tag_info = f" (tag: {tag})" if tag else ""
        logger.info(f"Navigating to r/{subreddit}{tag_info}: {url}")

        self.driver.get(url)
        # Brief wait for page to render
        self._random_sleep(1.0, 2.0)

        logger.info("Starting scroll and collect...")
        posts = self._scroll_and_collect()

        logger.info(f"Successfully extracted {len(posts)} posts from r/{subreddit}{tag_info}")

        return {
            "subreddit": subreddit,
            "tag": tag,
            "post_count": len(posts),
            "posts": posts,
        }

    def close(self):
        """Quit the browser."""
        try:
            self.driver.quit()
            logger.info("Browser closed.")
        except Exception:
            pass
