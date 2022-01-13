import io
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile


def run(options, target):
    default_arachni_path = os.path.join(options["directory"], "tools", "arachni", "bin")
    if not os.path.isdir(default_arachni_path): default_arachni_path = ""

    if "arachni_dir" in options:
        arachni_path = os.path.join(os.path.abspath(options["arachni_dir"]), "bin")
    else:
        arachni_path = default_arachni_path

    report = os.path.join(tempfile.gettempdir(), target.get_hash() + ".afr")

    scan_cmd = [os.path.join(arachni_path, "arachni")]
    if platform.system() == "Windows":
        scan_cmd[0] = scan_cmd[0] + ".bat"
    scan_cmd += ["--report-save-path", report]
    scan_cmd += ["--output-only-positives"]
    scan_cmd += ["--scope-page-limit", "1"]
    scan_cmd += ["--scope-include-pattern", target.url.split("?", 1)[0]]
    if "args" in options:
        scan_cmd += options["args"].split()
    scan_cmd += [target.url]

    report_cmd = [os.path.join(arachni_path, "arachni_reporter")]
    if platform.system() == "Windows":
        report_cmd[0] = report_cmd[0] + ".bat"
    report_cmd += ["--reporter", "json:outfile=" + report + ".json"]
    report_cmd += [report]

    try:
        subprocess.run(scan_cmd, cwd=arachni_path, check=True)
        subprocess.run(report_cmd, cwd=arachni_path, check=True)
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical(
                "Could not find arachni. If not in PATH, extract or symlink as [directory]/tools/arachni or set arachni_dir option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError as e:
        logging.error("Failed to execute arachni command - %s", str(e))
        return False

    with io.open(report + ".json", encoding="utf-8") as data_file:
        contents = data_file.read()
        data = json.loads(contents)
        vulns = []
        for issue in data["issues"]:
            vuln = {}
            vuln["vulnerability"] = issue["check"]["shortname"]
            vuln["url"] = issue["vector"]["url"]
            vuln["parameter"] = issue["vector"]["affected_input_name"]
            if vuln["parameter"] is None:
                vuln["parameter"] = ""
            vuln["method"] = issue["request"]["method"]
            vuln["poc"] = issue["response"]["url"]
            vuln["poc_data"] = issue["request"]["effective_body"]
            if vuln["poc_data"] is None:
                vuln["poc_data"] = ""
            vulns.append(vuln)

    os.remove(report)
    os.remove(report + ".json")

    return vulns
