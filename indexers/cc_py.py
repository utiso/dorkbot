from __future__ import print_function
import sys
import os
import subprocess
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(options):
    required = ["domain"]
    for r in required:
        if r not in options:
            print ("ERROR: %s must be set" % r, file=sys.stderr)
            sys.exit(1)

    dorkbot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)

    domain = options["domain"]

    if "cc_py_dir" in options:
        cc_py_path = os.path.abspath(options["cc_py_dir"])
    elif os.path.isdir(os.path.join(dorkbot_dir, "tools", "cc.py")):
        cc_py_path = os.path.join(dorkbot_dir, "tools", "cc.py")
    else:
        cc_py_path = ""

    cc_py_cmd = os.path.join(cc_py_path, "cc.py")

    if "year" in options: year = options["year"]
    else: year = ""

    if "filename" in options: filename = options["filename"]
    else: filename = "%s.txt" % domain

    index_cmd = [cc_py_cmd]
    if year: index_cmd += ["-y", year]
    if filename: index_cmd += ["-o", filename]
    index_cmd += [domain]

    results = []
    try:
        results = get_results(index_cmd, filename)
    except OSError as e:
        if "No such file or directory" in e:
            print("Could not execute cc.py. If not in PATH, then download and unpack as /path/to/dorkbot/tools/cc.py/ or set cc_py_dir option to correct directory.", file=sys.stderr)
            sys.exit(1)
        elif "Permission denied" in e:
            print("Could not execute cc.py. Make sure it is executable, e.g.: chmod +x tools/cc.py/cc.py", file=sys.stderr)
            sys.exit(1)

    return results

def get_results(index_cmd, filename):
    subprocess.check_call(index_cmd)

    results = []
    with open(os.path.abspath(filename), "r") as output:
        for result in output: results.append(urlparse(result.strip()))
    os.remove(os.path.abspath(filename))

    unique_results_tuples = []
    unique_results = []
    for result in results:
        if result.query and (result.netloc, result.path) not in unique_results_tuples:
            unique_results_tuples.append((result.netloc, result.path))
            unique_results.append(result)

    return unique_results

