if __package__:
    from .pywb import populate_pywb_options, run_pywb
    from .general import populate_general_options
else:
    from indexers.pywb import populate_pywb_options, run_pywb
    from indexers.general import populate_general_options


def populate_parser(_, parser):
    module_group = parser.add_argument_group(__name__, "Searches archive.org crawl data")
    populate_general_options(module_group)
    populate_pywb_options(module_group)
    defaults = {"server": "https://web.archive.org", "cdx_api_suffix": "/cdx/search/cdx", "field": "original"}
    module_group.set_defaults(**defaults)
    next(action for action in module_group._actions if action.dest == "server").required = False
    module_group.add_argument("--from", dest="from_", metavar="FROM",
                              help="beginning timestamp")
    module_group.add_argument("--to",
                              help="end timestamp")


def run(args):
    source = __name__.split(".")[-1]
    data = {"collapse": "urlkey"}

    if args.from_:
        data["from"] = args.from_
        source += f",from:{args.from_}"
    if args.to:
        data["to"] = args.to
        source += f",to:{args.to}"

    results, source = run_pywb(args, data, source)
    return results, source
