from urllib.request import Request, urlopen
from urllib.parse import urlencode,urlparse
from urllib.error import HTTPError
import json
import sys
import time
import logging

def run(options):
    required = ["key", "query"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    results = get_results(options)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results

def get_results(options):
    data = {"q": options["query"],
            "count": 50,
            "offset": 0}

    results = []
    while data["offset"] < 1000:
        items = issue_request(data, options["key"])
        data["offset"] += data["count"]
        if not items:
            break
        results.extend(items)

    return results

def issue_request(data, key):
    url = "https://api.cognitive.microsoft.com/bing/v7.0/search?" + urlencode(data)
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

