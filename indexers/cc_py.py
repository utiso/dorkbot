from __future__ import print_function
import sys
import os
import tempfile
import subprocess
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

    with tempfile.NamedTemporaryFile() as temp_file:
        index_cmd = [os.path.join(cc_py_path, "cc.py")]
        if year: index_cmd += ["-y", year]
        if index: index_cmd += ["-i", index]
        index_cmd += ["-o", temp_file.name]
        index_cmd += [domain]

        try:
            subprocess.check_call(index_cmd)
        except OSError as e:
            if "No such file or directory" in str(e):
                print("Could not execute cc.py. If not in PATH, then download the cc.py project and unpack it in /path/to/dorkbot_directory/tools/ as \"cc.py\" (e.g. ~/.config/dorkbot/tools/cc.py/) such that it contains an executable cc.py, or set cc_py_dir option to correct directory.", file=sys.stderr)
                sys.exit(1)
            elif "Permission denied" in e:
                print("Could not execute cc.py. Make sure it is executable, e.g.: chmod +x tools/cc.py/cc.py", file=sys.stderr)
                sys.exit(1)
        except subprocess.CalledProcessError:
            return False

        return [urlparse(item.decode("utf-8").strip()).geturl() for item in temp_file]

