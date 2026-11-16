import json
import os
import re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

URL = "https://www.facebook.com/NFLDBulletin/posts"

def parse_count(raw_str):
    """Converts Facebook shorthand like '1.2K' or '45' into an integer."""
    if not raw_str:
        return 0
    clean = raw_str.strip().upper().replace(",", "")
    match = re.search(r'(\d+(?:\.\d+)?)\s*([KM])?', clean)
    if not match:
        return 0
    num = float(match.group(1))
    suffix = match.group(2)
    if suffix == "K":
        num *= 1000
    elif suffix == "M":
        num *= 1000000
    return int(num)

def extract_engagement(article):
    """Extracts reaction (likes) and comment counts from a Facebook article container."""
    likes = 0
    comments = 0

    try:
        full_text = article.inner_text()

        comment_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s+comments?\b', full_text, re.IGNORECASE)
        if comment_match:
            comments = parse_count(comment_match.group(1))

        for el in article.locator('[aria-label*="reaction"], [aria-label*="Like"], [aria-label*="people reacted"]').all():
            label = el.get_attribute("aria-label") or ""
            m = re.search(r'(\d+(?:\.\d+)?[KM]?)', label)
            if m:
                val = parse_count(m.group(1))
                if val > likes:
                    likes = val

        if likes == 0:
            lines = [line.strip() for line in full_text.split("\n") if line.strip()]
            for i, line in enumerate(lines):
                if line.lower() in ("like", "comment", "share") and i > 0:
                    prev_line = lines[i - 1]
                    if re.fullmatch(r'\d+(?:\.\d+)?[KM]?', prev_line, re.IGNORECASE):
                        likes = parse_count(prev_line)
                        break
    except Exception:
        pass

    return likes, comments

def extract_post_image(article):
    """Extracts the primary post photo URL while skipping profile avatars and tiny reaction icons."""
    try:
        for img in article.locator('img[src*="scontent"], img[src*="fbcdn"]').all():
            src = img.get_attribute("src") or ""
            if not src or "emoji" in src or "static.xx.fbcdn.net" in src:
                continue

            # Filter out small 32x32 / 40x40 circular page avatars
            width_attr = img.get_attribute("width")
            height_attr = img.get_attribute("height")
            if width_attr and width_attr.isdigit() and int(width_attr) < 120:
                continue
            if height_attr and height_attr.isdigit() and int(height_attr) < 120:
                continue

            # Skip images inside the header/profile link area if small
            box = img.bounding_box()
            if box and (box["width"] < 120 or box["height"] < 120):
                continue

            return src
    except Exception:
        pass
    return ""

def scrape_facebook():
    scraped_map = {}
    debug_title = ""
    now_utc = datetime.now(timezone.utc)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1800},
            locale="en-CA"
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # Aborting image downloads still leaves the <img src="..."> URLs intact in the DOM
        page.route("**/*.{png,jpg,jpeg,webp,gif,mp4,woff,woff2}", lambda route: route.abort())

        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4500)
        debug_title = page.title()

        # Dismiss login modal
        try:
            close_btn = page.locator('[aria-label="Close"]').first
            if close_btn.is_visible(timeout=2000):
                close_btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            page.keyboard.press("Escape")

        for _ in range(3):
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(1500)

        articles = page.locator('[role="article"]').all()

        for article in articles:
            try:
                # Expand "See more" before reading text
                for btn in article.locator('div[role="button"]:has-text("See more")').all():
                    try:
                        if btn.is_visible(timeout=300):
                            btn.click()
                            page.wait_for_timeout(500)
                    except Exception:
                        pass

                link = ""
                for a in article.locator('a[href*="/posts/"], a[href*="/permalink/"], a[href*="/videos/"], a[href*="story_fbid"]').all():
                    href = a.get_attribute("href")
                    if href:
                        clean_href = href.split("?")[0]
                        if clean_href.startswith("/"):
                            clean_href = f"https://www.facebook.com{clean_href}"
                        link = clean_href
                        break

                if not link or link in scraped_map:
                    continue

                msg_locator = article.locator('[data-ad-preview="message"]').first
                if msg_locator.count() > 0:
                    raw_text = msg_locator.inner_text()
                else:
                    blocks = [
                        b.strip() for b in article.locator('div[dir="auto"]').all_inner_texts()
                        if len(b.strip()) > 30 and "Want to help support what we do?" not in b
                    ]
                    raw_text = blocks[0] if blocks else ""

                clean_text = re.sub(r'\s*(See less|See more)\s*$', '', raw_text.strip()).strip()

                if clean_text and "Want to help support what we do?" not in clean_text:
                    likes, comments = extract_engagement(article)
                    image_url = extract_post_image(article)
                    scraped_map[link] = {
                        "text": clean_text,
                        "url": link,
                        "image": image_url,
                        "likes": likes,
                        "comments": comments,
                        "first_seen": now_utc.isoformat()
                    }
            except Exception:
                continue

        browser.close()

    existing_posts = []
    if os.path.exists("nfld_fb.json"):
        try:
            with open("nfld_fb.json", "r", encoding="utf-8") as f:
                existing_posts = json.load(f).get("posts", [])
        except Exception:
            existing_posts = []

    cutoff = now_utc - timedelta(hours=48)
    merged_posts = []
    seen_urls = set()

    existing_by_url = {p["url"]: p for p in existing_posts if "url" in p}
    for url, fresh_post in scraped_map.items():
        if url in existing_by_url:
            fresh_post["first_seen"] = existing_by_url[url].get("first_seen", now_utc.isoformat())
            if not fresh_post["image"]:
                fresh_post["image"] = existing_by_url[url].get("image", "")
        merged_posts.append(fresh_post)
        seen_urls.add(url)

    for old_post in existing_posts:
        url = old_post.get("url")
        if url and url not in seen_urls and len(merged_posts) < 60:
            seen_str = old_post.get("first_seen")
            if not seen_str:
                old_post["first_seen"] = now_utc.isoformat()
                merged_posts.append(old_post)
                seen_urls.add(url)
            elif datetime.fromisoformat(seen_str) > cutoff:
                old_post.setdefault("image", "")
                old_post.setdefault("likes", 0)
                old_post.setdefault("comments", 0)
                merged_posts.append(old_post)
                seen_urls.add(url)

    output = {
        "updated_at": now_utc.isoformat(),
        "source": "NFLD Bulletin (Facebook)",
        "page_title": debug_title,
        "posts": merged_posts
    }

    with open("nfld_fb.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scrape_facebook()
