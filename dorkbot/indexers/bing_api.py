from __future__ import print_function
try:
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode,urlparse
    from urllib.error import HTTPError
except ImportError:
    from urllib import urlencode
    from urllib2 import Request, urlopen, HTTPError
    from urlparse import urlparse
import json
import sys
import time

def run(args):
    required = ["key", "query"]
    for r in required:
        if r not in args:
            print("ERROR: %s must be set" % r, file=sys.stderr)
            sys.exit(1)

    results = get_results(args)
    return results

def get_results(args):
    data = {"q": args["query"],
            "count": 50,
            "offset": 0}

    results = []
    while data["offset"] < 1000:
        items = issue_request(data, args["key"])
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

