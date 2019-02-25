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

    args = [os.path.join(wapiti_path, "wapiti")]
    args += ["--url", target.url]
    args += ["--module", modules]
    args += ["--scope", "page"]
    args += ["--flush-session"]
    args += ["--format", "json"]
    args += ["--output", report]

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
            print("Error executing wapiti.", file=sys.stderr)
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

