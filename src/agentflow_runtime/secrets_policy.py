"""Fail-closed scoped secret access and DNS-pinned HTTPS egress.

Never expose this broker directly to untrusted plugins. External agents in
restricted tenant mode remain disabled; the broker is for trusted operators.
"""
import hashlib
import http.client
import ipaddress
import os
import re
import socket
import ssl
from urllib.parse import urlsplit

NAME=re.compile(r'[A-Z][A-Z0-9_]{1,63}\Z')
DNS_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')

class ScopedSecrets:
    def __init__(self, allowed_names):
        if not isinstance(allowed_names,(list,tuple,set)) or any(not isinstance(x,str) or not NAME.fullmatch(x) for x in allowed_names):
            raise ValueError('invalid secret allowlist')
        self._allowed=frozenset(allowed_names)
    def get(self, name):
        if name not in self._allowed:raise PermissionError('secret not authorized')
        value=os.environ.get(name)
        if not value:raise KeyError('configured secret is missing')
        return value
    def fingerprint(self,name):
        # Non-secret diagnostic: truncated HMAC-independent hash is NOT a credential.
        return hashlib.sha256(self.get(name).encode()).hexdigest()[:12]

class EgressPolicy:
    """Exact hostname HTTPS allowlist; resolution must be public IP only.

    IP address pinning prevents a second DNS lookup after policy evaluation.
    No redirects, cookies, proxy variables or unaudited HTTP libraries are used.
    """
    def __init__(self, hostnames):
        if not isinstance(hostnames,(list,tuple,set)) or not hostnames:
            raise ValueError('explicit hostname allowlist required')
        self.hostnames=frozenset(hostnames)
        for h in self.hostnames:
            if (not isinstance(h,str) or len(h)>253 or h!=h.lower()
                    or not all(DNS_LABEL.fullmatch(label) for label in h.split('.'))):
                raise ValueError('invalid hostname')
    def resolve(self,url):
        # Refuse ambiguous request targets before DNS or socket creation. In
        # particular, never interpolate raw whitespace/control bytes into HTTP/1.1.
        if (not isinstance(url, str) or not url.isascii() or
                any(ord(c) <= 32 or ord(c) == 127 or c == '\\' for c in url)):
            raise PermissionError('unsafe HTTPS URL')
        try:
            parsed=urlsplit(url)
            port=parsed.port
        except ValueError as exc:
            raise PermissionError('invalid HTTPS URL') from exc
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.fragment or port not in (None,443):
            raise PermissionError('only direct HTTPS on port 443 is allowed')
        host=parsed.hostname
        if host not in self.hostnames:raise PermissionError('host not allowlisted')
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        ips=[]
        for addr in addresses:
            ip=ipaddress.ip_address(addr[4][0])
            if not ip.is_global:raise PermissionError('non-public resolved address refused')
            ips.append(str(ip))
        if not ips:raise PermissionError('no usable address')
        return host,ips[0],parsed.path or '/',parsed.query
    def get(self,url,*,timeout=8,max_bytes=1_000_000):
        if not 0<timeout<=30 or not 1<=max_bytes<=2_000_000:raise ValueError('invalid bounds')
        host,ip,path,query=self.resolve(url)
        # TLS uses the validated hostname for SNI and certificate verification.
        # The socket is connected to the approved IP rather than re-resolving.
        conn=socket.create_connection((ip,443),timeout=timeout)
        try:
            with ssl.create_default_context().wrap_socket(conn,server_hostname=host) as secure:
                secure.settimeout(timeout)
                request_path=path+('?' + query if query else '')
                http=(f'GET {request_path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nAccept: application/json\r\n\r\n').encode('ascii')
                secure.sendall(http)
                response=http.client.HTTPResponse(secure);response.begin()
                if response.status<200 or response.status>=300:raise RuntimeError('egress response failed')
                if response.getheader('Content-Encoding') not in (None,'identity'):
                    raise RuntimeError('compressed responses disabled for bounded reads')
                data=response.read(max_bytes+1)
                if len(data)>max_bytes:raise RuntimeError('egress response too large')
                return data
        finally:
            conn.close()
