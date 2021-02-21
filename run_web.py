#!/usr/bin/env python3
import logging
import sys

from gevent.pywsgi import WSGIServer

import server

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logging.getLogger("sqlitedict").setLevel(logging.WARNING)
    http_server = WSGIServer(('', 5000), server.app)
    http_server.serve_forever()
