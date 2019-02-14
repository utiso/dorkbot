from __future__ import print_function
import sys
import os
import tempfile
import json
import subprocess
import io

def run(args, target):
    default_wapiti_path = os.path.join(args["dorkbot_dir"], "tools", "wapiti", "bin")
    if not os.path.isdir(default_wapiti_path): default_wapiti_path = ""
    default_modules = "blindsql,exec,file,permanentxss,sql,xss"

    if "wapiti_dir" in args:
        wapiti_path = os.path.join(os.path.abspath(args["wapiti_dir"]), "bin")
    else:
        wapiti_path = default_wapiti_path
    modules = args.get("modules", default_modules).replace(" ", ",").replace("\"","")

    report = os.path.join(tempfile.gettempdir(), target.hash + ".json")

    scan_cmd = [os.path.join(wapiti_path, "wapiti")]
    scan_cmd += ["--url", target.url]
    scan_cmd += ["--module", modules]
    scan_cmd += ["--scope", "page"]
    scan_cmd += ["--flush-session"]
    scan_cmd += ["--format", "json"]
    scan_cmd += ["--output", report]

    try:
        subprocess.check_call(scan_cmd, cwd=wapiti_path)
    except OSError as e:
        if "No such file or directory" in str(e):
            print("Could not find wapiti. If not in PATH, then download the wapiti project and unpack it in /path/to/dorkbot_directory/tools/ as \"wapiti\" (e.g. ~/.config/dorkbot/tools/wapiti/) such that it contains an executable bin/wapiti, or set wapiti_dir option to correct directory.", file=sys.stderr)
            sys.exit(1)
    except subprocess.CalledProcessError:
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

