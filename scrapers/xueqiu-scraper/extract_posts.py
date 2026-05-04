"""
Extract posts from Xueqiu full_page.html using Playwright DOM scraping.
Also parse any embedded data from the HTML.
"""
import sys, os
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json, re
from playwright.sync_api import sync_playwright

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"


def extract_from_embedded_data(html):
    """Extract any JSON data embedded in script tags."""
    results = {}

    # Extract SNOWMAN_TARGET (user profile)
    match = re.search(r'window\.SNOWMAN_TARGET\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
    if match:
        try:
            results['user_profile'] = json.loads(match.group(1))
            print(f"[+] Extracted user profile: {results['user_profile'].get('screen_name', 'unknown')}")
            print(f"    Followers: {results['user_profile'].get('followers_count', 0)}")
            print(f"    Statuses: {results['user_profile'].get('status_count', 0)}")
            print(f"    Description: {results['user_profile'].get('description', '')}")
        except json.JSONDecodeError as e:
            print(f"[!] Failed to parse SNOWMAN_TARGET: {e}")

    # Look for any other SNOWMAN_ or window. objects
    for pattern in [r'window\.SNOWMAN_\w+\s*=\s*(\{.*?\});', r'window\.SNB_\w+\s*=\s*(\{.*?\});']:
        for m in re.finditer(pattern, html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                print(f"[*] Found embedded data: {str(data)[:200]}")
            except:
                pass

    return results


def scrape_with_playwright():
    """Use Playwright to interact with the loaded page and extract posts."""
    all_posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = context.new_page()

        # Go to user timeline
        url = f"https://xueqiu.com/u/{USER_ID}"
        print(f"[*] Loading {url} ...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        title = page.title()
        print(f"[*] Title: {title}")

        # Try to scroll and extract posts using JavaScript evaluation
        # Xueqiu uses a feed/timeline with status-list items

        posts_extracted = 0
        no_new = 0
        scroll = 0

        while scroll < 500 and no_new < 20:
            # Extract all status items using JavaScript directly
            items = page.evaluate("""() => {
                const results = [];
                // Try different selectors for timeline items
                const selectors = [
                    '.timeline__item',
                    '[class*="timeline__item"]',
                    '.status-list > div',
                    'article.status-item',
                    '[class*="feed"] [class*="item"]',
                    '.profile__main .timeline__item',
                ];

                let items = [];
                for (const sel of selectors) {
                    items = document.querySelectorAll(sel);
                    if (items.length > 0) break;
                }

                // If still no items found, try to find all large text blocks
                if (items.length === 0) {
                    // Look for the main content area
                    const main = document.querySelector('.profile__main, main, [role="main"], #app');
                    if (main) {
                        // Get all divs with substantial text
                        const divs = main.querySelectorAll('div');
                        for (const div of divs) {
                            const text = div.innerText;
                            if (text && text.length > 50 && text.length < 5000) {
                                const cls = div.className || '';
                                results.push({html: div.outerHTML.substring(0, 2000), text: text.substring(0, 1000)});
                            }
                        }
                        return results.slice(0, 50);
                    }
                }

                for (const item of items) {
                    const text = item.innerText;
                    const html = item.outerHTML;
                    if (text && text.length > 10) {
                        results.push({
                            text: text.substring(0, 3000),
                            html: html.substring(0, 5000),
                            className: item.className
                        });
                    }
                }
                return results.slice(0, 50);
            }""")

            if items:
                new_found = 0
                for item in items:
                    text = item.get('text', '').strip()
                    if text and len(text) > 20:
                        dedup = text[:100]
                        if not any(p.get('text', '')[:100] == dedup for p in all_posts):
                            all_posts.append(item)
                            new_found += 1

                if new_found > 0:
                    print(f"[*] Scroll {scroll+1}: +{new_found} posts (total: {len(all_posts)})")
                    no_new = 0
                else:
                    no_new += 1

                posts_extracted += new_found
            else:
                no_new += 1

            # Scroll down
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            # Click load more
            try:
                page.evaluate("""() => {
                    const btns = document.querySelectorAll('a, button, span, div');
                    for (const btn of btns) {
                        if (btn.innerText && (btn.innerText.includes('查看更多') || btn.innerText.includes('加载更多'))) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
            except:
                pass

            scroll += 1

        # After scrolling, capture the full list using Vue devtools-style extraction
        print(f"\n[*] Scrolling done. Extracting final data...")

        # Try to get all rendered text
        full_text = page.evaluate("""() => {
            const main = document.querySelector('.profile__main, main, [role="main"]');
            if (main) return main.innerText;
            return document.body.innerText;
        }""")

        # Save full text
        text_path = os.path.join(OUTPUT_DIR, "full_text.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(full_text or "")
        print(f"[+] Saved full rendered text ({len(full_text or '')} chars) to {text_path}")

        # Also save updated HTML
        html = page.content()
        html_path = os.path.join(OUTPUT_DIR, "full_page_scrolled.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[+] Saved scrolled HTML ({len(html)} chars) to {html_path}")

        browser.close()

    return all_posts


if __name__ == "__main__":
    print("=" * 60)
    print("Xueqiu Post Extractor")
    print("=" * 60)

    # Step 1: Extract from already downloaded HTML
    html_path = os.path.join(OUTPUT_DIR, "page_debug.html")
    if os.path.exists(html_path):
        print(f"\n[Phase 1] Parsing embedded data from {html_path}...")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        profile = extract_from_embedded_data(html)

    # Step 2: Use Playwright to scroll and extract
    print(f"\n[Phase 2] Using Playwright to scroll and extract posts...")
    posts = scrape_with_playwright()

    # Save posts
    posts_path = os.path.join(OUTPUT_DIR, "extracted_posts.json")
    with open(posts_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"\n[+] Saved {len(posts)} posts to {posts_path}")

    # Print first 3 posts
    print("\n--- PREVIEW ---")
    for i, post in enumerate(posts[:3]):
        text = post.get('text', '')[:500]
        print(f"\n[Post {i+1}]")
        print(text)
        if len(post.get('text', '')) > 500:
            print("...")
