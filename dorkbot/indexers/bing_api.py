import json
import logging
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Searches bing.com")
    module_group.add_argument("--key", required=True, \
                          help="API key")
    module_group.add_argument("--query", required=True, \
                          help="search query")


def run(args):
    source = __name__.split(".")[-1]
    results = get_results(args.key, args.query)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results, source


def get_results(key, query):
    data = {"q": query,
            "count": 50,
            "offset": 0}

    results = []
    while data["offset"] < 1000:
        items = issue_request(data, key)
        data["offset"] += data["count"]
        if not items:
            break
        results.extend(items)

    return results


def issue_request(data, key):
    url = "https://api.bing.microsoft.com/v7.0/search?" + urlencode(data)
    while True:
        try:
            r = Request(url)
            r.add_header("Ocp-Apim-Subscription-Key", key)
            response_str = urlopen(r)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
            break
        except HTTPError as e:
            response_str = e.read().decode("utf-8")
            response = json.loads(response_str)
            if e.code == 429:
                time.sleep(0.5)

    if "webPages" not in response or response["webPages"]["totalEstimatedMatches"] < data["offset"]:
        return []

    return [urlparse(item["url"].strip()).geturl() for item in response["webPages"]["value"]]
