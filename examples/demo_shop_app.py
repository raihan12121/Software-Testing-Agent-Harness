"""Sandboxed Local Multi-Page Web Application Demo (Shopping Cart).

Used for explore mode validation and end-to-end multi-page testing.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class ShopAppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            body = """<!DOCTYPE html>
<html>
<head><title>Demo Shop - Catalog</title></head>
<body>
  <h1>Product Catalog</h1>
  <div class="product" id="prod-1">
    <h2>Mechanical Keyboard</h2>
    <a href="/product/1" id="link-prod-1">View Details</a>
    <a href="/cart?add=1" id="link-add-cart">Add to Cart</a>
  </div>
  <a href="/cart" id="nav-cart">Shopping Cart (0)</a>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        elif path == "/product/1":
            body = """<!DOCTYPE html>
<html>
<head><title>Mechanical Keyboard</title></head>
<body>
  <h1>Mechanical Keyboard</h1>
  <p class="price">$120.00</p>
  <p class="description">Tactile mechanical keyboard with RGB backlighting.</p>
  <a href="/cart?add=1" id="btn-add">Add to Cart</a>
  <a href="/" id="nav-home">Back to Catalog</a>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        elif path == "/cart":
            body = """<!DOCTYPE html>
<html>
<head><title>Shopping Cart</title></head>
<body>
  <h1>Your Cart</h1>
  <p>Items: 1 x Mechanical Keyboard ($120.00)</p>
  <a href="/checkout" id="btn-checkout">Proceed to Checkout</a>
  <a href="/" id="btn-continue">Continue Shopping</a>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        elif path == "/checkout":
            body = """<!DOCTYPE html>
<html>
<head><title>Secure Checkout</title></head>
<body>
  <h1>Checkout</h1>
  <form action="/order-confirmation" method="POST">
    <input type="text" name="name" placeholder="Full Name" />
    <button type="submit" id="btn-submit-order">Place Order</button>
  </form>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        elif path == "/explore-subview":
            body = """<!DOCTYPE html>
<html><head><title>Discovered Flow</title></head><body><h1>Exploration Subview</h1></body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress noisy HTTP logs during testing
        pass


def run_server(port: int = 8899) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), ShopAppHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    import time
    server = run_server(8899)
    print("Demo Shop server running on http://127.0.0.1:8899")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
