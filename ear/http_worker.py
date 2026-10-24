"""Isolated HTTPS GET transport. Public destinations, pinned DNS, verified TLS."""
import base64
from hashlib import sha256
import http.client
import ipaddress
import json
import socket
import ssl
import sys
from .actions import validate_spec


def retrieve(spec):
    parts = validate_spec(spec)
    host = parts.hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global
                            or ipaddress.ip_address(a[4][0]).is_multicast
                            or ipaddress.ip_address(a[4][0]).is_reserved for a in addresses):
        raise ValueError('Destination must resolve only to public IP addresses')
    address = addresses[0][4][0]
    # Connect to the checked numeric address; do not resolve the hostname again.
    raw = socket.create_connection((address, 443), timeout=5)
    conn = http.client.HTTPSConnection(host, timeout=5)
    try:
        conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        target = parts.path or '/'
        if parts.query:
            target += '?' + parts.query
        conn.request('GET', target, headers={'User-Agent': 'EAR-research/0.2', 'Accept-Encoding': 'identity', 'Connection': 'close'})
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise ValueError(f'HTTP {response.status}; redirects are not followed')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise ValueError('Compressed responses are not supported')
        body = response.read(spec['max_bytes'] + 1)
        if len(body) > spec['max_bytes']:
            raise ValueError('Response exceeded approved byte limit')
        return {'http_status': response.status, 'content_type': response.getheader('Content-Type', ''),
                'body_base64': base64.b64encode(body).decode('ascii'), 'sha256': sha256(body).hexdigest()}
    finally:
        conn.close()
        raw.close()


def main():
    try:
        spec = json.loads(sys.stdin.read(8192))
        print(json.dumps(retrieve(spec)))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
