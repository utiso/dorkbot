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
    module_group = parser.add_argument_group(__name__, "Searches archive.org crawl data")
    module_group.add_argument("--domain", required=True, \
                          help="pull all results for given domain or subdomain")
    module_group.add_argument("--filter", \
                          help="query filter to apply to the search")
    module_group.add_argument("--from", dest="from_", metavar="FROM", \
                          help="beginning timestamp")
    module_group.add_argument("--to", \
                          help="end timestamp")
    module_group.add_argument("--retries", type=int, default=10, \
                          help="number of times to retry fetching results on error")
    module_group.add_argument("--threads", type=int, default=1, \
                          help="number of concurrent requests to wayback.org")


def run(args):
    source = __name__.split(".")[-1]
    data = {}
    data["url"] = "*.%s" % args.domain
    data["fl"] = "original"
    data["output"] = "json"
    if args.filter:
        data["filter"] = args.filter
    if args.from_:
        data["from"] = args.from_
        source += f",from:{args.from_}"
    if args.to:
        data["to"] = args.to
        source += f",to:{args.to}"

    num_pages = get_num_pages(data, int(args.retries))

    results = get_results(args.domain, data, num_pages, args.threads, args.retries)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results, source


def get_num_pages(data, retries):
    data["showNumPages"] = "true"
    url = "https://web.archive.org/cdx/search/cdx?" + urlencode(data)

    for i in range(retries):
        try:
            response = urlopen(url)
            response = response.read().decode("utf-8")
        except (HTTPError, IncompleteRead) as e:
            if e.code == 400:
                response = "1"
            elif i == retries - 1:
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
                time.sleep(random.randrange(i, 2 ** i))
                continue
        except Exception:
            logging.exception("Failed to fetch results (page %d)", page)
            sys.exit(1)
        break

    pattern = "http[s]?://([^/.]*\.)*" + domain + "(/|$)"
    domain_url = re.compile(pattern)

    results = set()
    for item in response[1:]:
        url_parsed = urlparse(item[0].strip())
        url_parsed = url_parsed._replace(netloc=url_parsed.hostname)
        url = url_parsed.geturl()
        if domain_url.match(url):
            results.add(url)

    return results


def get_results(domain, data, num_pages, num_threads, retries):
    try:
        executor = ThreadPoolExecutor(max_workers=num_threads)
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
