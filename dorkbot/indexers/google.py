import sys
import os
import subprocess
from urllib.parse import urlparse
import logging

def run(options):
    required = ["engine", "query"]
    for r in required:
        if r not in options:
            logging.error("%s must be set", r)
            sys.exit(1)

    tools_dir = os.path.join(options["directory"], "tools")
    if "phantomjs_dir" in options:
        phantomjs_path = os.path.join(os.path.abspath(options["phantomjs_dir"]), "bin")
    elif os.path.isdir(os.path.join(tools_dir, "phantomjs", "bin")):
        phantomjs_path = os.path.join(tools_dir, "phantomjs", "bin")
    else:
        phantomjs_path = ""

    if "domain" in options: domain = options["domain"]
    else: domain = ""

    index_cmd = [os.path.join(phantomjs_path, "phantomjs")]
    index_cmd += ["--ignore-ssl-errors=true"]
    index_cmd += [os.path.join(os.path.dirname(os.path.abspath(__file__)), "google.js")]
    index_cmd += [options["engine"]]
    index_cmd += [options["query"]]
    if domain: index_cmd += [domain]

    try:
        output = subprocess.run(index_cmd, check=True, stdout=subprocess.PIPE).stdout
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical("Could not find phantomjs. If not in PATH, extract or symlink as [directory]/tools/phantomjs or set phantomjs_dir option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError:
        logging.error("Failed to execute phantomjs command")
        return False

    results = [urlparse(item.decode("utf-8").strip()).geturl() for item in output.split()]
    for result in results:
        logging.debug(result)
    logging.info("Fetched %d results", len(results))
    return results

