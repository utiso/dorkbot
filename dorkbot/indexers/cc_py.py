from __future__ import print_function
import sys
import os
import tempfile
import subprocess
import re
from io import open
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

def run(args):
    required = ["domain"]
    for r in required:
        if r not in args:
            print ("ERROR: %s must be set" % r, file=sys.stderr)
            sys.exit(1)

    default_cc_py_path = os.path.join(args["dorkbot_dir"], "tools", "cc.py")
    if not os.path.isdir(default_cc_py_path): default_cc_py_path = ""

    if "cc_py_dir" in args:
        cc_py_path = os.path.abspath(args["cc_py_dir"])
    else:
        cc_py_path = default_cc_py_path
    domain = args["domain"]
    year = args.get("year", "")
    index = args.get("index", "")

    fd, temp_file_name = tempfile.mkstemp()

    args = [os.path.join(cc_py_path, "cc.py")]
    if year: args += ["-y", year]
    if index: args += ["-i", index]
    args += ["-o", temp_file_name]
    args += [domain]

    for cmd in ["python3", "python"]:
        try:
            subprocess.check_call([cmd] + args)
        except OSError as e:
            if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
                if cmd is "python3":
                    continue
                else:
                    print("Could not run script with \"python3\" or \"python\".", file=sys.stderr)
                    sys.exit(1)
        except subprocess.CalledProcessError:
            print("Could not execute cc.py. Make sure to download the cc.py project and unpack it in /path/to/dorkbot_directory/tools/ as \"cc.py\" (e.g. ~/.config/dorkbot/tools/cc.py/) such that it contains the file cc.py, or set cc_py_dir option to correct directory.", file=sys.stderr)
            sys.exit(1)

        pattern = "http[s]?://([^/]*\.)*" + domain + "/"
        domain_url = re.compile(pattern)

        with open(temp_file_name, encoding="utf-8") as temp_file:
            results = []
            for item in temp_file:
                url = urlparse(item.strip()).geturl()
                if domain_url.match(url):
                    results.append(url)
        os.close(fd)
        os.remove(temp_file_name)

        return results

