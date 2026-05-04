"""
Scrape Xueqiu user posts using Playwright to bypass WAF.
Target: 直到一万点 (user_id=7845696728)
"""
import sys
import time
import json
import re
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

USER_ID = "7845696728"
XUEQIU_URL = f"https://xueqiu.com/u/{USER_ID}"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xueqiu_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg):
    """Print safely to Windows console."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def scrape_xueqiu():
    all_statuses = []
    cookies_list = []

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

        log(f"[*] Navigating to {XUEQIU_URL} ...")
        page.goto(XUEQIU_URL, wait_until="domcontentloaded", timeout=30000)
        log("[*] Page loaded, waiting for render...")
        time.sleep(6)

        title = page.title()
        log(f"[*] Page title: {title}")
        log(f"[*] Current URL: {page.url}")

        # Save HTML for inspection
        html = page.content()
        html_path = os.path.join(OUTPUT_DIR, "page_debug.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"[+] Saved HTML ({len(html)} chars) to {html_path}")

        # Check for key elements
        for selector in ["[class*='user']", "[class*='profile']", "[class*='timeline']", "[class*='status']", "[class*='article']"]:
            try:
                count = len(page.query_selector_all(selector))
                if count > 0:
                    log(f"[*] Found {count} elements matching '{selector}'")
            except:
                pass

        # Get cookies for API access
        cookies_list = context.cookies()
        log(f"[*] Got {len(cookies_list)} cookies from browser session")

        # Try to intercept XHR responses to capture API data
        # Set up response listener before reloading
        api_data = []

        def handle_response(response):
            url = response.url
            if '/v4/statuses/user_timeline' in url and response.status == 200:
                try:
                    data = response.json()
                    statuses = data.get('statuses', [])
                    api_data.extend([{
                        'text': re.sub(r'<[^>]+>', '', s.get('text', s.get('description', ''))).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'),
                        'title': s.get('title', ''),
                        'created_at': s.get('created_at', ''),
                        'id': s.get('id', ''),
                        'retweet_count': s.get('retweet_count', 0),
                        'reply_count': s.get('reply_count', 0),
                        'view_count': s.get('view_count', 0),
                    } for s in statuses])
                    log(f"[*] Intercepted {len(statuses)} statuses from API (total: {len(api_data)})")
                except Exception as e:
                    log(f"[!] Error parsing intercepted response: {e}")

        page.on("response", handle_response)

        # Scroll to trigger API calls and load more content
        scroll_count = 0
        no_change_count = 0
        last_count = 0
        max_scrolls = 300

        while scroll_count < max_scrolls and no_change_count < 15:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # Try clicking "load more" buttons
            for btn_text in ['查看更多', '加载更多', '展开更多']:
                try:
                    btns = page.get_by_text(btn_text)
                    if btns.count() > 0:
                        btns.first.click()
                        log(f"[*] Clicked '{btn_text}' button")
                        time.sleep(1)
                except:
                    pass

            scroll_count += 1
            current_count = len(api_data)
            if current_count == last_count:
                no_change_count += 1
            else:
                no_change_count = 0
                last_count = current_count

            if scroll_count % 10 == 0:
                log(f"[*] Scroll {scroll_count}: {current_count} posts collected...")

        # Save full HTML after scrolling
        full_html = page.content()
        with open(os.path.join(OUTPUT_DIR, "full_page.html"), "w", encoding="utf-8") as f:
            f.write(full_html)
        log(f"[+] Saved full page HTML")

        browser.close()

    return api_data, cookies_list


def scrape_via_cookies(cookies):
    """Use Playwright cookies to access Xueqiu API via requests."""
    import requests

    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://xueqiu.com/u/{USER_ID}',
        'X-Requested-With': 'XMLHttpRequest',
    })

    # Set cookies
    cookie_dict = {}
    for c in cookies:
        cookie_dict[c['name']] = c['value']
    s.cookies.update(cookie_dict)

    all_statuses = []
    for page_num in range(1, 101):
        url = f"https://xueqiu.com/v4/statuses/user_timeline.json?user_id={USER_ID}&page={page_num}"
        try:
            resp = s.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                statuses = data.get('statuses') or data.get('list', [])
                if not statuses:
                    log(f"[*] API page {page_num}: empty, stopping")
                    break

                for s in statuses:
                    text = s.get('text', s.get('description', ''))
                    text = re.sub(r'<[^>]+>', '', text)
                    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'")

                    all_statuses.append({
                        'id': s.get('id', ''),
                        'title': s.get('title', ''),
                        'text': text.strip(),
                        'created_at': s.get('created_at', ''),
                        'retweet_count': s.get('retweet_count', 0),
                        'reply_count': s.get('reply_count', 0),
                        'view_count': s.get('view_count', 0),
                    })

                log(f"[*] API page {page_num}: {len(statuses)} posts (total: {len(all_statuses)})")
                time.sleep(0.5)
            elif resp.status_code == 400:
                log(f"[*] API page {page_num}: 400 - session expired or rate limited")
                break
            else:
                log(f"[*] API page {page_num}: HTTP {resp.status_code}")
                break
        except Exception as e:
            log(f"[!] API error on page {page_num}: {e}")
            break

    return all_statuses


if __name__ == "__main__":
    log("=" * 60)
    log("Xueqiu Scraper - Target: 直到一万点 (ID: 7845696728)")
    log("=" * 60)

    # Step 1: Use Playwright to get cookies and intercept API calls
    log("\n[Phase 1] Launching browser to bypass WAF and intercept API calls...")
    api_data, cookies = scrape_xueqiu()

    log(f"\n[*] Phase 1 result: {len(api_data)} posts from API interception")

    # Save Phase 1 results
    with open(os.path.join(OUTPUT_DIR, "posts_intercepted.json"), "w", encoding="utf-8") as f:
        json.dump(api_data, f, ensure_ascii=False, indent=2)

    # Step 2: Use cookies to call API directly for more pages
    log(f"\n[Phase 2] Using browser cookies ({len(cookies)} cookies) to call API directly...")
    api_posts = scrape_via_cookies(cookies)

    log(f"\n[*] Phase 2 result: {len(api_posts)} posts from direct API calls")

    with open(os.path.join(OUTPUT_DIR, "posts_api.json"), "w", encoding="utf-8") as f:
        json.dump(api_posts, f, ensure_ascii=False, indent=2)

    # Deduplicate and merge
    seen_ids = set()
    all_posts = []
    for post_list in [api_data, api_posts]:
        for p in post_list:
            pid = p.get('id') or p.get('text', '')[:50]
            if pid not in seen_ids:
                seen_ids.add(pid)
                all_posts.append(p)

    # Save final combined results
    output_path = os.path.join(OUTPUT_DIR, "all_posts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    log(f"\n[+] FINAL: {len(all_posts)} unique posts saved to {output_path}")
    log(f"[+] Also saved: page HTML in {OUTPUT_DIR}")

    # Print first few posts as preview
    if all_posts:
        log("\n--- POST PREVIEW ---")
        for i, post in enumerate(all_posts[:5]):
            text = post.get('text', '')[:300]
            created = post.get('created_at', '')
            log(f"\n[Post {i+1}] {created}")
            log(f"  {text}")
            if post.get('text', '') and len(post.get('text', '')) > 300:
                log("  ... (truncated)")
