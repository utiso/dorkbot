import io
import logging
import sys
from urllib.parse import urlparse


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Accepts urls from stdin, one per line")


def run(args):
    source = __name__.split(".")[-1]
    with io.open(sys.stdin.fileno(), encoding="utf-8") as stdin:
        results = [urlparse(item.strip()).geturl() for item in stdin]

        for result in results:
            logging.debug(result)
        logging.info("Fetched %d results", len(results))
        return results, source
