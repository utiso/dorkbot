#!/usr/bin/env python3
if __package__:
    from ._version import __version__
    from dorkbot.database import TargetDatabase
    from dorkbot.target import Target
    from dorkbot.blocklist import Blocklist
    from dorkbot.util import generate_timestamp
else:
    from _version import __version__
    from database import TargetDatabase
    from target import Target
    from blocklist import Blocklist
    from util import generate_timestamp
import argparse
import configparser
import importlib
import logging
import os
import re
import sys
from logging.handlers import WatchedFileHandler
from urllib.parse import parse_qsl, quote, urlencode, urlparse


def main():
    args, parser = get_main_args_parser()
    initialize_logger(args.log, args.verbose)

    if args.directory and not os.path.isdir(args.directory):
        logging.debug("Creating directory - %s", args.directory)
        try:
            os.makedirs(args.directory)
        except OSError as e:
            logging.error("Failed to create directory - %s", str(e))
            sys.exit(1)

    if args.help:
        indexer_parser = None
        if args.indexer:
            indexer_parser, other_args = get_module_parser(load_module("indexers", args.indexer))
            if not args.scanner:
                indexer_parser.print_help()
        if args.scanner:
            scanner_parser, other_args = get_module_parser(load_module("scanners", args.scanner), parent_parser=indexer_parser)
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
            or args.list_unscanned or args.reset_scanned \
            or args.list_sources:

        pattern = "^[^:]+://.*$"
        regex = re.compile(pattern)
        if (regex.match(args.database)):
            blocklist = Blocklist(args.database)
        else:
            blocklist = Blocklist("sqlite3://" + args.database)

        blocklists = [blocklist]
        if args.external_blocklist:
            for external_blocklist in args.external_blocklist:
                blocklists.append(Blocklist(external_blocklist))

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

        db = TargetDatabase(args.database, drop_tables=args.drop_tables, create_tables=True)
        if args.flush_fingerprints:
            db.flush_fingerprints()
        if args.reset_scanned:
            db.reset_scanned()
        if args.flush_targets:
            db.flush_targets()
        if args.add_target:
            url_parts = urlparse(args.add_target)
            quoted_path = quote(url_parts.path)
            encoded_query = urlencode(parse_qsl(url_parts.query, keep_blank_values=True))
            parsed_url = url_parts._replace(path=quoted_path, query=encoded_query)
            db.add_target(parsed_url.geturl(), args.source)
        if args.delete_target:
            db.delete_target(args.delete_target)

        if args.indexer:
            indexer_module = load_module("indexers", args.indexer)
            indexer_parser, other_args = get_module_parser(indexer_module)
            indexer_args = indexer_parser.parse_args(format_module_args(args.indexer_arg))
            try:
                index(db, blocklists, indexer_module, args, indexer_args)
            except KeyboardInterrupt:
                sys.exit(1)

        if args.generate_fingerprints:
            db.generate_fingerprints(args.source)

        if args.prune:
            prune(db, blocklists, args)

        if args.scanner:
            scanner_module = load_module("scanners", args.scanner)
            scanner_parser, other_args = get_module_parser(scanner_module)
            scanner_args = scanner_parser.parse_args(format_module_args(args.scanner_arg))
            try:
                scan(db, blocklists, scanner_module, args, scanner_args)
            except KeyboardInterrupt:
                sys.exit(1)

        if args.list_targets or args.list_unscanned:
            try:
                urls = db.get_urls(unscanned_only=args.list_unscanned, source=args.source, random=args.random)
                if args.count > 0:
                    urls = urls[:args.count]
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

        db.close()
    else:
        parser.print_usage()

    logging.shutdown()


def initialize_logger(log_file, verbose):
    log = logging.getLogger()

    if verbose and verbose >= 2:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    log_formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        log_filehandler = WatchedFileHandler(log_file, mode="a", encoding="utf-8")
        log_filehandler.setLevel(logging.DEBUG)
        log_filehandler.setFormatter(log_formatter)
        log.addHandler(log_filehandler)
    else:
        class LogFilter(logging.Filter):
            def __init__(self, level):
                self.level = level

            def filter(self, record):
                return record.levelno < self.level

        log_stdouthandler = logging.StreamHandler(sys.stdout)
        log_stdouthandler.setLevel(logging.DEBUG)
        log_stdouthandler.addFilter(LogFilter(logging.WARNING))
        log.addHandler(log_stdouthandler)

        log_stderrhandler = logging.StreamHandler(sys.stderr)
        log_stderrhandler.setLevel(logging.ERROR)
        log.addHandler(log_stderrhandler)


def load_module(category, name):
    module_name = "%s.%s" % (category, name)
    if __package__:
        module_name = "." + module_name
    try:
        module = importlib.import_module(module_name, package=__package__)
    except ImportError:
        logging.error("Module not found")
        sys.exit(1)

    return module


def get_initial_args_parser():
    config_dir = os.path.abspath(os.path.expanduser(
        os.environ.get("XDG_CONFIG_HOME")
        or os.environ.get("APPDATA")
        or os.path.join(os.environ["HOME"], ".config")
    ))

    initial_parser = argparse.ArgumentParser(
        description="dorkbot", add_help=False)
    initial_parser.add_argument("-c", "--config",
                                default=os.path.join(config_dir, "dorkbot", "dorkbot.ini"),
                                help="Configuration file")
    initial_parser.add_argument("-r", "--directory",
                                default=os.getcwd(),
                                help="Dorkbot directory (default location of db, tools, reports)")
    initial_parser.add_argument("--source", nargs="?", const=True, default=False,
                                help="Label associated with targets")
    initial_parser.add_argument("--show-defaults", action="store_true",
                                help="Show default values in help output")
    retrieval_options = initial_parser.add_argument_group("retrieval")
    retrieval_options.add_argument("--count", type=int, default=-1,
                                   help="number of targets to retrieve, or -1 for all")
    retrieval_options.add_argument("--random", action="store_true",
                                   help="retrieve targets in random order")
    initial_args, other_args = initial_parser.parse_known_args()

    return initial_args, other_args, initial_parser


def get_main_args_parser():
    initial_args, other_args, initial_parser = get_initial_args_parser()

    defaults = {
        "database": os.path.join(initial_args.directory, "dorkbot.db"),
    }

    if os.path.isfile(initial_args.config):
        config = configparser.ConfigParser()
        config.read(initial_args.config)
        try:
            config_items = config.items("dorkbot")
            defaults.update(dict(config_items))
        except KeyError:
            pass
        except configparser.NoSectionError as e:
            logging.debug(e)

    if initial_args.show_defaults:
        parser = argparse.ArgumentParser(parents=[initial_parser], add_help=False,
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    else:
        parser = argparse.ArgumentParser(parents=[initial_parser], add_help=False)

    parser.set_defaults(**defaults)
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

    targets = parser.add_argument_group('targets')
    targets.add_argument("-l", "--list-targets", action="store_true",
                         help="List targets in database")
    targets.add_argument("--list-unscanned", action="store_true",
                         help="List unscanned targets in database")
    targets.add_argument("--list-sources", action="store_true",
                         help="List sources in database")
    targets.add_argument("--add-target", metavar="TARGET",
                         help="Add a url to the target database")
    targets.add_argument("--delete-target", metavar="TARGET",
                         help="Delete a url from the target database")
    targets.add_argument("--flush-targets", action="store_true",
                         help="Delete all targets")

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
    scanning.add_argument("-x", "--reset-scanned", action="store_true",
                          help="Reset scanned status of all targets")

    fingerprints = parser.add_argument_group('fingerprints')
    fingerprints.add_argument("-g", "--generate-fingerprints", action="store_true",
                              help="Generate fingerprints for all targets")
    fingerprints.add_argument("-f", "--flush-fingerprints", action="store_true",
                              help="Delete all generated fingerprints")

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

    args = parser.parse_args(other_args, namespace=initial_args)
    return args, parser


def get_module_parser(module, parent_parser=None):
    initial_args, other_args, initial_parser = get_initial_args_parser()

    defaults = {}
    module_defaults = {}

    if os.path.isfile(initial_args.config):
        config = configparser.ConfigParser()
        config.read(initial_args.config)

        try:
            config_items = config.items("dorkbot")
            defaults.update(dict(config_items))
        except KeyError:
            pass
        except configparser.NoSectionError as e:
            logging.debug(e)

        try:
            module_config_items = config.items(module.__name__)
            module_defaults.update(dict(module_config_items))
        except KeyError:
            pass
        except configparser.NoSectionError as e:
            logging.debug(e)

    if parent_parser:
        initial_parser = parent_parser

    usage = "%(prog)s [args] -i/-s [module] -o/-p [module_arg[=value]] ..."
    epilog = "NOTE: module args are passed via -o/-p as key=value and do not themselves require hyphens"

    if initial_args.show_defaults:
        parser = argparse.ArgumentParser(parents=[initial_parser], usage=usage, epilog=epilog, add_help=False,
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    else:
        parser = argparse.ArgumentParser(parents=[initial_parser], usage=usage, epilog=epilog, add_help=False)

    parser.set_defaults(**defaults)
    module.populate_parser(initial_args, parser)
    parser.set_defaults(**module_defaults)

    return parser, other_args


def format_module_args(args_list):
    args = []

    if args_list:
        for arg in args_list:
            if arg.startswith("--"):
                args.add(arg)
            else:
                args.append("--" + arg)

    return args


def index(db, blocklists, indexer, args, indexer_args):
    indexer_name = indexer.__name__.split(".")[-1]
    logging.info("Indexing: %s %s", indexer_name, vars(indexer_args) if args.verbose else "")
    setattr(indexer_args, "directory", args.directory)
    urls, module_source = indexer.run(indexer_args)
    if args.source:
        source = args.source
    else:
        source = module_source

    targets = []
    for url in urls:
        if True in [blocklist.match(Target(url)) for blocklist in blocklists]:
            logging.debug("Ignoring (matches blocklist pattern): %s", url)
            continue

        url_parts = urlparse(url)
        quoted_path = quote(url_parts.path)
        encoded_query = urlencode(parse_qsl(url_parts.query, keep_blank_values=True))
        parsed_url = url_parts._replace(path=quoted_path, query=encoded_query)
        targets.append(parsed_url.geturl())

    db.add_targets(targets, source)


def prune(db, blocklists, args):
    logging.info("Pruning database")

    db.prune(blocklists, args.source, args.random)


def scan(db, blocklists, scanner, args, scanner_args):
    if not os.path.isdir(scanner_args.report_dir):
        try:
            os.makedirs(scanner_args.report_dir)
        except OSError as e:
            logging.error("Failed to create report directory - %s", str(e))
            sys.exit(1)

    scanned = 0
    while scanned < args.count or args.count == -1:
        url = db.get_next_target(source=args.source, random=args.random)
        if not url:
            break

        target = Target(url)

        if True in [blocklist.match(target) for blocklist in blocklists]:
            logging.debug("Deleting (matches blocklist pattern): %s", url)
            db.delete_target(url)
            continue

        logging.info("Scanning: %s %s", url, vars(scanner_args) if args.verbose else "")
        results = scanner.run(scanner_args, target)
        scanned += 1

        if results is False:
            logging.error("Scan failed: %s", target.url)
            continue

        target.endtime = generate_timestamp()
        target.write_report(scanner_args, results)


if __name__ == "__main__":
    main()
