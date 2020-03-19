from urllib.request import urlopen
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
from http.client import IncompleteRead
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
import json
import sys
import re
import logging
import time
import random

def run(options):
    required = ["domain"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    retries = int(options.get("retries", "10"))
    threads = int(options.get("threads", "1"))
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

    num_pages = get_num_pages(data, retries)
 
    results = get_results(domain, data, num_pages, threads, retries)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results

def get_num_pages(data, retries):
    data["showNumPages"] = "true"
    url = "https://web.archive.org/cdx/search/cdx?" + urlencode(data)

    for i in range(retries):
        try:
            response = urlopen(url)
            response = response.read().decode("utf-8")
        except (HTTPError, IncompleteRead) as e:
            if i == retries - 1:
                logging.error("Failed to fetch number of pages (retries exceeded) - %s", str(e))
                sys.exit(1)
            else:
                logging.warn("Failed to fetch number of pages (will retry) - %s", str(e))
                time.sleep(random.randrange(i, 2**i))
                continue
        except Exception:
            logging.exception("Failed to fetch number of pages")
            sys.exit(1)
        break

    del data["showNumPages"]
    num_pages = int(response)
    logging.debug("Got %d pages", num_pages)
    return num_pages

def get_page(domain, data, retries, page):
    data["page"] = page
    url = "https://web.archive.org/cdx/search/cdx?" + urlencode(data)

    logging.debug("Fetching page %d", page)
    for i in range(retries):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
        except (HTTPError, IncompleteRead) as e:
            if i == retries - 1:
                logging.error("Failed to fetch results (page %d, retries exceeded) - %s", page, str(e))
                sys.exit(1)
            else:
                logging.warn("Failed to fetch results (page %d, will retry) - %s", page, str(e))
                time.sleep(random.randrange(i, 2**i))
                continue
        except Exception:
            logging.exception("Failed to fetch results (page %d)", page)
            sys.exit(1)
        break

    pattern = "http[s]?://([^/]*\.)*" + domain + "/"
    domain_url = re.compile(pattern)

    results = set()
    for item in response[1:]:
        url_parsed = urlparse(item[0].strip())
        url_parsed = url_parsed._replace(netloc=url_parsed.hostname)
        url = url_parsed.geturl()
        if domain_url.match(url):
            results.add(url)

    return results

def get_results(domain, data, num_pages, threads, retries):
    try:
        executor = ThreadPoolExecutor(max_workers=threads)
        threads = executor.map(get_page, repeat(domain), repeat(data), repeat(retries), range(num_pages))
    except Exception:
        logging.error("Failed to execute threads")
        sys.exit(1)

    results = set()
    try:
        for result in list(threads):
            results.update(result)
    except Exception:
        logging.exception("Failed to fetch all results")
        sys.exit(1)

    return list(results)

