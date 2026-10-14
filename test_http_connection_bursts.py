"""Network admission regression: a PWA burst must not fill a five-slot backlog."""
import socket
import unittest
from http.server import BaseHTTPRequestHandler
from server import BobHTTPServer

class ConnectionBurstTests(unittest.TestCase):
    def test_session_service_uses_same_burst_protection(self):
        import push_server
        self.assertIs(push_server.BobHTTPServer, BobHTTPServer)

    def test_parallel_connections_queue_before_handler_can_run(self):
        clients=[]
        with BobHTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler) as server:
            try:
                for _ in range(24):
                    clients.append(socket.create_connection(server.server_address,timeout=1))
                accepted,address=server.get_request()
                try:
                    self.assertEqual(accepted.gettimeout(),30)
                finally:
                    accepted.close()
            finally:
                for client in clients:client.close()

if __name__=='__main__':unittest.main()
