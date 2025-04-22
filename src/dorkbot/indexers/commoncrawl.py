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
    module_group = parser.add_argument_group(__name__, f"Searches commoncrawl.org crawl data")
    populate_general_options(args, module_group)
    populate_pywb_options(args, module_group)
    for action in module_group._actions:
        if action.dest == "server":
            action.default = "https://index.commoncrawl.org/"
        elif action.dest == "cdx_api_suffix":
            action.default = "-index"
        elif action.dest == "field":
            action.default = "url"
        else:
            continue
        action.help = argparse.SUPPRESS


def run(args):
    results, source = run_pywb(args)
    return results, source
