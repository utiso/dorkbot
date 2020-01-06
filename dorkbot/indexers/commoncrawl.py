from urllib.request import urlopen
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
import json
import sys
import re
import logging

def run(options):
    required = ["domain"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    domain = options["domain"]
    index = options.get("index", get_latest_index())
    url_filter = options.get("filter", "")

    results = get_results(domain, index, url_filter)
    return results

def get_latest_index():
    url = "https://index.commoncrawl.org/collinfo.json"

    try:
        response_str = urlopen(url)
        response_str = response_str.read().decode("utf-8")
        response = json.loads(response_str)
    except HTTPError as e:
        logging.error("Failed to fetch index list - %s", str(e))
        sys.exit(1)

    index = response[0]["id"]
    return index

def get_num_pages(index, data):
    data["showNumPages"] = "true"
    url = "https://index.commoncrawl.org/" + index + "-index?" + urlencode(data)

    try:
        response_str = urlopen(url)
        response_str = response_str.read().decode("utf-8")
        response = json.loads(response_str)
    except HTTPError as e:
        logging.error("Failed to fetch number of pages - %s", str(e))
        sys.exit(1)

    num_pages = response["pages"]
    return num_pages

def get_results(domain, index, url_filter):
    data = {}
    data["url"] = "*.%s" % domain
    data["fl"] = "url"
    data["output"] = "json"
    if url_filter:
        data["filter"] = url_filter

    num_pages = get_num_pages(index, data)
    del data["showNumPages"]

    results = []
    for page in range(0, num_pages):
        data["page"] = page
        url = "https://index.commoncrawl.org/" + index + "-index?" + urlencode(data)
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = response_str.splitlines()
        except HTTPError as e:
            logging.error("Failed to fetch results - %s", str(e))
            sys.exit(1)

        pattern = "http[s]?://([^/]*\.)*" + domain + "/"
        domain_url = re.compile(pattern)

        for item in response:
            item_json = json.loads(item)
            url = urlparse(item_json["url"].strip()).geturl()
            if domain_url.match(url):
                results.append(url)

    return results

