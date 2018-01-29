from __future__ import print_function
import sys
import os
import hashlib
import json
from subprocess import call
from io import open

def run(options, url):
    dorkbot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)

    if "arachni_dir" in options:
        arachni_path = os.path.join(os.path.abspath(options["arachni_dir"]), "bin")
    elif os.path.isdir(os.path.join(dorkbot_dir, "tools", "arachni", "bin")):
        arachni_path = os.path.join(dorkbot_dir, "tools", "arachni", "bin")
    else:
        arachni_path = ""

    arachni_cmd = os.path.join(arachni_path, "arachni")
    arachni_reporter_cmd = os.path.join(arachni_path, "arachni_reporter")

    if "report_dir" in options:
        report_dir = os.path.abspath(options["report_dir"])
    else:
        report_dir = os.path.join(dorkbot_dir, "reports")

    if "checks" in options:
        checks = options["checks"].replace(" ", ",")
    else:
        checks = "active/*,-csrf,-unvalidated_redirect,-source_code_disclosure,-response_splitting,-no_sql_injection_differential"

    url_base = url.split("?", 1)[0].replace("(", "%28").replace(")", "%29")
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    report = os.path.join(report_dir, url_hash + ".bin")
    report_stderr = os.path.join(report_dir, url_hash + ".stderr")
    report_json = os.path.join(report_dir, url_hash + ".json")

    scan_cmd = [arachni_cmd]
    scan_cmd += ["--report-save-path", report]
    scan_cmd += ["--timeout", "00:10:00"]
    scan_cmd += ["--http-request-concurrency", "1"]
    scan_cmd += ["--http-request-queue-size", "25"]
    scan_cmd += ["--http-response-max-size", "100000"]
    scan_cmd += ["--scope-page-limit", "1"]
    scan_cmd += ["--output-only-positives"]
    scan_cmd += ["--scope-auto-redundant", "2"]
    scan_cmd += ["--scope-include-pattern", url_base]
    scan_cmd += ["--checks", checks]
    scan_cmd += ["--plugin", "autothrottle"]
    scan_cmd += ["--browser-cluster-ignore-images"]
    scan_cmd += [url]

    report_cmd = [arachni_reporter_cmd]
    report_cmd += ["--reporter", "json:outfile="+report_json]
    report_cmd += [report]

    if os.path.isfile(report) or os.path.isfile(report_stderr):
        print("Skipping (found report file): " + url)

    else:
        print("Scanning: " + url)
        report_stderr_f = open(report_stderr, "a")
        try:
            ret = call(scan_cmd, cwd=arachni_path, stderr=report_stderr_f)
            if ret != 0: sys.exit(1)
        except OSError as e:
            if "No such file or directory" in e:
                print("Could not execute arachni. If not in PATH, then download and unpack as /path/to/dorkbot/tools/arachni/ or set arachni_dir option to correct directory.", file=sys.stderr)
                report_stderr_f.close()
                os.remove(report_stderr)
                sys.exit(1)
        try:
            ret = call(report_cmd, cwd=arachni_path, stderr=report_stderr_f)
            if ret != 0: sys.exit(1)
        except OSError as e:
            if "No such file or directory" in e:
                print("Could not execute arachni_reporter. If not in PATH, then download and unpack as /path/to/dorkbot/tools/arachni/ or set arachni_dir option to correct directory.", file=sys.stderr)
                report_stderr_f.close()
                os.remove(report_stderr)
                sys.exit(1)
        if os.path.isfile(report_stderr):
            report_stderr_f.close()
            os.remove(report_stderr)

        with open(report_json, encoding="utf-8") as data_file:    
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
                if issue["check"]["shortname"] == "xss_script_context":
                    vuln["poc"] = issue["page"]["dom"]["url"].replace("window.top._arachni_js_namespace_taint_tracer.log_execution_flow_sink()", "alert(150)")
                elif issue["check"]["shortname"] == "xss_tag":
                    vuln["poc"] = issue["page"]["dom"]["url"].replace("arachni_xss_in_tag", "autofocus+onfocus=alert(150)+onload=alert(150)+xss")
                elif issue["check"]["shortname"] == "xss_path":
                    vuln["poc"] = issue["page"]["dom"]["url"].replace("%3Cmy_tag", "%3Cimg+src=xyz+onerror=alert(150)%3E%3Cmy_tag")
                elif issue["check"]["shortname"] == "xss":
                    vuln["poc"] = issue["page"]["dom"]["url"].replace("%3Cxss", "%3Cimg+src=xyz+onerror=alert(150)%3E%3Cxss")
                else:
                    vuln["poc"] = issue["page"]["dom"]["url"]
                vulns.append(vuln)
            return vulns

