import sys
import os
import tempfile
import json
import subprocess
import io
import logging
import platform

def run(options, target):
    default_wapiti_path = os.path.join(options["directory"], "tools", "wapiti", "bin")
    if not os.path.isdir(default_wapiti_path): default_wapiti_path = ""

    if "wapiti_dir" in options:
        wapiti_path = os.path.join(os.path.abspath(options["wapiti_dir"]), "bin")
    else:
        wapiti_path = default_wapiti_path

    report = os.path.join(tempfile.gettempdir(), target.get_hash() + ".json")

    cmd = [os.path.join(wapiti_path, "wapiti")]
    if platform.system() is "Windows":
        cmd.insert(0, sys.executable)
    cmd += ["--url", target.url]
    cmd += ["--scope", "page"]
    cmd += ["--flush-session"]
    cmd += ["--format", "json"]
    cmd += ["--output", report]
    if "args" in options:
        cmd += options["args"].split()

    try:
        subprocess.run(cmd, check=True)
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical("Could not find wapiti. If not in PATH, extract or symlink as [directory]/tools/wapiti or set wapiti_dir option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError:
        logging.error("Failed to execute wapiti command")
        return False

    with io.open(report, encoding="utf-8") as data_file:
        contents = data_file.read()
        data = json.loads(contents)
        vulns = []
        for vuln_type in data["vulnerabilities"]:
            for vulnerability in data["vulnerabilities"][vuln_type]:
                vuln = {}
                vuln["vulnerability"] = vuln_type
                vuln["url"] = data["infos"]["target"]
                vuln["parameter"] = vulnerability["parameter"]
                vuln["method"] = vulnerability["method"]
                vuln["poc"] = ""
                vulns.append(vuln)

    os.remove(report)

    return vulns

