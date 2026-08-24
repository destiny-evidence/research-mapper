"""Serve the demo UI, proxying /api to the research-mapper API.

Disposable. It exists because the API has no CORS and the demo isn't worth adding any.
"""

import argparse
import json
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent


class Handler(SimpleHTTPRequestHandler):
    api = "http://127.0.0.1:8080"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("GET")
            return
        super().do_GET()

    def do_POST(self) -> None:
        self._proxy("POST")

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("content-length") or 0)
        request = urllib.request.Request(
            self.api + self.path.removeprefix("/api"),
            data=self.rfile.read(length) if length else None,
            method=method,
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                self._relay(response.status, response.read())
        except urllib.error.HTTPError as error:
            # 4xx bodies carry the message the UI shows the user, so pass them through.
            self._relay(error.code, error.read())
        except urllib.error.URLError as error:
            body = json.dumps({"detail": f"API unreachable: {error.reason}"})
            self._relay(502, body.encode())

    def _relay(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        """Quiet. The interesting log is the worker's."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api", default=Handler.api)
    arguments = parser.parse_args()
    Handler.api = arguments.api.rstrip("/")
    print(f"demo UI on http://{arguments.host}:{arguments.port}  ->  {Handler.api}")
    ThreadingHTTPServer((arguments.host, arguments.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
