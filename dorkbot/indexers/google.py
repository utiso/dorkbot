import sys
import os
import subprocess
from urllib.parse import urlparse
import logging

def run(args):
    required = ["engine", "query"]
    for r in required:
        if r not in args:
            logging.error("%s must be set", r)
            sys.exit(1)

    tools_dir = os.path.join(args["dorkbot_dir"], "tools")
    if "phantomjs_dir" in args:
        phantomjs_path = os.path.join(os.path.abspath(args["phantomjs_dir"]), "bin")
    elif os.path.isdir(os.path.join(tools_dir, "phantomjs", "bin")):
        phantomjs_path = os.path.join(tools_dir, "phantomjs", "bin")
    else:
        phantomjs_path = ""

    if "domain" in args: domain = args["domain"]
    else: domain = ""

    index_cmd = [os.path.join(phantomjs_path, "phantomjs")]
    index_cmd += ["--ignore-ssl-errors=true"]
    index_cmd += [os.path.join(os.path.dirname(os.path.abspath(__file__)), "google.js")]
    index_cmd += [args["engine"]]
    index_cmd += [args["query"]]
    if domain: index_cmd += [domain]

    try:
        output = subprocess.check_output(index_cmd)
    except OSError as e:
        if "No such file or directory" in str(e):
            logging.critical("Could not find phantomjs. If not in PATH, extract or symlink as [directory]/tools/phantomjs or set phantomjs_dir option to correct directory.")
            sys.exit(1)

    return [urlparse(item.decode("utf-8").strip()).geturl() for item in output.split()]

