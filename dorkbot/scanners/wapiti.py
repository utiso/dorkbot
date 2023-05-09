import argparse
import io
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
from urllib.parse import urlparse, urlunparse, urljoin


def populate_parser(args, parser):
    module_group = parser.add_argument_group(__name__, "Scans with the wapiti3 command-line scanner")
    module_group.add_argument("--wapiti-dir", default=os.path.join(args.directory, "tools", "wapiti"), \
                          help="wapiti base dir containing bin/wapiti")
    module_group.add_argument("--args", \
                          help="space-delimited list of additional arguments")
    module_group.add_argument("--report-dir", default=os.path.join(args.directory, "reports"),\
                          help="directory to save vulnerability report")
    module_group.add_argument("--label", default="", \
                          help="friendly name field to include in vulnerability report")


def run(args, target):
    if not os.path.isdir(args.wapiti_dir): args.wapiti_dir = ""

    if args.wapiti_dir:
        wapiti_path = os.path.join(os.path.abspath(args.wapiti_dir), "bin")
    else:
        wapiti_path = args.wapiti_dir

    report = os.path.join(tempfile.gettempdir(), target.get_hash() + ".json")

    cmd = [os.path.join(wapiti_path, "wapiti")]
    if platform.system() == "Windows" and wapiti_path != "":
        cmd.insert(0, sys.executable)
    cmd += ["--url", target.url]
    cmd += ["--scope", "page"]
    cmd += ["--flush-session"]
    cmd += ["--format", "json"]
    cmd += ["--output", report]
    if args.args:
        cmd += args.args.split()

    try:
        subprocess.run(cmd, check=True)
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical(
                "Could not find wapiti. If not in PATH, extract or symlink as [directory]/tools/wapiti or set wapiti_dir option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError as e:
        logging.error("Failed to execute wapiti command - %s", str(e))
        return False

    with io.open(report, encoding="utf-8") as data_file:
        contents = data_file.read()
        data = json.loads(contents)
        vulns = []
        for vuln_type in data["vulnerabilities"]:
            for vulnerability in data["vulnerabilities"][vuln_type]:
                url = urlparse(data["infos"]["target"])
                poc_request = vulnerability["http_request"].split("\n")
                poc_path = poc_request[0].split(" ")[1]

                vuln = {}
                vuln["vulnerability"] = vuln_type
                vuln["url"] = urlunparse(url)
                vuln["parameter"] = vulnerability["parameter"]
                vuln["method"] = vulnerability["method"]
                vuln["poc"] = urljoin(vuln["url"], poc_path)
                if vuln["method"] == "POST":
                    vuln["poc_data"] = poc_request[-1]
                else:
                    vuln["poc_data"] = ""

                vulns.append(vuln)

    os.remove(report)

    return vulns
