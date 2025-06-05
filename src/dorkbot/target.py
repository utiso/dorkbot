#!/usr/bin/env python3
if __package__:
    from dorkbot.util import generate_hash, parse_host, resolve_ip
else:
    from util import generate_hash, parse_host, resolve_ip


class Target:
    def __init__(self, url):
        self.url = url
        self._host = None
        self._ip = None
        self._hash = None

    def get_host(self):
        if not self._host:
            self._host = parse_host(self.url)
        return self._host

    def get_ip(self):
        if not self._ip:
            host = self.get_host()
            self._ip = resolve_ip(host)
        return self._ip

    def get_hash(self):
        if not self._hash:
            self._hash = generate_hash(self.url)
        return self._hash
