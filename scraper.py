def extract_engagement(article):
    """Extracts reaction (likes), comment, and share counts from a Facebook article container."""
    likes = 0
    comments = 0
    shares = 0

    try:
        # 1. Check aria-labels first (most reliable across Facebook DOM changes)
        for el in article.locator('[aria-label]').all():
            label = (el.get_attribute("aria-label") or "").strip()
            if not label:
                continue

            if any(k in label.lower() for k in ("reaction", "like", "people reacted")):
                m = re.search(r'(\d+(?:\.\d+)?[KM]?)', label, re.IGNORECASE)
                if m:
                    val = parse_count(m.group(1))
                    if val > likes:
                        likes = val

            elif re.search(r'\bcomments?\b', label, re.IGNORECASE):
                m = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*comments?\b', label, re.IGNORECASE)
                if m:
                    val = parse_count(m.group(1))
                    if val > comments:
                        comments = val

            elif re.search(r'\bshares?\b', label, re.IGNORECASE):
                m = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*shares?\b', label, re.IGNORECASE)
                if m:
                    val = parse_count(m.group(1))
                    if val > shares:
                        shares = val

        # 2. Check clickable counters (Facebook puts comment/share counts in role="button" elements)
        for btn in article.locator('div[role="button"], span[role="button"]').all():
            txt = (btn.inner_text() or "").strip()
            if not txt:
                continue

            c_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*comments?\b', txt, re.IGNORECASE)
            if c_match:
                val = parse_count(c_match.group(1))
                if val > comments:
                    comments = val

            s_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*shares?\b', txt, re.IGNORECASE)
            if s_match:
                val = parse_count(s_match.group(1))
                if val > shares:
                    shares = val

        # 3. Fallback: scan normalized full text (collapsing newlines/non-breaking spaces)
        full_text = article.inner_text()
        normalized_text = re.sub(r'[\s\u00a0]+', ' ', full_text)

        if comments == 0:
            c_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*comments?\b', normalized_text, re.IGNORECASE)
            if c_match:
                comments = parse_count(c_match.group(1))

        if shares == 0:
            s_match = re.search(r'(\d+(?:\.\d+)?[KM]?)\s*shares?\b', normalized_text, re.IGNORECASE)
            if s_match:
                shares = parse_count(s_match.group(1))

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

    return likes, comments, shares
