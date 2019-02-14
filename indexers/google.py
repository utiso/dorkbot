from __future__ import print_function
import sys
import os
import subprocess
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(args):
    required = ["engine", "query"]
    for r in required:
        if r not in args:
            print ("ERROR: %s must be set" % r, file=sys.stderr)
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
            print("Could not find phantomjs. If not in PATH, then download the phantomjs project and unpack it in /path/to/dorkbot_directory/tools/ as \"phantomjs\" (e.g. ~/.config/dorkbot/tools/phantomjs/) such that it contains an executable bin/phantomjs, or set phantomjs_dir option to correct directory.", file=sys.stderr)
            sys.exit(1)

    return [urlparse(item.decode("utf-8").strip()).geturl() for item in output.split()]

