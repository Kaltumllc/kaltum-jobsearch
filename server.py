from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import subprocess


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Kaltum Job Search Assistant is running.")
            return

        if self.path == "/followup":
            result = subprocess.run(
                ["python", "app.py", "followup"],
                capture_output=True,
                text=True
            )

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(result.stdout.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Kaltum Job Search web service running on port {port}")
    server.serve_forever()