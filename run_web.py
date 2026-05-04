"""
Start the web dashboard server.
Usage: python run_web.py [--port 8080]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == '__main__':
    from web.server import run
    run()
