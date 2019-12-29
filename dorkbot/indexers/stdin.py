import sys
import io
from urllib.parse import urlparse

def run(args):
    with io.open(sys.stdin.fileno(), encoding="utf-8") as stdin:
        return [urlparse(item.strip()).geturl() for item in stdin]
