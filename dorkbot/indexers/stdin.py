import sys
import io
from urllib.parse import urlparse

def run(args):
    with io.open(sys.stdin.fileno(), encoding="utf-8") as stdin:
        results = [urlparse(item.strip()).geturl() for item in stdin]
        for result in results:
            logging.debug(result)
        logging.info("Fetched %d results", len(results))
        return results
