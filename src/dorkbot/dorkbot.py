#!/usr/bin/env python3
if __package__:
    from ._version import __version__
    from dorkbot.target import Target
    from dorkbot.targetdatabase import TargetDatabase
    from dorkbot.blocklist import Blocklist
    from dorkbot.util import generate_timestamp, generate_report, write_report
else:
    from _version import __version__
    from target import Target
    from targetdatabase import TargetDatabase
    from blocklist import Blocklist
    from util import generate_timestamp, generate_report, write_report
import argparse
import configparser
import importlib
import json
import logging
import os
import signal
import sys
from logging.handlers import WatchedFileHandler


def main():
    signal.signal(signal.SIGINT, graceful_shutdown)
    args, parser = get_main_args_parser()
    initialize_logger(args.log, args.verbose)

    if args.directory:
        try:
            os.makedirs(os.path.abspath(args.directory), exist_ok=True)
        except OSError as e:
            logging.error(f"Failed to create dorkbot directory - {str(e)}")
            sys.exit(1)

    if args.help:
        indexer_parser = None
        if args.indexer:
            indexer_parser, _ = get_module_parser(load_module("indexers", args.indexer))
            if not args.scanner:
                indexer_parser.print_help()
        if args.scanner:
            scanner_parser, _ = get_module_parser(load_module("scanners", args.scanner), parent_parser=indexer_parser)
            scanner_parser.print_help()
        if not args.indexer and not args.scanner:
            parser.print_help()
        sys.exit(0)

    if args.indexer or args.prune or args.scanner \
            or args.list_targets or args.flush_targets \
            or args.add_target or args.delete_target \
            or args.list_blocklist or args.flush_blocklist \
            or args.add_blocklist_item or args.delete_blocklist_item \
            or args.flush_fingerprints or args.generate_fingerprints \
            or args.reset_scanned or args.list_sources or args.show_stats:

        retry = {"retries": args.retries, "retry_on": args.retry_on}

        try:
            tables = {"drop_tables": args.drop_tables, "create_tables": True}
            db = TargetDatabase(args.database, **tables, **retry)
            blocklist = Blocklist(db.address, **tables, **retry)
        except Exception as e:
            logging.error(f"Failed to load database - {str(e)}")
            sys.exit(1)

        blocklists = [blocklist]
        if args.external_blocklist:
            for external_blocklist in args.external_blocklist:
                try:
                    blocklists.append(Blocklist(external_blocklist, **retry))
                except Exception:
                    sys.exit(1)

        if args.flush_blocklist:
            blocklist.flush()
        if args.add_blocklist_item:
            blocklist.add(args.add_blocklist_item)
        if args.delete_blocklist_item:
            blocklist.delete(args.delete_blocklist_item)
        if args.list_blocklist:
            for blocklist in blocklists:
                for item in blocklist.get_parsed_items():
                    print(item)

        if args.flush_fingerprints:
            db.flush_fingerprints()
        if args.reset_scanned:
            db.reset_scanned()
        if args.flush_targets:
            db.flush_targets()
        if args.add_target:
            db.add_target(args.add_target, source=args.source, blocklists=blocklists)
        if args.delete_target:
            db.delete_target(args.delete_target)

        if args.indexer:
            indexer_module = load_module("indexers", args.indexer)
            indexer_parser, _ = get_module_parser(indexer_module)
            indexer_args = indexer_parser.parse_args(format_module_args(args.indexer_arg))
            index(db, blocklists, indexer_module, args, indexer_args)

        if args.generate_fingerprints:
            db.generate_fingerprints(args)

        if args.prune:
            db.prune(blocklists, args)

        if args.scanner:
            scanner_module = load_module("scanners", args.scanner)
            scanner_parser, _ = get_module_parser(scanner_module)
            scanner_args = scanner_parser.parse_args(format_module_args(args.scanner_arg))
            scan(db, blocklists, scanner_module, args, scanner_args)

        if args.list_targets:
            try:
                urls = db.get_urls(args)
                for url in urls:
                    print(url)
            except BrokenPipeError:
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, sys.stdout.fileno())
                sys.exit(1)

        if args.list_sources:
            sources = db.get_sources()
            for source in sources:
                print(source)

        if args.show_stats:
            target_count = db.get_target_count(args)
            unscanned_count = db.get_target_count(args, unscanned_only=True)
            fingerprint_count = db.get_fingerprint_count()
            print(f"targets: {target_count}\n"
                  f"unscanned: {unscanned_count}\n"
                  f"fingerprints: {fingerprint_count}")

        db.close()
    else:
        parser.print_usage()

    logging.shutdown()


def graceful_shutdown(*_):
    sys.exit(0)


def initialize_logger(log_file, verbose):
    log = logging.getLogger()
    log.handlers = []

    if log_file:
        log_formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            log_filehandler = WatchedFileHandler(log_file, mode="a", encoding="utf-8")
            log_filehandler.setLevel(logging.DEBUG)
            log_filehandler.setFormatter(log_formatter)
            log.addHandler(log_filehandler)
        except OSError as e:
            logging.error(f"Failed to create log file - {str(e)}")
            raise
    else:
        class LogFilter(logging.Filter):
            def __init__(self, level):
                self.level = level

            def filter(self, record):
                return record.levelno <= self.level

        log_stdouthandler = logging.StreamHandler(sys.stdout)
        log_stdouthandler.setLevel(logging.DEBUG)
        log_stdouthandler.addFilter(LogFilter(logging.WARNING))
        log.addHandler(log_stdouthandler)

        log_stderrhandler = logging.StreamHandler(sys.stderr)
        log_stderrhandler.setLevel(logging.ERROR)
        log.addHandler(log_stderrhandler)

    if verbose and verbose >= 2:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)


def load_module(category, name):
    module_name = "%s.%s" % (category, name)
    if __package__:
        module_name = "." + module_name
    try:
        module = importlib.import_module(module_name, package=__package__)
    except ImportError:
        logging.error("Module not found")
        raise

    return module


def get_defaults(config_file, section, parser, defaults=None):
    if not defaults:
        defaults = {}
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
        config_items = dict(config.items(section))
    except configparser.NoSectionError as e:
        config_items = {}
        logging.debug(e)
    for action in parser._actions:
        if action.dest in config_items:
            try:
                defaults[action.dest] = json.loads(config_items[action.dest])
            except json.decoder.JSONDecodeError:
                defaults[action.dest] = config_items[action.dest]
    return defaults


def get_config_args(args=None):
    config_dir = os.path.abspath(os.path.expanduser(
        os.environ.get("XDG_CONFIG_HOME")
        or os.environ.get("APPDATA")
        or os.path.join(os.environ["HOME"], ".config")
    ))
    default_config = os.path.join(config_dir, "dorkbot", "dorkbot.ini")

    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("-c", "--config", default=default_config)
    config_args, _ = config_parser.parse_known_args(args)

    return config_args


def get_initial_args_parser(args=None):
    config_args = get_config_args(args=args)

    initial_parser = argparse.ArgumentParser(
        description="dorkbot", add_help=False)
    initial_parser.add_argument("-c", "--config",
                                default=config_args.config,
                                help="Configuration file")
    initial_parser.add_argument("-r", "--directory",
                                default=os.getcwd(),
                                help="Dorkbot directory (default location of db, tools, reports)")
    initial_parser.add_argument("--source", nargs="?", const=True, default=False,
                                help="Label associated with targets")
    initial_parser.add_argument("--show-defaults", action="store_true",
                                help="Show default values in help output")
    retrieval_options = initial_parser.add_argument_group("retrieval")
    retrieval_options.add_argument("--count", type=int, default=0,
                                   help="number of targets to retrieve (0/unset = all)")
    retrieval_options.add_argument("--random", action="store_true",
                                   help="retrieve targets in random order")

    defaults = get_defaults(config_args.config, "dorkbot", initial_parser)
    initial_parser.set_defaults(**defaults)
    initial_args, other_args = initial_parser.parse_known_args(args)

    return initial_args, other_args, initial_parser


def get_main_args_parser(args=None):
    initial_args, other_args, initial_parser = get_initial_args_parser(args=args)

    if initial_args.show_defaults:
        formatter = argparse.ArgumentDefaultsHelpFormatter
    else:
        formatter = argparse.HelpFormatter
    parser = argparse.ArgumentParser(
        parents=[initial_parser], add_help=False, formatter_class=formatter)

    parser.add_argument("-h", "--help", action="store_true",
                        help="Show program (or specified module) help")
    parser.add_argument("--log",
                        help="Path to log file")
    parser.add_argument("-v", "--verbose", action="count",
                        help="Enable verbose logging (can be used multiple times to increase verbosity)")
    parser.add_argument("-V", "--version", action="version",
                        version="%(prog)s " + __version__, help="Print version")

    database = parser.add_argument_group('database')
    database.add_argument("-d", "--database",
                          help="Database file/uri")
    database.add_argument("-u", "--prune", action="store_true",
                          help="Apply fingerprinting and blocklist without scanning")
    database.add_argument("--drop-tables", action="store_true",
                          help="Delete and recreate tables")
    database.add_argument("--retries", type=int, default=3,
                          help="Number of retries when an operation fails")
    database.add_argument("--retry-on", action="append", default=[],
                          help="Error strings that should result in a retry (can be used multiple times)")
    database.add_argument("--show-stats", action="store_true",
                          help="Show the total/unscanned target and fingerprint counts")

    targets = parser.add_argument_group('targets')
    targets.add_argument("-l", "--list-targets", action="store_true",
                         help="List targets in database")
    targets.add_argument("-n", "--unscanned-only", action="store_true",
                         help="Only include unscanned targets")
    targets.add_argument("--list-sources", action="store_true",
                         help="List sources in database")
    targets.add_argument("--add-target", metavar="TARGET",
                         help="Add a url to the target database")
    targets.add_argument("--delete-target", metavar="TARGET",
                         help="Delete a url from the target database")
    targets.add_argument("--flush-targets", action="store_true",
                         help="Delete all targets")
    targets.add_argument("-e", "--delete-on-error", action="store_true",
                         help="Delete target if error encountered while processing it")

    indexing = parser.add_argument_group('indexing')
    indexing.add_argument("-i", "--indexer",
                          help="Indexer module to use")
    indexing.add_argument("-o", "--indexer-arg", action="append",
                          help="Pass an argument to the indexer module (can be used multiple times)")

    scanning = parser.add_argument_group('scanning')
    scanning.add_argument("-s", "--scanner",
                          help="Scanner module to use")
    scanning.add_argument("-p", "--scanner-arg", action="append",
                          help="Pass an argument to the scanner module (can be used multiple times)")
    scanning.add_argument("-t", "--test", action="store_true",
                          help="Fetch next scannable target but do not mark it scanned")
    scanning.add_argument("-x", "--reset-scanned", action="store_true",
                          help="Reset scanned status of all targets")

    fingerprints = parser.add_argument_group('fingerprints')
    fingerprints.add_argument("-g", "--generate-fingerprints", action="store_true",
                              help="Generate fingerprints for all targets")
    fingerprints.add_argument("-f", "--flush-fingerprints", action="store_true",
                              help="Delete all generated fingerprints")
    fingerprints.add_argument("--fingerprint-max", type=int, default=0,
                              help="Maximum matches per fingerprint before deleting new matches")

    blocklist = parser.add_argument_group('blocklist')
    blocklist.add_argument("--list-blocklist", action="store_true",
                           help="List internal blocklist entries")
    blocklist.add_argument("--add-blocklist-item", metavar="ITEM",
                           help="Add an ip/host/regex pattern to the internal blocklist")
    blocklist.add_argument("--delete-blocklist-item", metavar="ITEM",
                           help="Delete an item from the internal blocklist")
    blocklist.add_argument("--flush-blocklist", action="store_true",
                           help="Delete all internal blocklist items")
    blocklist.add_argument("-b", "--external-blocklist", action="append",
                           help="Supplemental external blocklist file/db (can be used multiple times)")

    seed_defaults = {"database": os.path.join(initial_args.directory, "dorkbot.db")}
    defaults = get_defaults(initial_args.config, "dorkbot", parser, seed_defaults)
    parser.set_defaults(**defaults)
    parsed_args = parser.parse_args(other_args, namespace=initial_args)
    return parsed_args, parser


def get_module_parser(module, parent_parser=None, args=None):
    initial_args, other_args, initial_parser = get_initial_args_parser(args)

    if parent_parser:
        initial_parser = parent_parser

    usage = "%(prog)s [args] -i/-s [module] -o/-p [module_arg[=value]] ..."
    epilog = "NOTE: module args are passed via -o/-p as key=value and do not themselves require hyphens"

    if initial_args.show_defaults:
        formatter = argparse.ArgumentDefaultsHelpFormatter
    else:
        formatter = argparse.HelpFormatter
    parser = argparse.ArgumentParser(
        parents=[initial_parser], usage=usage, epilog=epilog, add_help=False, formatter_class=formatter)

    defaults = get_defaults(initial_args.config, "dorkbot", parser)
    parser.set_defaults(**defaults)

    module.populate_parser(initial_args, parser)
    module_section = ("" if __package__ else "dorkbot.") + module.__name__
    module_defaults = get_defaults(initial_args.config, module_section, parser)
    parser.set_defaults(**module_defaults)

    return parser, other_args


def format_module_args(args_list):
    args = []

    if args_list:
        for arg in args_list:
            if arg.startswith("--"):
                args.append(arg)
            else:
                args.append("--" + arg)

    return args


def index(db, blocklists, indexer, args, indexer_args):
    indexer_name = indexer.__name__.split(".")[-1]
    logging.info(f"Indexing: {indexer_name} {vars(indexer_args) if args.verbose else ''}")
    setattr(indexer_args, "directory", args.directory)
    urls, module_source = indexer.run(indexer_args)
    if args.source:
        source = args.source
    else:
        source = module_source
    db.add_targets(urls, source=source, blocklists=blocklists)


def scan(db, blocklists, scanner, args, scanner_args):
    scanned = 0
    while not args.count or scanned < args.count:
        if args.test and scanned > 0:
            break
        url = db.get_next_target(args, blocklists=blocklists)
        if not url:
            break

        target = Target(url)
        logging.info(f"Scanning: {target.url} {vars(scanner_args) if args.verbose else ''}")
        start_time = generate_timestamp()
        results = scanner.run(scanner_args, target)
        end_time = generate_timestamp()
        scanned += 1

        if results is False:
            logging.error(f"Scan failed: {target.url}")
            continue

        report = generate_report(target.url, start_time, end_time, scanner_args.label, results)
        write_report(report, scanner_args, hash=target.get_hash())


if __name__ == "__main__":
    main()
