"""Start the local website and open the browser only after it is ready."""
import argparse
import threading
import time
import webbrowser
from pathlib import Path

import requests
import uvicorn

from forecasting.service import load_model


def ready(url):
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(url + '/api/status', timeout=1)
        return response.status_code == 200 and response.json().get('mode') == 'local'
    except (requests.RequestException, ValueError):
        return False


def open_when_ready(url):
    for _ in range(100):
        if ready(url):
            webbrowser.open(url)
            return
        time.sleep(.2)


def main():
    parser = argparse.ArgumentParser(description='NBA Eval Personal: free data, local storage.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a port from 1024 to 65535.')
    url = f'http://127.0.0.1:{args.port}'
    if ready(url):
        print(f'NBA Eval is already running at {url}')
        if not args.no_browser:
            webbrowser.open(url)
        return
    try:
        load_model()
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Forecast model unavailable: {exc}\nSee docs/PERSONAL_LOCAL.md for setup.\n')
    if not (Path(__file__).resolve().parents[1] / 'frontend' / 'dist-personal' / 'personal.html').exists():
        parser.exit(1, 'Frontend not built. Run npm install and npm run build:personal in frontend/, then launch again.\n')
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    print(f'NBA Eval Personal: {url} — Ctrl+C to stop.')
    uvicorn.run('personal.app:app', host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
