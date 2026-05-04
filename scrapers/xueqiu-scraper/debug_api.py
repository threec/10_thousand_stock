"""Debug: Inspect Xueqiu API response structure for pagination."""
import sys, os, json, time
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

USER_ID = "7845696728"

def log(msg):
    try: print(msg)
    except: print(msg.encode('ascii', errors='replace').decode('ascii'))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='zh-CN',
    )
    page = context.new_page()

    log("[*] Loading page...")
    page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    log(f"Title: {page.title()}")

    # Try different API endpoints and parameters
    tests = [
        {"url": f"/v4/statuses/user_timeline.json?user_id={USER_ID}&page=1&type=0", "desc": "page=1, type=0 (all)"},
        {"url": f"/v4/statuses/user_timeline.json?user_id={USER_ID}&page=1", "desc": "page=1, no type"},
        {"url": f"/v4/statuses/user_timeline.json?user_id={USER_ID}&page=2&type=0", "desc": "page=2, type=0"},
        {"url": f"/v4/statuses/user_timeline.json?user_id={USER_ID}&page=2", "desc": "page=2, no type"},
        {"url": f"/v4/statuses/user_timeline.json?user_id={USER_ID}&page=1&count=50", "desc": "page=1, count=50"},
        {"url": f"/v4/statuses/user_timeline.json?user_id={USER_ID}&max_id=0&count=20", "desc": "max_id=0, count=20"},
    ]

    for test in tests:
        url = test['url']
        desc = test['desc']
        result = page.evaluate("""
            async (url) => {
                try {
                    const response = await fetch('https://xueqiu.com' + url, {
                        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'include',
                    });
                    const status = response.status;
                    const text = await response.text();
                    return { status, text: text.substring(0, 2000) };
                } catch (e) {
                    return { error: e.message };
                }
            }
        """, url)

        log(f"\n{'='*60}")
        log(f"[TEST] {desc}")
        if result.get('error'):
            log(f"  ERROR: {result['error']}")
        else:
            log(f"  Status: {result['status']}")
            log(f"  Response (first 2000 chars):\n{result['text'][:2000]}")

        time.sleep(0.5)

    # Also try to capture the actual network request from infinite scroll
    log(f"\n{'='*60}")
    log("[*] Capturing real scroll-triggered API calls...")

    captured_urls = []
    def capture_request(request):
        url = request.url
        if 'statuses/user_timeline' in url or 'statuses' in url:
            captured_urls.append(url)
            log(f"  Captured: {url}")

    page.on('request', capture_request)

    # Scroll down
    for i in range(5):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

    log(f"\n[*] Captured {len(captured_urls)} API URLs:")
    for u in captured_urls:
        log(f"  {u}")

    browser.close()
