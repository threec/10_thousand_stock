"""
Use Playwright to call Xueqiu API from WITHIN the browser context.
This way, the browser's WAF bypass, cookies, and session are used naturally.
"""
import sys, os, json, re, time
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg):
    try:
        print(msg)
    except:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def fetch_timeline_in_browser():
    all_statuses = []

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

        # First, visit the main page to establish session and get through WAF
        log("[Step 1] Visiting user page to establish session...")
        page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        log(f"  Title: {page.title()}")

        # Collect cookies to save
        cookies = context.cookies()
        cookie_path = os.path.join(OUTPUT_DIR, "cookies.json")
        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log(f"  Saved {len(cookies)} cookies")

        # Now use page.evaluate() to call the API from within the browser
        log("\n[Step 2] Calling timeline API from within browser...")

        max_page = 500
        for page_num in range(1, max_page + 1):
            # Use fetch inside the browser to call the API
            # This automatically includes all browser cookies and headers
            result = page.evaluate("""
                async (params) => {
                    const { userId, page, baseUrl } = params;
                    const url = `${baseUrl}/v4/statuses/user_timeline.json?user_id=${userId}&page=${page}&type=0`;

                    try {
                        const response = await fetch(url, {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                            credentials: 'include',
                        });

                        if (!response.ok) {
                            return { error: true, status: response.status };
                        }

                        const data = await response.json();
                        const statuses = data.statuses || data.list || [];

                        return {
                            error: false,
                            status: response.status,
                            count: statuses.length,
                            statuses: statuses.map(s => ({
                                id: s.id,
                                title: s.title || '',
                                text: (s.text || s.description || '').replace(/<[^>]*>/g, ''),
                                created_at: s.created_at || '',
                                retweet_count: s.retweet_count || 0,
                                reply_count: s.reply_count || 0,
                                view_count: s.view_count || 0,
                                retweeted_status: s.retweeted_status ? {
                                    text: (s.retweeted_status.text || '').replace(/<[^>]*>/g, ''),
                                    user_name: s.retweeted_status.user ? s.retweeted_status.user.screen_name : '',
                                } : null,
                            }))
                        };
                    } catch (err) {
                        return { error: true, message: err.message };
                    }
                }
            """, {"userId": USER_ID, "page": page_num, "baseUrl": "https://xueqiu.com"})

            if result.get('error'):
                status_code = result.get('status', 'unknown')
                msg = result.get('message', '')
                log(f"  Page {page_num}: ERROR (status={status_code}, msg={msg})")
                if status_code == 400:
                    log("  -> 400 error, likely end of data or rate limited")
                    break
                if page_num > 3:
                    log("  -> Stopping due to error")
                    break
                time.sleep(2)
                continue

            statuses = result.get('statuses', [])
            count = result.get('count', 0)

            if count == 0:
                log(f"  Page {page_num}: empty, reached end of posts")
                break

            for s in statuses:
                # Clean HTML entities
                text = s.get('text', '')
                text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'").replace('&nbsp;', ' ')
                s['text'] = text
                all_statuses.append(s)

            log(f"  Page {page_num}: {count} posts (total: {len(all_statuses)})")

            if count < 5:
                log(f"  -> Less than 5 posts, likely end")
                break

            # Be polite - don't hammer the API
            time.sleep(0.8)

        browser.close()

    return all_statuses


if __name__ == "__main__":
    log("=" * 60)
    log("Xueqiu Timeline API Scraper (Browser-Context)")
    log(f"Target: User ID {USER_ID}")
    log("=" * 60)

    posts = fetch_timeline_in_browser()

    log(f"\n[+] Total posts collected: {len(posts)}")

    # Save results
    output_path = os.path.join(OUTPUT_DIR, "timeline_posts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    log(f"[+] Saved to {output_path}")

    # Print date range
    if posts:
        dates = [p.get('created_at', '') for p in posts if p.get('created_at')]
        if dates:
            log(f"[*] Date range: {dates[-1]} to {dates[0]}")

    # Print preview
    log("\n--- POST PREVIEW (first 5) ---")
    for i, post in enumerate(posts[:5]):
        created = post.get('created_at', 'unknown')
        text = post.get('text', '')[:400]
        title = post.get('title', '')
        log(f"\n[{i+1}] {created}")
        if title:
            log(f"  Title: {title[:100]}")
        log(f"  {text}")
        if len(post.get('text', '')) > 400:
            log("  ...")

    # Print latest posts too
    if len(posts) > 5:
        log(f"\n--- LATEST POSTS (last 3) ---")
        for i, post in enumerate(posts[-3:]):
            created = post.get('created_at', 'unknown')
            text = post.get('text', '')[:400]
            log(f"\n[{len(posts)-2+i}] {created}")
            log(f"  {text}")
