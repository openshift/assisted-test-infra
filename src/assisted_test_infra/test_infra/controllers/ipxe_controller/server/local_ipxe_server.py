#!/usr/bin/env python3

import os
from http.server import CGIHTTPRequestHandler, HTTPServer

ip = os.getenv("SERVER_IP", "192.168.122.1")
port = int(os.getenv("SERVER_PORT", 8500))

# Make sure the server is hosting the iPXE scripts directory
dir = f"{os.getcwd()}/ipxe_scripts"
os.chdir(dir)

# Create server object
server_object = HTTPServer(server_address=(ip, port), RequestHandlerClass=CGIHTTPRequestHandler)
# Start the web server
server_object.serve_forever(poll_interval=1.5)
