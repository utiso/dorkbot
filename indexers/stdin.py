import sys
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(options):
    results = []

    for url in sys.stdin:
        result = urlparse(url.rstrip('\n').encode("utf-8"))
        results.append(result)

    return results

