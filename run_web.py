#!/usr/bin/env python3

from gevent.pywsgi import WSGIServer

import server

if __name__ == "__main__":
    http_server = WSGIServer(('', 5000), server.app)
    http_server.serve_forever()
