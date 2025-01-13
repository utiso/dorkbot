import io
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile

if __package__:
    from .general import populate_general_options
else:
    from scanners.general import populate_general_options


def populate_parser(args, parser):
    scanner = __name__.split(".")[-1]
    module_group = parser.add_argument_group(__name__, f"Scans with the {scanner} command-line scanner")
    populate_general_options(args, module_group)
    module_group.add_argument("--path", default=os.path.join(args.directory, "tools", scanner, "bin"), \
                          help="path to scanner binary")


def run(args, target):
    if os.path.isdir(args.path):
        path = os.path.abspath(args.path)
    else:
        path = ""

    scanner = __name__.split(".")[-1]
    report = os.path.join(tempfile.gettempdir(), target.get_hash())

    scan_cmd = [os.path.join(path, scanner)]
    if platform.system() == "Windows":
        scan_cmd[0] = f"{scan_cmd[0]}.bat"
    scan_cmd += ["--report-save-path", f"{report}.bin"]
    scan_cmd += ["--output-only-positives"]
    scan_cmd += ["--scope-page-limit", "1"]
    scan_cmd += ["--scope-include-pattern", target.url.split("?", 1)[0]]
    if args.args:
        scan_cmd += args.args.split()
    scan_cmd += [target.url]

    report_cmd = [os.path.join(path, f"{scanner}_reporter")]
    if platform.system() == "Windows":
        report_cmd[0] = f"{report_cmd[0]}.bat"
    report_cmd += ["--reporter", f"json:outfile={report}.json"]
    report_cmd += [f"{report}.bin"]

    try:
        subprocess.run(scan_cmd, check=True, capture_output=True)
        subprocess.run(report_cmd, check=True, capture_output=True)
    except OSError as e:
        if "No such file or directory" in str(e) or "The system cannot find the file specified" in str(e):
            logging.critical(
                f"Could not find {scanner}. If not in PATH, extract or symlink as [directory]/tools/{scanner} or set path option to correct directory.")
            sys.exit(1)
        else:
            raise
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to execute command - {str(e)}\n{e.stderr.decode()}")
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

    os.remove(report + ".bin")
    os.remove(report + ".json")

    return vulns
