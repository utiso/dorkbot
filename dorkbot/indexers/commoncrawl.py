from __future__ import print_function
try:
    from urllib.request import urlopen
    from urllib.parse import urlencode, urlparse
    from urllib.error import HTTPError
except ImportError:
    from urllib import urlencode
    from urllib2 import urlopen, HTTPError
    from urlparse import urlparse
import json
import sys

def run(args):
    required = ["domain"]
    for r in required:
        if r not in args:
            print ("ERROR: %s must be set" % r, file=sys.stderr)
            sys.exit(1)

    domain = args["domain"]
    index = args.get("index", get_latest_index())
    url_filter = args.get("filter", "")

    data = {}
    data["url"] = "*.%s" % domain
    data["fl"] = "url"
    data["output"] = "json"
    if url_filter:
        data["filter"] = url_filter
 
    results = get_results(index, data)
    return results

def get_latest_index():
    url = "https://index.commoncrawl.org/collinfo.json"

    try:
        response_str = urlopen(url)
        response_str = response_str.read().decode("utf-8")
        response = json.loads(response_str)
    except HTTPError as e:
        print("error: %s" % str(e), file=sys.stderr)
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
        print("error: %s" % str(e), file=sys.stderr)
        sys.exit(1)

    num_pages = response["pages"]
    return num_pages

def get_results(index, data):
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
            print("error: %s" % str(e), file=sys.stderr)
            sys.exit(1)

        for item in response:
            item_json = json.loads(item)
            url = urlparse(item_json["url"].strip()).geturl()
            results.append(url)

    return results

