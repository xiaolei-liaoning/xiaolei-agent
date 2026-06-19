#!/usr/bin/env python3
"""简单的HTTP服务器"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <head><title>测试服务器</title></head>
            <body>
                <h1>Hello from Simple Server!</h1>
                <p>这是一个简单的HTTP服务器</p>
                <a href="/api/data">查看API数据</a>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        elif self.path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            data = {"message": "Hello from API", "status": "success"}
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
    
    def log_message(self, format, *args):
        pass  # 禁用日志输出

if __name__ == "__main__":
    server = HTTPServer(('localhost', 8080), SimpleHandler)
    print("服务器启动在 http://localhost:8080")
    print("按 Ctrl+C 停止服务器")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("服务器已停止")
        server.server_close()
