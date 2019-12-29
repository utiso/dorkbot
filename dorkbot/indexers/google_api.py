from urllib.request import urlopen
from urllib.parse import urlencode,urlparse
from urllib.error import HTTPError
import json
import sys
import time
import logging

def run(args):
    required = ["key", "engine", "query"]
    for r in required:
        if r not in args:
            logging.error("%s must be set", r)
            sys.exit(1)

    results = get_results(args)
    return results

def get_results(args):
    data = {}
    data["key"] = args["key"]
    data["cx"] = args["engine"]
    data["q"] = args["query"]
    data["num"] = 10
    data["start"] = 1

    if "domain" in args:
        data["siteSearch"] = args["domain"]

    results = []
    while True:
        items = issue_request(data)
        data["start"] += data["num"]
        if not items:
            break
        results.extend(items)

    return results

def issue_request(data):
    url = "https://www.googleapis.com/customsearch/v1?" + urlencode(data)
    while True:
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
            break
        except HTTPError as e:
            response_str = e.read().decode("utf-8")
            response = json.loads(response_str)
            if "Invalid Value" in response["error"]["message"]:
                return []
            logging.error("Failed to fetch results - %d %s", response["error"]["code"], response["error"]["message"])
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
                sys.exit(1)

    items = []
    for request in response["queries"]["request"]:
        if int(request["totalResults"]) == 0:
            return []
        for item in response["items"]:
            items.append(urlparse(item["link"]).geturl())

    return items

