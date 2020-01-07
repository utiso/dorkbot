import sys
import os
import json
import tempfile
import subprocess
import io
import platform
import logging

def run(options, target):
    default_arachni_path = os.path.join(options["directory"], "tools", "arachni", "bin")
    if not os.path.isdir(default_arachni_path): default_arachni_path = ""

    if "arachni_dir" in options:
        arachni_path = os.path.join(os.path.abspath(options["arachni_dir"]), "bin")
    else:
        arachni_path = default_arachni_path

    report = os.path.join(tempfile.gettempdir(), target.get_hash() + ".afr")

    scan_cmd = [os.path.join(arachni_path, "arachni")]
    if platform.system() is "Windows":
        scan_cmd[0] = scan_cmd[0] + ".bat"
    scan_cmd += ["--report-save-path", report]
    scan_cmd += ["--output-only-positives"]
    scan_cmd += ["--scope-page-limit", "1"]
    scan_cmd += ["--scope-include-pattern", target.url.split("?", 1)[0]]
    if "args" in options:
        scan_cmd += options["args"].split()
    scan_cmd += [target.url]

    report_cmd = [os.path.join(arachni_path, "arachni_reporter")]
    if platform.system() is "Windows":
        report_cmd[0] = report_cmd[0] + ".bat"
    report_cmd += ["--reporter", "json:outfile="+report+".json"]
    report_cmd += [report]

    try:
        subprocess.run(scan_cmd, cwd=arachni_path, check=True)
        subprocess.run(report_cmd, cwd=arachni_path, check=True)
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical("Could not find arachni. If not in PATH, extract or symlink as [directory]/tools/arachni or set arachni_dir option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError:
        logging.error("Failed to execute arachni command")
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

