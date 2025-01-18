import os
import subprocess

if __package__:
    from .general import populate_general_options
else:
    from scanners.general import populate_general_options


def populate_parser(args, parser):
    scanner = __name__.split(".")[-1]
    module_group = parser.add_argument_group(__name__, f"Scans with the {scanner} command-line scanner")
    populate_general_options(args, module_group)
    module_group.add_argument("--path", default=os.path.join(args.directory, "tools", scanner, "bin"),
                              help="path to scanner binary")

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
