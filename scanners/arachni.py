from __future__ import print_function
import os
import hashlib
import json
from subprocess import call
from io import open

def run(options, url):
    dorkbot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)

    if "arachni_dir" in options:
        arachni_path = os.path.join(os.path.normcase(options["arachni_dir"]), "bin")
    elif os.path.isdir(os.path.join(dorkbot_dir, "tools", "arachni", "bin")):
        arachni_path = os.path.join(dorkbot_dir, "tools", "arachni", "bin")
    else:
        arachni_path = ""

    arachni_cmd = os.path.join(arachni_path, "arachni")
    arachni_reporter_cmd = os.path.join(arachni_path, "arachni_reporter")

    if "report_dir" in options:
        report_dir = os.path.normcase(options["report_dir"])
    else:
        report_dir = os.path.join(dorkbot_dir, "reports")

    if "checks" in options:
        checks = options["checks"]
    else:
        checks = "active/*,-csrf,-unvalidated_redirect,-source_code_disclosure,-response_splitting,-no_sql_injection_differential"

    url_base = url.split('?', 1)[0].replace("(", "%28").replace(")", "%29")
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    url_quoted = "'"+url.replace("'", "%27")+"'"

    report_base = os.path.join(report_dir, url_hash)
    report = report_base+".bin"

    if os.path.isfile(report) or os.path.isfile(report_base+".stderr"):
        print("Skipping (found report file): " + url)
    else:
        print("Scanning: " + url)
        scan_options = \
            " --report-save-path " + report + \
            " --timeout 00:30:00" + \
            " --http-request-concurrency 1" + \
            " --http-request-queue-size 25" + \
            " --http-response-max-size 100000" + \
            " --scope-page-limit 1" + \
            " --output-only-positives" + \
            " --scope-auto-redundant 2" + \
            " --scope-include-pattern " + "\""+url_base+"\"" + \
            " --checks " + checks + \
            " --plugin autothrottle" + \
            " --browser-cluster-ignore-images" + \
            " "

        scan_cmd = arachni_cmd + scan_options + url_quoted + " 2>"+report_base+".stderr"
        ret = call(scan_cmd, shell=True)

        if ret == 0 and os.path.isfile(report_base+".stderr"):
            os.remove(report_base+".stderr")

        report_options = \
            " --reporter json:outfile="+report_base+".json" + \
            " "

        report_cmd = arachni_reporter_cmd + report_options + report
        call(report_cmd, shell=True)

        with open(report_base+".json", encoding="utf-8") as data_file:    
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

