from urllib.request import urlopen
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
import json
import sys
import re
import logging
import time

def run(options):
    required = ["domain"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    retries = int(options.get("retries", "10"))
    threads = int(options.get("threads", "10"))
    domain = options["domain"]
    index = options.get("index", "")
    url_filter = options.get("filter", "")

    data = {}
    data["url"] = "*.%s" % domain
    data["fl"] = "url"
    data["output"] = "json"
    if url_filter:
        data["filter"] = url_filter

    if not index:
        index = get_latest_index(retries)
    num_pages = get_num_pages(index, data, retries)

    results = get_results(domain, index, data, num_pages, threads, retries)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results

def get_latest_index(retries):
    url = "https://index.commoncrawl.org/collinfo.json"

    logging.debug("Fetching latest index list")
    for i in range(retries + 1):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
        except HTTPError as e:
            if e.code == 504 or e.code == 503:
                if i == retries:
                    logging.error("Failed to fetch index list (retries exceeded) - %s", str(e))
                    sys.exit(1)
                else:
                    logging.warn("Failed to fetch index list (will retry) - %s", str(e))
                    time.sleep(1)
                continue
            else:
                raise
        except Exception:
            logging.exception("Failed to fetch index list")
            sys.exit(1)
        break

    index = response[0]["id"]
    return index

def get_num_pages(index, data, retries):
    data["showNumPages"] = "true"
    url = "https://index.commoncrawl.org/" + index + "-index?" + urlencode(data)

    logging.debug("Fetching number of pages")
    for i in range(retries + 1):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
        except HTTPError as e:
            if e.code == 504 or e.code == 503:
                if i == retries:
                    logging.error("Failed to fetch number of pages (retries exceeded) - %s", str(e))
                    sys.exit(1)
                else:
                    logging.warn("Failed to fetch number of pages (will retry) - %s", str(e))
                    time.sleep(1)
                continue
            else:
                raise
        except Exception:
            logging.error("Failed to fetch number of pages")
            sys.exit(1)
        break

    del data["showNumPages"]
    num_pages = response["pages"]
    logging.debug("Got %d pages", num_pages)
    return num_pages

def get_page(domain, index, data, retries, page):
    data["page"] = page
    url = "https://index.commoncrawl.org/" + index + "-index?" + urlencode(data)

    logging.debug("Fetching page %d", page)
    for i in range(retries + 1):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = response_str.splitlines()
        except HTTPError as e:
            if e.code == 504 or e.code == 503:
                if i == retries:
                    logging.error("Failed to fetch results (page %d, retries exceeded) - %s", page, str(e))
                    sys.exit(1)
                else:
                    logging.warn("Failed to fetch results (page %d, will retry) - %s", page, str(e))
                    time.sleep(1)
                continue
            else:
                raise
        except Exception:
            logging.exception("Failed to fetch results (page %d)", page)
            sys.exit(1)
        break

    pattern = "http[s]?://([^/]*\.)*" + domain + "/"
    domain_url = re.compile(pattern)

    results = []
    for item in response:
        item_json = json.loads(item)
        url = urlparse(item_json["url"].strip()).geturl()
        if domain_url.match(url):
            results.append(url)

    return results

def get_results(domain, index, data, num_pages, threads, retries):
    try:
        executor = ThreadPoolExecutor(max_workers=threads)
        threads = executor.map(get_page, repeat(domain), repeat(index), repeat(data), repeat(retries), range(num_pages))
    except Exception:
        logging.error("Failed to execute threads")
        sys.exit(1)

    results = []
    try:
        for result in list(threads):
            results.extend(result)
    except Exception:
        logging.exception("Failed to fetch all results")
        sys.exit(1)

    return results

