"""Bounded HTTPS fetching with validated, pinned public IP addresses."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit, urlunsplit
from .core import UserError

MAX_BYTES = 512_000


def validate_url(url):
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        raise UserError('Invalid URL or port') from None
    if p.scheme != 'https' or not p.hostname or p.username or p.password or port not in (None, 443):
        raise UserError('Use a public HTTPS URL on port 443 without credentials')
    if len(url) > 2000:
        raise UserError('URL too long')
    return p


def public_address(host):
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise UserError('Public hostname could not be resolved') from None
    ips = {item[4][0] for item in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise UserError('Private, local and reserved network addresses are blocked')
    return sorted(ips)[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        super().__init__(host, timeout=12, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        raw = socket.create_connection((self.ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def fetch(url, check=lambda: None, event=lambda a, s: None, allowed=None):
    initial = validate_url(url)
    redirects = []
    for _ in range(4):
        check()
        p = validate_url(url)
        if p.hostname != initial.hostname:
            raise UserError('Off-site redirect blocked; supply the final website URL')
        # Reapply robots and action-route rules to every redirect BEFORE DNS or HTTP.
        if allowed is not None and not allowed(url):
            raise UserError('URL or redirect destination excluded by crawl policy')
        ip = public_address(p.hostname)
        check()
        conn = PinnedHTTPS(p.hostname, ip)
        try:
            event('public HTTPS GET ' + p.path, 'starting')
            conn.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                         headers={'User-Agent': 'GoalPilotAudit/0.2', 'Accept': 'text/html,application/xml,text/plain'})
            res = conn.getresponse()
            event('public HTTPS GET ' + p.path, 'HTTP ' + str(res.status))
            if res.status in (301, 302, 303, 307, 308):
                location = res.getheader('Location')
                if not location:
                    raise UserError('Redirect has no destination')
                redirects.append({'url': url, 'status': res.status})
                url = urljoin(url, location)
                continue
            body = res.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise UserError('Response exceeds the 512 KB audit limit')
            check()
            return {'url': url, 'status': res.status, 'redirects': redirects,
                    'content_type': res.getheader('Content-Type', ''),
                    'x_robots_tag': res.getheader('X-Robots-Tag', ''),
                    'text': body.decode('utf-8', errors='replace')}
        except (OSError, http.client.HTTPException):
            event('public HTTPS GET ' + p.path, 'network failure; details redacted')
            raise UserError('Network request failed; no page status was confirmed') from None
        finally:
            conn.close()
    raise UserError('Redirect limit reached (possible loop)')
