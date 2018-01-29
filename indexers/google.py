from __future__ import print_function
import sys
import os
import subprocess
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(options):
    required = ["engine", "query"]
    for r in required:
        if r not in options:
            print ("ERROR: %s must be set" % r, file=sys.stderr)
            sys.exit(1)

    dorkbot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)

    if "phantomjs_dir" in options:
        phantomjs_path = os.path.join(os.path.abspath(options["phantomjs_dir"]), "bin")
    elif os.path.isdir(os.path.join(dorkbot_dir, "tools", "phantomjs", "bin")):
        phantomjs_path = os.path.join(dorkbot_dir, "tools", "phantomjs", "bin")
    else:
        phantomjs_path = ""

    phantomjs_cmd = os.path.join(phantomjs_path, "phantomjs")

    indexer_dir = os.path.dirname(os.path.abspath(__file__))
    if "domain" in options: domain = options["domain"]
    else: domain = ""

    index_cmd = [phantomjs_cmd]
    index_cmd += ["--ignore-ssl-errors=true"]
    index_cmd += [os.path.join(indexer_dir, "google.js")]
    index_cmd += [options["engine"]]
    index_cmd += [options["query"]]
    if domain: index_cmd += [domain]

    try:
        results = get_results(index_cmd)
    except OSError as e:
        if "No such file or directory" in e:
            print("Could not execute phantomjs. If not in PATH, then download and unpack as /path/to/dorkbot/tools/phantomjs/ or set phantomjs_dir option to correct directory.", file=sys.stderr)
            sys.exit(1)

    return results

def get_results(index_cmd):
    output = subprocess.check_output(index_cmd)

    results = []
    for result in output.split(): results.append(urlparse(result))

    unique_results_tuples = []
    unique_results = []
    for result in results:
        if result.query and (result.netloc, result.path) not in unique_results_tuples:
            unique_results_tuples.append((result.netloc, result.path))
            unique_results.append(result)

    return unique_results

