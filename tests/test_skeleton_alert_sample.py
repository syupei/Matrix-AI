"""Loopback-only example of health, fault injection, and delivery of a correlated alert."""
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread
import unittest


@contextmanager
def serve(handler):
    with HTTPServer(('127.0.0.1', 0), handler) as server:
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join()


class SampleHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body):
        self.send_response(status)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


def probe(port, path, request_id):
    connection = HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        connection.request('GET', path, headers={'X-Request-ID': request_id})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class SkeletonAlertSample(unittest.TestCase):
    def test_request_failure_reaches_loopback_receiver(self):
        events, receipts = [], []

        class Receiver(SampleHandler):
            def do_POST(self):
                event = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                receipts.append(event)
                self.respond(202, {'accepted': event['request_id']})

        with serve(Receiver) as receiver_port:
            class Skeleton(SampleHandler):
                def do_GET(self):
                    if self.path == '/health':
                        self.respond(200, {'status': 'ok'})
                        return
                    if self.path != '/test/inject':
                        self.respond(404, {'status': 'unknown route'})
                        return
                    event = {'request_id': self.headers['X-Request-ID'],
                             'status': 503, 'reason': 'synthetic_fault'}
                    events.append(event)
                    receiver = HTTPConnection('127.0.0.1', receiver_port, timeout=3)
                    try:
                        receiver.request('POST', '/alerts', json.dumps(event),
                                         {'Content-Type': 'application/json'})
                        response = receiver.getresponse()
                        if response.status == 202:
                            events.append(json.loads(response.read()))
                    finally:
                        receiver.close()
                    self.respond(503, {'request_id': event['request_id']})

            with serve(Skeleton) as service_port:
                self.assertEqual((200, {'status': 'ok'}),
                                 probe(service_port, '/health', 'healthy'))
                self.assertEqual([], receipts)
                self.assertEqual((503, {'request_id': 'skeleton-test'}),
                                 probe(service_port, '/test/inject', 'skeleton-test'))
                self.assertEqual((200, {'status': 'ok'}),
                                 probe(service_port, '/health', 'post-injection'))

        self.assertEqual([{'request_id': 'skeleton-test', 'status': 503,
                           'reason': 'synthetic_fault'}], receipts)
        self.assertEqual([receipts[0], {'accepted': 'skeleton-test'}], events)


if __name__ == '__main__':
    unittest.main()
