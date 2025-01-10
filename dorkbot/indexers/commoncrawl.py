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


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Searches commoncrawl.org crawl data")
    module_group.add_argument("--domain", required=True, \
                          help="pull all results for given domain or subdomain")
    module_group.add_argument("--index", \
                          help="search a specific index, e.g. CC-MAIN-2019-22 (default: latest)")
    module_group.add_argument("--filter", \
                          help="query filter to apply to the search")
    module_group.add_argument("--retries", type=int, default=10, \
                          help="number of times to retry fetching results on error")
    module_group.add_argument("--threads", type=int, default=1, \
                          help="number of concurrent requests to commoncrawl.org")


def run(args):
    source = __name__.split(".")[-1]
    data = {}
    data["url"] = "*.%s" % args.domain
    data["fl"] = "url"
    data["output"] = "json"
    if args.filter:
        data["filter"] = args.filter

    if not args.index:
        args.index = get_latest_index(int(args.retries))
    num_pages = get_num_pages(args.index, data, int(args.retries))

    source += f",index:{args.index}"

    results = get_results(args.domain, args.index, data, num_pages, args.threads, args.retries)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results, source


def get_latest_index(retries):
    url = "https://index.commoncrawl.org/collinfo.json"

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

    index = response[0]["id"]
    return index


def get_num_pages(index, data, retries):
    data["showNumPages"] = "true"
    url = "https://index.commoncrawl.org/" + index + "-index?" + urlencode(data)

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


def get_page(domain, index, data, retries, page):
    data["page"] = page
    url = "https://index.commoncrawl.org/" + index + "-index?" + urlencode(data)

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

    pattern = r"http[s]?://([^/.]*\.)*" + domain + "(/|$)"
    domain_url = re.compile(pattern)

    results = set()
    for item in response:
        item_json = json.loads(item)
        url = urlparse(item_json["url"].strip()).geturl()
        if domain_url.match(url):
            results.add(url)

    return results


def get_results(domain, index, data, num_pages, num_threads, retries):
    try:
        executor = ThreadPoolExecutor(max_workers=num_threads)
        threads = executor.map(get_page, repeat(domain), repeat(index), repeat(data), repeat(retries), range(num_pages))
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
