import sys
import io
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(args):
    with io.open(sys.stdin.fileno(), encoding="utf-8") as stdin:
        return [urlparse(item.strip()).geturl() for item in stdin]
