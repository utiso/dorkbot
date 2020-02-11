from urllib.request import urlopen
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
import json
import sys
import logging

def run(options):
    required = ["domain"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    domain = options["domain"]
    time_from = options.get("from", "")
    time_to = options.get("to", "")
    url_filter = options.get("filter", "")

    data = {}
    data["url"] = "*.%s" % domain
    data["fl"] = "original"
    data["output"] = "json"
    if url_filter:
        data["filter"] = url_filter
    if time_from:
        data["from"] = time_from
    if time_to:
        data["to"] = time_to
 
    results = get_results(data, domain)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results

def get_num_pages(data):
    data["showNumPages"] = "true"
    url = "https://web.archive.org/cdx/search/cdx?" + urlencode(data)

    try:
        response = urlopen(url)
        response = response.read().decode("utf-8")
    except HTTPError as e:
        logging.error("Failed to fetch number of pages - %s", str(e))
        sys.exit(1)

    num_pages = int(response)
    return num_pages

def get_results(data, domain):
    num_pages = get_num_pages(data)
    del data["showNumPages"]

    results = []
    for page in range(0, num_pages):
        data["page"] = page
        url = "https://web.archive.org/cdx/search/cdx?" + urlencode(data)
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
        except HTTPError as e:
            logging.error("Failed to fetch results - %s", str(e))
            sys.exit(1)

        for item in response[1:]:
            parsed = urlparse(item[0].strip())
            if parsed.hostname.endswith(domain):
                parsed = parsed._replace(netloc=parsed.hostname)
                url = parsed.geturl()
                results.append(url)

    return results

