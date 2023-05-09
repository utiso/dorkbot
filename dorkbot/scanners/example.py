import argparse
import os
import subprocess


def get_parser(initial_parser):
    parser = argparse.ArgumentParser(parents=[initial_parser])
    module_group = parser.add_argument_group(__name__, "Example module that returns a few vulnerabilities")

    return parser


def run(args, target):
    scan_cmd = [os.path.abspath(os.path.join(os.sep, "bin", "echo"))]
    scan_cmd += ["pretending"]
    scan_cmd += ["to"]
    scan_cmd += ["scan", target.url]
    try:
        subprocess.run(scan_cmd, check=True)
    except subprocess.CalledProcessError:
        return False

    vulns = []
    for i in range(1, 3):
        vuln = {}
        vuln["vulnerability"] = "Example Vulnerability %d" % i
        vuln["url"] = target.url
        vuln["parameter"] = "foo%d" % i
        vuln["method"] = "post"
        vuln["poc"] = target.url + "';%20drop%20table%20users;--%20"
        vulns.append(vuln)

    return vulns
