import json
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

URL = "https://www.facebook.com/NFLDBulletin"

def scrape_facebook():
    posts = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="en-CA"
        )
        page = context.new_page()

        # Block images/media/fonts to keep runs fast and lightweight
        page.route("**/*.{png,jpg,jpeg,webp,gif,mp4,woff,woff2}", lambda route: route.abort())

        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        # Dismiss Facebook's login popup if it appears
        try:
            close_btn = page.locator('[aria-label="Close"]').first
            if close_btn.is_visible(timeout=2000):
                close_btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            page.keyboard.press("Escape")

        # Scroll slightly to ensure the top 5 posts render
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(2000)

        articles = page.locator('[role="article"]').all()

        for article in articles:
            if len(posts) >= 5:
                break
            try:
                # Expand "See more" buttons if present
                see_more = article.locator('div[role="button"]:has-text("See more")').first
                if see_more.is_visible(timeout=500):
                    see_more.click()
                    page.wait_for_timeout(500)

                text_blocks = article.locator('[data-ad-preview="message"], div[dir="auto"]').all_inner_texts()
                clean_text = "\n".join(
                    dict.fromkeys(line.strip() for line in text_blocks if len(line.strip()) > 25)
                )

                # Extract post permalink
                link = URL
                for a in article.locator('a[href*="/posts/"], a[href*="/permalink/"], a[href*="/videos/"], a[href*="story_fbid"]').all():
                    href = a.get_attribute("href")
                    if href:
                        link = href.split("?")[0]
                        if link.startswith("/"):
                            link = f"https://www.facebook.com{link}"
                        break

                if clean_text and not any(existing["text"] == clean_text for existing in posts):
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
        "posts": posts
    }

    with open("nfld_fb.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scrape_facebook()
