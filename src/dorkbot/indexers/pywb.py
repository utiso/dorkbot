import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import IncompleteRead
from itertools import repeat
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

if __package__:
    from .general import populate_general_options
else:
    from indexers.general import populate_general_options


def populate_pywb_options(module_group):
    module_group.add_argument("--server", required=True,
                              help="pywb server url")
    module_group.add_argument("--domain", required=True,
                              help="pull all results for given domain or subdomain")
    module_group.add_argument("--cdx-api-suffix", default="/cdx",
                              help="suffix after index for index api")
    module_group.add_argument("--index",
                              help="search a specific index")
    module_group.add_argument("--field", default="url",
                              help="field (fl) to query")
    module_group.add_argument("--filter",
                              help="query filter to apply to the search")
    module_group.add_argument("--page-size", type=int,
                              help="number of results to request per page")


def populate_parser(_, parser):
    module_group = parser.add_argument_group(__name__, "Searches a given pywb server's crawl data")
    populate_general_options(module_group)
    populate_pywb_options(module_group)


def run(args):
    source = __name__.split(".")[-1]
    results, source = run_pywb(args, source)
    return results, source


def run_pywb(args, source, data={}):
    data["url"] = f"*.{args.domain}"
    data["output"] = "json"
    if args.filter:
        data["filter"] = args.filter

    if args.index is None:
        args.index = get_latest_index(args)

    if args.index:
        source += f",index:{args.index}"
    else:
        args.index = ""

    num_pages = get_num_pages(args, data)

    results = get_results(args, data, num_pages)
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results, source


def issue_request(args, url):
    response = ""
    for i in range(args.retries + 1):
        try:
            logging.debug(url)
            response = urlopen(url).read().decode("utf-8")
        except (HTTPError, IncompleteRead, URLError) as e:
            if type(e).__name__ == "HTTPError" and e.code == 404:
                response_str = e.read().decode("utf-8")
                if "message" in response_str:
                    message = json.loads(response_str)["message"]
                else:
                    message = str(e)
                logging.error(f"Request failed - {message}")
                raise
            elif i == args.retries:
                logging.error(f"Request failed - {str(e)}")
                raise
            else:
                logging.debug(f"Request failed (attempt {i + 1} of {args.retries}) - {str(e)}")
                time.sleep(2**i)
                continue
        break

    return response


def get_latest_index(args):
    logging.debug("Fetching latest index list")
    url = f"{args.server}/collinfo.json"

    try:
        response_str = issue_request(args, url)
    except Exception:
        sys.exit(1)

    try:
        response = json.loads(response_str)
    except json.decoder.JSONDecodeError:
        logging.error(f"Unexpected response:\n{response_str}")
        sys.exit(1)

    try:
        if "fixed" in response:
            fixed = response["fixed"]
            dynamic = response["dynamic"]
            index = sorted(fixed)[-1] if fixed else sorted(dynamic)[-1]
        else:
            index = response[0]["id"]
    except Exception:
        logging.error(f"Unexpected response:\n{response}")
        sys.exit(1)
    return index


def get_num_pages(args, data):
    logging.debug("Fetching number of pages")
    data["showNumPages"] = "true"
    if args.page_size:
        data["pageSize"] = args.page_size
    url = f"{args.server}/{args.index}{args.cdx_api_suffix}?{urlencode(data)}"

    try:
        response_str = issue_request(args, url)
    except Exception:
        sys.exit(1)

    try:
        response = json.loads(response_str)
    except json.decoder.JSONDecodeError:
        logging.error(f"Unexpected response:\n{response_str}")
        sys.exit(1)

    if "pages" in response:
        num_pages = int(response["pages"])
    elif response[0] and response[0][0] == "numpages":
        num_pages = int(response[1][0])
    else:
        logging.error(f"Unexpected response:\n{response}")
        sys.exit(1)

    del data["showNumPages"]
    logging.debug("Got %d pages", num_pages)
    return num_pages


def get_page(args, data, page):
    logging.debug("Fetching page %d", page)
    data["fl"] = args.field
    data["page"] = page
    url = f"{args.server}/{args.index}{args.cdx_api_suffix}?{urlencode(data)}"

    response_str = issue_request(args, url)

    if response_str.startswith("["):
        try:
            response = json.loads(response_str.replace("\n", ""))[1:]
        except json.decoder.JSONDecodeError:
            logging.error(f"Unexpected response:\n{response_str}")
            sys.exit(1)
    else:
        response = response_str.splitlines()

    pattern = r"http[s]?://([^/.]*\.)*" + args.domain + "(/|$)"
    domain_url = re.compile(pattern)

    results = set()
    for item in response:
        if isinstance(item, list):
            item_url = item[0]
        else:
            try:
                item_url = json.loads(item)["url"]
            except json.decoder.JSONDecodeError:
                logging.error(f"Unexpected item:\n{item}")
                break


        parsed_url = urlparse(item_url.strip())
        url = parsed_url._replace(netloc=parsed_url.hostname).geturl()

        if domain_url.match(url):
            results.add(url)
    return results


def get_results(args, data, num_pages):
    results = set()
    try:
        if args.threads == 1:
            for page in range(num_pages):
                results.update(get_page(args, data, page))
        else:
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                threads = executor.map(get_page, repeat(args), repeat(data), range(num_pages))
                for result in threads:
                    results.update(result)
    except Exception:
        logging.error("Failed to fetch all results")
        pass

    return list(results)
