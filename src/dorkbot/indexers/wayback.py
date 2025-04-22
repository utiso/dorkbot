import argparse
import json
import logging
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from itertools import repeat
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

if __package__:
    from .pywb import populate_pywb_options, run_pywb
    from .general import populate_general_options
else:
    from indexers.pywb import populate_pywb_options
    from indexers.general import populate_general_options


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Searches archive.org crawl data")
    populate_general_options(args, module_group)
    populate_pywb_options(args, module_group)
    for action in module_group._actions:
        if action.dest == "server":
            action.default = "https://web.archive.org/"
        elif action.dest == "cdx_api_suffix":
            action.default = "/cdx/search/cdx"
        elif action.dest == "field":
            action.default = "original"
        else:
            continue
        action.help = argparse.SUPPRESS
    module_group.add_argument("--from", dest="from_", metavar="FROM",
                              help="beginning timestamp")
    module_group.add_argument("--to",
                              help="end timestamp")


def run(args):
    source = __name__.split(".")[-1]
    data = {"collapse": "urlkey"}

    if args.from_:
        data["from"] = args.from_
        source += f",from:{args.from_}"
    if args.to:
        data["to"] = args.to
        source += f",to:{args.to}"

    results, source = run_pywb(args, data, source)
    return results, source
