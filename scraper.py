import json
import re
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

URL = "https://www.facebook.com/NFLDBulletin"

def scrape_facebook():
    posts = []
    seen_urls = set()
    debug_title = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 2200},
            locale="en-CA"
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.route("**/*.{png,jpg,jpeg,webp,gif,mp4,woff,woff2}", lambda route: route.abort())

        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        debug_title = page.title()

        # Dismiss login modal
        try:
            close_btn = page.locator('[aria-label="Close"]').first
            if close_btn.is_visible(timeout=1500):
                close_btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            page.keyboard.press("Escape")

        # Scroll down in steps to load the top 6-8 posts
        for _ in range(5):
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1800)

        articles = page.locator('[role="article"]').all()

        for article in articles:
            if len(posts) >= 6:
                break
            try:
                # Expand "See more" before reading text
                for btn in article.locator('div[role="button"]:has-text("See more")').all():
                    try:
                        if btn.is_visible(timeout=300):
                            btn.click()
                            page.wait_for_timeout(500)
                    except Exception:
                        pass

                # Extract post permalink first to deduplicate
                link = ""
                for a in article.locator('a[href*="/posts/"], a[href*="/permalink/"], a[href*="/videos/"], a[href*="story_fbid"]').all():
                    href = a.get_attribute("href")
                    if href:
                        clean_href = href.split("?")[0]
                        if clean_href.startswith("/"):
                            clean_href = f"https://www.facebook.com{clean_href}"
                        link = clean_href
                        break

                if not link or link in seen_urls:
                    continue

                # Grab only the primary message container to prevent paragraph duplication
                msg_locator = article.locator('[data-ad-preview="message"]').first
                if msg_locator.count() > 0:
                    raw_text = msg_locator.inner_text()
                else:
                    blocks = [
                        b.strip() for b in article.locator('div[dir="auto"]').all_inner_texts()
                        if len(b.strip()) > 30 and "Want to help support what we do?" not in b
                    ]
                    raw_text = blocks[0] if blocks else ""

                # Clean up trailing "See less" / "See more" and extra blank lines
                clean_text = re.sub(r'\s*(See less|See more)\s*$', '', raw_text.strip()).strip()

                if clean_text and "Want to help support what we do?" not in clean_text:
                    seen_urls.add(link)
                    posts.append({
                        "text": clean_text,
                        "url": link
                    })
            except Exception:
                continue

        browser.close()

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NFLD Bulletin (Facebook)",
        "page_title": debug_title,
        "posts": posts
    }

    with open("nfld_fb.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scrape_facebook()
