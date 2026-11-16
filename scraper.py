import json
import re
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

URLS = [
    "https://www.facebook.com/NFLDBulletin/posts",
    "https://m.facebook.com/NFLDBulletin"
]

def extract_from_scripts(html):
    posts = []
    # Facebook embeds post text inside serialized JSON script blocks ("text":"...")
    matches = re.findall(r'"message"\s*:\s*\{"text"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
    for raw in matches:
        try:
            decoded = json.loads(f'"{raw}"')
            clean = decoded.strip()
            if len(clean) > 35 and clean not in [p["text"] for p in posts]:
                posts.append({
                    "text": clean,
                    "url": "https://www.facebook.com/NFLDBulletin"
                })
        except Exception:
            continue
    return posts[:5]

def scrape_facebook():
    posts = []
    debug_title = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="en-CA"
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.route("**/*.{png,jpg,jpeg,webp,gif,mp4,woff,woff2}", lambda route: route.abort())

        for target_url in URLS:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
                debug_title = page.title()

                # Try dismissing login modal
                try:
                    close_btn = page.locator('[aria-label="Close"]').first
                    if close_btn.is_visible(timeout=1500):
                        close_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    page.keyboard.press("Escape")

                # 1. Try DOM article extraction
                articles = page.locator('[role="article"], article').all()
                for article in articles:
                    if len(posts) >= 5:
                        break
                    text_blocks = article.locator('[data-ad-preview="message"], div[dir="auto"], p').all_inner_texts()
                    clean_text = "\n".join(
                        dict.fromkeys(line.strip() for line in text_blocks if len(line.strip()) > 30)
                    )
                    if clean_text and not any(existing["text"] == clean_text for existing in posts):
                        link = target_url
                        for a in article.locator('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]').all():
                            href = a.get_attribute("href")
                            if href:
                                link = href.split("?")[0]
                                if link.startswith("/"):
                                    link = f"https://www.facebook.com{link}"
                                break
                        posts.append({"text": clean_text, "url": link})

                # 2. Fallback: parse embedded JSON scripts from raw HTML
                if not posts:
                    posts = extract_from_scripts(page.content())

                if posts:
                    break
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
