from __future__ import print_function
import sys
import os
import json
import tempfile
import subprocess
import io
import platform

def run(args, target):
    default_arachni_path = os.path.join(args["dorkbot_dir"], "tools", "arachni", "bin")
    if not os.path.isdir(default_arachni_path): default_arachni_path = ""
    default_checks = "active/*"

    if "arachni_dir" in args:
        arachni_path = os.path.join(os.path.abspath(args["arachni_dir"]), "bin")
    else:
        arachni_path = default_arachni_path
    checks = args.get("checks", default_checks).replace(" ", ",").replace("\"","")

    report = os.path.join(tempfile.gettempdir(), target.hash + ".afr")

    scan_cmd = [os.path.join(arachni_path, "arachni")]
    if platform.system() is "Windows":
        scan_cmd[0] = scan_cmd[0] + ".bat"
    scan_cmd += ["--checks", checks]
    scan_cmd += ["--report-save-path", report]
    scan_cmd += ["--output-only-positives"]
    scan_cmd += ["--scope-page-limit", "1"]
    scan_cmd += ["--scope-include-pattern", target.url.split("?", 1)[0]]
    if "timeout" in args:
        scan_cmd += ["--timeout", args["timeout"]]
    if "single-thread" in args:
        scan_cmd += ["--http-request-concurrency", "1"]
        scan_cmd += ["--browser-cluster-pool-size", "1"]
    if "throttle" in args:
        scan_cmd += ["--plugin", "rate_limiter:requests_per_second=%d" % int(args["throttle"])]
    scan_cmd += [target.url]

    report_cmd = [os.path.join(arachni_path, "arachni_reporter")]
    if platform.system() is "Windows":
        report_cmd[0] = report_cmd[0] + ".bat"
    report_cmd += ["--reporter", "json:outfile="+report+".json"]
    report_cmd += [report]

    try:
        subprocess.check_call(scan_cmd, cwd=arachni_path)
        subprocess.check_call(report_cmd, cwd=arachni_path)
    except OSError as e:
        if "No such file or directory" in str(e):
            print("Could not find arachni. If not in PATH, then download the arachni project and unpack it in /path/to/dorkbot_directory/tools/ as \"arachni\" (e.g. ~/.config/dorkbot/tools/arachni/) such that it contains an executable bin/arachni, or set arachni_dir option to correct directory.", file=sys.stderr)
            sys.exit(1)
    except subprocess.CalledProcessError:
        return False

    with io.open(report+".json", encoding="utf-8") as data_file:    
        contents = data_file.read()
        data = json.loads(contents)
        vulns = []
        for issue in data["issues"]:
            vuln = {}
            vuln["vulnerability"] = issue["check"]["shortname"]
            vuln["url"] = issue["referring_page"]["dom"]["url"]
            vuln["parameter"] = issue["vector"]["affected_input_name"]
            if "method" in issue["vector"]:
                vuln["method"] = issue["vector"]["method"]
            else:
                vuln["method"] = ""
            vuln["poc"] = issue["page"]["dom"]["url"]
            vulns.append(vuln)

    os.remove(report)
    os.remove(report+".json")

    return vulns

