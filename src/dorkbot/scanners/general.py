import os


def populate_general_options(args, module_group):
    module_group.add_argument("--args", \
                          help="space-delimited list of additional arguments")
    module_group.add_argument("--report-dir", default=os.path.join(args.directory, "reports"), \
                          help="directory to save report file")
    module_group.add_argument("--report-filename", \
                          help="filename to save vulnerability report as")
    module_group.add_argument("--report-append", \
                          help="append to report file if it exists", action="store_true")
    module_group.add_argument("--report-indent", \
                          help="indent level for vulnerability report json")
    module_group.add_argument("--label", default="", \
                          help="friendly name field to include in vulnerability report")
