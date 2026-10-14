"""Shared connection admission for Bob web and session/push services."""
from http.server import ThreadingHTTPServer

class BobHTTPServer(ThreadingHTTPServer):
    # Python 3.12 defaults to only five pending TCP connections. Parallel PWA
    # refreshes can exhaust that queue before the login handler is even reached.
    request_queue_size = 128

    def get_request(self):
        connection, address = super().get_request()
        # A client that never finishes its headers must not retain a thread forever.
        connection.settimeout(30)
        return connection, address

