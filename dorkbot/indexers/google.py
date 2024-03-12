import logging
import os
import subprocess
import sys
from urllib.parse import urlparse


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Searches google.com via scraping")
    module_group.add_argument("--engine", required=True, \
                          help="CSE id")
    module_group.add_argument("--query", required=True, \
                          help="search query")
    module_group.add_argument("--phantomjs-dir", \
                          help="phantomjs base dir containing bin/phantomjs")
    module_group.add_argument("--domain", \
                          help="limit searches to specified domain")


def run(args):
    source = __name__.split(".")[-1]
    tools_dir = os.path.join(args.directory, "tools")
    if args.phantomjs_dir:
        phantomjs_path = os.path.join(os.path.abspath(argsphantomjs_dir, "bin"))
    elif os.path.isdir(os.path.join(tools_dir, "phantomjs", "bin")):
        phantomjs_path = os.path.join(tools_dir, "phantomjs", "bin")
    else:
        phantomjs_path = ""

    index_cmd = [os.path.join(phantomjs_path, "phantomjs")]
    index_cmd += ["--ignore-ssl-errors=true"]
    index_cmd += [os.path.join(os.path.dirname(os.path.abspath(__file__)), "google.js")]
    index_cmd += [args.engine]
    index_cmd += [args.query]
    if args.domain: index_cmd += [args.domain]

    try:
        output = subprocess.run(index_cmd, check=True, stdout=subprocess.PIPE).stdout
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical(
                "Could not find phantomjs. If not in PATH, extract or symlink as [directory]/tools/phantomjs or set phantomjs_dir option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError as e:
        logging.error("Failed to execute phantomjs command - %s", str(e))
        return False

    results = [urlparse(item.decode("utf-8").strip()).geturl() for item in output.split()]
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results, source
