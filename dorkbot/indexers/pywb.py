import json
import logging
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from itertools import repeat
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen


def run(options):
    required = ["server", "domain"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    source = __name__.split(".")[-1]

    retries = int(options.get("retries", "10"))
    threads = int(options.get("threads", "10"))
    server = options["server"]
    domain = options["domain"]
    index = options.get("index", "")
    url_filter = options.get("filter", "")
    cdx_api_suffix = options.get("cdx_api_suffix", "/cdx")

    data = {}
    data["url"] = "*.%s" % domain
    data["fl"] = "url"
    data["output"] = "json"
    if url_filter:
        data["filter"] = url_filter

    if not index:
        index = get_latest_index(server, retries)
    base_url = f"{server}/{index}{cdx_api_suffix}"
    num_pages = get_num_pages(base_url, data, retries)

    source += f",index:{index}"

    results = get_results(base_url, data, retries, num_pages, threads, domain)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results, source


def get_latest_index(server, retries):
    url = f"{server}/collinfo.json"

    logging.debug("Fetching latest index list")
    for i in range(retries):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
        except (HTTPError, IncompleteRead) as e:
            if i == retries - 1:
                logging.error("Failed to fetch index list (retries exceeded) - %s", str(e))
                sys.exit(1)
            else:
                logging.warn("Failed to fetch index list (will retry) - %s", str(e))
                time.sleep(random.randrange(i, 2 ** i))
                continue
        except Exception:
            logging.exception("Failed to fetch index list")
            sys.exit(1)
        break

    fixed = response["fixed"]
    dynamic = response["dynamic"]
    index = fixed[0] if fixed else dynamic[0]
    return index


def get_num_pages(base_url, data, retries):
    data["showNumPages"] = "true"
    url = f"{base_url}?" + urlencode(data)

    logging.debug("Fetching number of pages")
    for i in range(retries):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = json.loads(response_str)
        except (HTTPError, IncompleteRead) as e:
            if i == retries - 1:
                logging.error("Failed to fetch number of pages (retries exceeded) - %s", str(e))
                sys.exit(1)
            else:
                logging.warn("Failed to fetch number of pages (will retry) - %s", str(e))
                time.sleep(random.randrange(i, 2 ** i))
                continue
        except Exception:
            logging.exception("Failed to fetch number of pages")
            sys.exit(1)
        break

    del data["showNumPages"]
    num_pages = response["pages"]
    logging.debug("Got %d pages", num_pages)
    return num_pages


def get_page(base_url, data, retries, page, domain):
    data["page"] = page
    url = f"{base_url}?" + urlencode(data)

    logging.debug("Fetching page %d", page)
    for i in range(retries):
        try:
            response_str = urlopen(url)
            response_str = response_str.read().decode("utf-8")
            response = response_str.splitlines()
        except (HTTPError, IncompleteRead) as e:
            if type(e).__name__ == "HTTPError" and e.code == 404:
                response_str = e.read().decode("utf-8")
                if "message" in response_str:
                    response = json.loads(response_str)
                    message = response["message"]
                else:
                    message = str(e)
                logging.warn("Failed to fetch results (page %d) - %s", page, message)
                return set()
            elif i == retries - 1:
                logging.error("Failed to fetch results (page %d, retries exceeded) - %s", page, str(e))
                sys.exit(1)
            else:
                logging.warn("Failed to fetch results (page %d, will retry) - %s", page, str(e))
                time.sleep(random.randrange(i, 2 ** i))
                continue
        except Exception:
            logging.exception("Failed to fetch results (page %d)", page)
            sys.exit(1)
        break

    pattern = "http[s]?://([^/]*\.)*" + domain + "/"
    domain_url = re.compile(pattern)

    results = set()
    for item in response:
        item_json = json.loads(item)
        url = urlparse(item_json["url"].strip()).geturl()
        if domain_url.match(url):
            results.add(url)

    return results


def get_results(base_url, data, retries, num_pages, num_threads, domain):
    try:
        executor = ThreadPoolExecutor(max_workers=num_threads)
        threads = executor.map(get_page, repeat(base_url), repeat(data), repeat(retries), range(num_pages), repeat(domain))
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
