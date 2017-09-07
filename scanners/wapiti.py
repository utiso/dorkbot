from __future__ import print_function
import os
import hashlib
import json
from subprocess import call
from io import open

def run(options, url):
    dorkbot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)

    if "wapiti_dir" in options:
        wapiti_path = os.path.join(os.path.normcase(options["wapiti_dir"]), "bin")
    elif os.path.isdir(os.path.join(dorkbot_dir, "tools", "wapiti", "bin")):
        wapiti_path = os.path.join(dorkbot_dir, "tools", "wapiti", "bin")
    else:
        wapiti_path = ""

    wapiti_cmd = os.path.join(wapiti_path, "wapiti")

    if "report_dir" in options:
        report_dir = os.path.normcase(options["report_dir"])
    else:
        report_dir = os.path.join(dorkbot_dir, "reports")

    url_base = url.split('?', 1)[0]
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    url_quoted = "'"+url.replace("'", "%27")+"'"

    report_base = os.path.join(report_dir, url_hash)
    report = report_base+".json"

    if os.path.isfile(report) or os.path.isfile(report_base+".stderr"): 
        print("Skipping (found report file): " + url)
    else:
        print("Scanning: " + url)
        scan_options = \
            " --module \"exec,file,sql,xss,permanentxss\"" + \
            " --scope page" + \
            " --timeout 5" + \
            " --nice 1" + \
            " --format json" + \
            " --output " + report + \
            " "

        scan_cmd = wapiti_cmd + scan_options + url_quoted + " 2>"+report_base+".stderr"
        ret = call(scan_cmd, shell=True)

        if ret == 0 and os.path.isfile(report_base+".stderr"):
            os.remove(report_base+".stderr")


        with open(report, encoding="utf-8") as data_file:
            contents = data_file.read()
            data = json.loads(contents)

            vulns = []

            for vuln_type in data["vulnerabilities"]:
                for vulnerability in data["vulnerabilities"][vuln_type]:
                    vuln = {}
                    vuln['vulnerability'] = vuln_type
                    vuln['url'] = data["infos"]["target"]
                    vuln['parameter'] = vulnerability["parameter"]
                    vuln['method'] = vulnerability["method"]
                    vulns.append(vuln)

        return vulns


