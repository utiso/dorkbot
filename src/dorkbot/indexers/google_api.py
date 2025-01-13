import json
import logging
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Searches google.com")
    module_group.add_argument("--key", required=True, \
                          help="API key")
    module_group.add_argument("--engine", required=True, \
                          help="CSE id")
    module_group.add_argument("--query", required=True, \
                          help="search query")
    module_group.add_argument("--domain", \
                          help="limit searches to specified domain")


def run(args):
    source = __name__.split(".")[-1]
    results = get_results(args.key, args.engine, args.query, args.domain)
    return results, source


def get_results(key, engine, query, domain):
    data = {}
    data["key"] = key
    data["cx"] = engine
    data["q"] = query
    data["num"] = 10
    data["start"] = 0

    if domain:
        data["siteSearch"] = domain

    results = []
    while True:
        items = issue_request(data)
        data["start"] += data["num"]
        if not items:
            break
        results.extend(items)

    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results


def issue_request(data):
    url = "https://www.googleapis.com/customsearch/v1?" + urlencode(data)
    while True:
        try:
            logging.debug("Issuing request: %s", url)
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
            break
        except HTTPError as e:
            response_str = e.read().decode("utf-8")
            response = json.loads(response_str)
            if "Invalid Value" in response["error"]["message"]:
                return []
            elif "Request contains an invalid argument" in response["error"]["message"]:
                return []
            for error in response["error"]["errors"]:
                logging.error("%s::%s::%s", error["domain"], error["reason"], error["message"])
            if "User Rate Limit Exceeded" in response["error"]["message"]:
                time.sleep(5)
                continue
            elif "Daily Limit Exceeded" in response["error"]["message"]:
                logging.info("sleeping 1 hour")
                time.sleep(3600)
                continue
            else:
                logging.error("Failed to fetch results - %d %s", response["error"]["code"],
                              response["error"]["message"])
                sys.exit(1)

    items = []
    # https://developers.google.com/custom-search/v1/reference/rest/v1/Search
    if int(response['searchInformation'].get('totalResults', 0)) == 0:
        return []
    for item in response["items"]:
        items.append(urlparse(item["link"]).geturl())

    return items
