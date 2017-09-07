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
        phantomjs_path = os.path.join(os.path.normcase(options["phantomjs_dir"]), "bin")
    elif os.path.isdir(os.path.join(dorkbot_dir, "tools", "phantomjs", "bin")):
        phantomjs_path = os.path.join(dorkbot_dir, "tools", "phantomjs", "bin")
    else:
        phantomjs_path = ""

    if "domain" in options:
        domain = options["domain"]
    else:
        domain = ""

    results = get_results(phantomjs_path, options["engine"], options["query"], domain)
    return results

def get_results(phantomjs_path, engine, query, domain):
    indexer_dir = os.path.dirname(os.path.abspath(__file__))

    index_cmd = []
    index_cmd.append(os.path.join(phantomjs_path, "phantomjs"))
    index_cmd.append("--ignore-ssl-errors=true")
    index_cmd.append(os.path.join(indexer_dir, "google.js"))
    index_cmd.append(engine)
    index_cmd.append(query)
    if domain:
        index_cmd.append(domain)

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

