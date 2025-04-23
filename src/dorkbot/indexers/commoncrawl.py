if __package__:
    from .pywb import populate_pywb_options, run_pywb
    from .general import populate_general_options
else:
    from indexers.pywb import populate_pywb_options, run_pywb
    from indexers.general import populate_general_options


def populate_parser(_, parser):
    defaults = {"server": "https://index.commoncrawl.org", "cdx_api_suffix": "-index", "field": "url"}
    module_group = parser.add_argument_group(__name__, f"Searches commoncrawl.org crawl data")
    populate_general_options(module_group)
    populate_pywb_options(module_group)
    module_group.set_defaults(**defaults)
    next(action for action in module_group._actions if action.dest == "server").required = False


def run(args):
    results, source = run_pywb(args)
    return results, source
