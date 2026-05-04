"""HTTP server for the stock dashboard."""
import http.server, os, webbrowser

PORT = 8080
WEB_DIR = r"D:\stock\data\web"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

server = http.server.HTTPServer(('127.0.0.1', PORT), Handler)
url = f"http://127.0.0.1:{PORT}"
print(f"\n  Dashboard: {url}")
print(f"  Ctrl+C to stop\n")
webbrowser.open(url)
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\nStopped.")
    server.shutdown()
