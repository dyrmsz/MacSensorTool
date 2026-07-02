"""
HTTP endpoint (stdlib only) so other apps -- widgets, menu bar apps,
dashboards, Shortcuts -- can read the sensors as JSON.

    GET /                     index: available sensors + endpoints
    GET /sensors              derived values for every available sensor
    GET /sensors/<name>       derived values for one sensor
    GET /raw/<name>           raw property table for one sensor

Binds to 127.0.0.1 only. CORS is open so local web dashboards can fetch it.
"""

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from macpower import sensors


def _snapshot(mods):
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "sensors": {mod.NAME: mod.derive(mod.read()) for mod in mods},
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200):
        body = json.dumps(obj, indent=2, default=repr).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        try:
            if not parts:
                self._send({
                    "sensors": {
                        mod.NAME: mod.DESCRIPTION
                        for mod in sensors.ALL if mod.available()
                    },
                    "endpoints": ["/sensors", "/sensors/<name>", "/raw/<name>"],
                })
            elif parts == ["sensors"]:
                self._send(_snapshot(sensors.get()))
            elif parts[0] in ("sensors", "raw") and len(parts) == 2:
                mod = sensors.REGISTRY.get(parts[1])
                if mod is None or not mod.available():
                    self._send({"error": f"no such sensor: {parts[1]}"}, 404)
                    return
                raw = mod.read()
                self._send(raw if parts[0] == "raw" else mod.derive(raw))
            else:
                self._send({"error": "not found"}, 404)
        except Exception as e:  # keep the server up on sensor hiccups
            self._send({"error": repr(e)}, 500)

    def log_message(self, fmt, *args):
        pass  # quiet


def serve(port: int):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"macpower serving on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    print(f"  try: curl http://127.0.0.1:{port}/sensors")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
