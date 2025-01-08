import io
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
from urllib.parse import urlparse, urlunparse, urljoin

if __package__:
    from .general import populate_general_options
else:
    from scanners.general import populate_general_options


def populate_parser(args, parser):
    scanner = __name__.split(".")[-1]
    module_group = parser.add_argument_group(__name__, f"Scans with the {scanner} command-line scanner")
    populate_general_options(args, module_group)
    module_group.add_argument("--path", default=os.path.join(args.directory, "tools", scanner, "bin"), \
                          help="path to scanner binary")


def run(args, target):
    if os.path.isdir(args.path):
        path = os.path.abspath(args.path)
    else:
        path = ""

    scanner = __name__.split(".")[-1]
    report = os.path.join(tempfile.gettempdir(), target.get_hash())

    scan_cmd = [os.path.join(path, scanner)]
    if platform.system() == "Windows" and path != "":
        scan_cmd.insert(0, sys.executable)
    scan_cmd += ["--url", target.url]
    scan_cmd += ["--scope", "page"]
    scan_cmd += ["--flush-session"]
    scan_cmd += ["--format", "json"]
    scan_cmd += ["--output", f"{report}.json"]
    if args.args:
        scan_cmd += args.args.split()

    try:
        subprocess.run(scan_cmd, check=True, capture_output=True)
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical(
                f"Could not find {scanner}. If not in PATH, extract or symlink as [directory]/tools/{scanner} or set path option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to execute command - {str(e)}\n{e.stderr.decode()}")
        return False

    with io.open(report + ".json", encoding="utf-8") as data_file:
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

    os.remove(report + ".json")

    return vulns
