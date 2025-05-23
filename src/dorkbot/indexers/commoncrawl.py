import argparse

if __package__:
    from .pywb import populate_pywb_options, run_pywb
    from .general import populate_general_options
else:
    from indexers.pywb import populate_pywb_options, run_pywb
    from indexers.general import populate_general_options


def populate_parser(_, parser):
    module_group = parser.add_argument_group(__name__, "Searches commoncrawl.org crawl data")
    populate_general_options(module_group)
    populate_pywb_options(module_group)

    defaults = {"server": "https://index.commoncrawl.org", "cdx_api_suffix": "-index", "field": "url"}
    module_group.set_defaults(**defaults)
    for action in module_group._actions:
        if action.dest in defaults.keys():
            action.help = argparse.SUPPRESS
            action.required = False


def run(args):
    source = __name__.split(".")[-1]
    results, source = run_pywb(args, source)
    return results, source
