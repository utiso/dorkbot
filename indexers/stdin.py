import sys
from io import open
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(args):
    with open(sys.stdin.fileno(), encoding="utf-8") as stdin:
        return [urlparse(item.strip()).geturl() for item in stdin]
