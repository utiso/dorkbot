#!/usr/bin/env python3
if __package__:
    from ._version import __version__
else:
    from _version import __version__
import argparse
import configparser
import datetime
import hashlib
import importlib
import ipaddress
import json
import logging
import os
import random
import re
import socket
import sys
from contextlib import closing
from logging.handlers import WatchedFileHandler
from urllib.parse import urlparse


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
            or args.flush_fingerprints or args.list_unscanned:

        db = TargetDatabase(args.database)

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

        if args.flush_blocklist: blocklist.flush()
        if args.add_blocklist_item: blocklist.add(args.add_blocklist_item)
        if args.delete_blocklist_item: blocklist.delete(args.delete_blocklist_item)
        if args.list_blocklist:
            for blocklist in blocklists:
                for item in blocklist.get_parsed_items(): print(item)

        if args.flush_fingerprints: db.flush_fingerprints()

        if args.flush_targets: db.flush_targets()
        if args.add_target: db.add_target(args.add_target, args.source)
        if args.delete_target: db.delete_target(args.delete_target)
        db.close()

        if args.indexer:
            indexer_module = load_module("indexers", args.indexer)
            indexer_parser, other_args = get_module_parser(indexer_module)
            indexer_args = indexer_parser.parse_args(format_module_args(args.indexer_arg))
            try:
                index(db, blocklists, indexer_module, args, indexer_args)
            except KeyboardInterrupt:
                sys.exit(1)

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

        db = TargetDatabase(args.database)
        if args.list_targets or args.list_unscanned:
            try:
                urls = db.get_urls(unscanned_only=args.list_unscanned, source=args.source, randomize=args.random)
                if args.count > 0:
                    urls = urls[:args.count]
                for url in urls:
                    print(url)
            except BrokenPipeError:
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, sys.stdout.fileno())
                sys.exit(1)
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
    if __package__: module_name = "." + module_name
    try:
        module = importlib.import_module(module_name, package=__package__)
    except ImportError:
        logging.error("Module not found")
        sys.exit(1)

    return module


def get_initial_args_parser():
    config_dir = os.path.abspath(os.path.expanduser(
        os.environ.get("XDG_CONFIG_HOME") or
        os.environ.get("APPDATA") or
        os.path.join(os.environ["HOME"], ".config")
    ))

    initial_parser = argparse.ArgumentParser(
        description="dorkbot", add_help=False)
    initial_parser.add_argument("-c", "--config", \
                                default=os.path.join(config_dir, "dorkbot", "dorkbot.ini"), \
                                help="Configuration file")
    initial_parser.add_argument("-r", "--directory", \
                                default=os.getcwd(), \
                                help="Dorkbot directory (default location of db, tools, reports)")
    initial_parser.add_argument("--source", nargs="?", const=True, default=False, \
                                help="Label associated with targets")
    initial_parser.add_argument("--show-defaults", action="store_true", \
                                help="Show default values in help output")
    retrieval_options = initial_parser.add_argument_group("retrieval")
    retrieval_options.add_argument("--count", type=int, default=-1, \
                          help="number of targets to retrieve, or -1 for all")
    retrieval_options.add_argument("--random", action="store_true", \
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
        parser = argparse.ArgumentParser(parents=[initial_parser], add_help=False, \
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    else:
        parser = argparse.ArgumentParser(parents=[initial_parser], add_help=False)

    parser.set_defaults(**defaults)
    parser.add_argument("-h", "--help", action="store_true", \
                        help="Show program (or specified module) help")
    parser.add_argument("--log", \
                        help="Path to log file")
    parser.add_argument("-v", "--verbose", action="count", \
                        help="Enable verbose logging (can be used multiple times to increase verbosity)")
    parser.add_argument("-V", "--version", action="version", \
                        version="%(prog)s " + __version__, help="Print version")

    database = parser.add_argument_group('database')
    database.add_argument("-d", "--database", \
                          help="Database file/uri")
    database.add_argument("-u", "--prune", action="store_true", \
                          help="Apply fingerprinting and blocklist without scanning")

    targets = parser.add_argument_group('targets')
    targets.add_argument("-l", "--list-targets", action="store_true", \
                         help="List targets in database")
    targets.add_argument("--list-unscanned", action="store_true", \
                         help="List unscanned targets in database")
    targets.add_argument("--add-target", metavar="TARGET", \
                         help="Add a url to the target database")
    targets.add_argument("--delete-target", metavar="TARGET", \
                         help="Delete a url from the target database")
    targets.add_argument("--flush-targets", action="store_true", \
                         help="Delete all targets")

    indexing = parser.add_argument_group('indexing')
    indexing.add_argument("-i", "--indexer", \
                          help="Indexer module to use")
    indexing.add_argument("-o", "--indexer-arg", action="append", \
                          help="Pass an argument to the indexer module (can be used multiple times)")

    scanning = parser.add_argument_group('scanning')
    scanning.add_argument("-s", "--scanner", \
                          help="Scanner module to use")
    scanning.add_argument("-p", "--scanner-arg", action="append", \
                          help="Pass an argument to the scanner module (can be used multiple times)")

    fingerprints = parser.add_argument_group('fingerprints')
    fingerprints.add_argument("-f", "--flush-fingerprints", action="store_true", \
                              help="Delete all fingerprints of previously-scanned items")

    blocklist = parser.add_argument_group('blocklist')
    blocklist.add_argument("--list-blocklist", action="store_true", \
                           help="List internal blocklist entries")
    blocklist.add_argument("--add-blocklist-item", metavar="ITEM", \
                           help="Add an ip/host/regex pattern to the internal blocklist")
    blocklist.add_argument("--delete-blocklist-item", metavar="ITEM", \
                           help="Delete an item from the internal blocklist")
    blocklist.add_argument("--flush-blocklist", action="store_true", \
                           help="Delete all internal blocklist items")
    blocklist.add_argument("-b", "--external-blocklist", action="append", \
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

    usage="%(prog)s [args] -i/-s [module] -o/-p [module_arg[=value]] ..."
    epilog="NOTE: module args are passed via -o/-p as key=value and do not themselves require hyphens"

    if initial_args.show_defaults:
        parser = argparse.ArgumentParser(parents=[initial_parser], usage=usage, epilog=epilog, add_help=False, \
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
            targets.append(url)

    db.connect()
    db.add_targets(targets, source)
    db.close()


def prune(db, blocklists, args):
    logging.info("Pruning database")

    db.connect()
    db.prune(blocklists, args.random)
    db.close()


def scan(db, blocklists, scanner, args, scanner_args):
    if not os.path.isdir(scanner_args.report_dir):
        try:
            os.makedirs(scanner_args.report_dir)
        except OSError as e:
            logging.error("Failed to create report directory - %s", str(e))
            sys.exit(1)

    scanned = 0
    while scanned < args.count or args.count == -1:
        db.connect()
        target = db.get_next_target(random=args.random)
        if not target:
            break

        if True in [blocklist.match(target) for blocklist in blocklists]:
            logging.debug("Deleting (matches blocklist pattern): %s", target.url)
            db.delete_target(target.url)
            continue

        db.close()

        logging.info("Scanning: %s %s", target.url, vars(scanner_args) if args.verbose else "")
        results = scanner.run(scanner_args, target)
        scanned += 1

        if results == False:
            logging.error("Scan failed: %s", target.url)
            continue

        target.endtime = generate_timestamp()
        target.write_report(scanner_args, results)


def generate_fingerprint(target):
    url_parts = urlparse(target.url)
    netloc = url_parts.netloc
    depth = str(url_parts.path.count("/"))
    page = url_parts.path.split("/")[-1]
    params = []
    for param in url_parts.query.split("&"):
        split = param.split("=", 1)
        if len(split) == 2 and split[1]:
            params.append(split[0])
    fingerprint = "|".join((netloc, depth, page, ",".join(sorted(params))))
    return generate_hash(fingerprint)


def generate_timestamp():
    return datetime.datetime.now().astimezone().isoformat()


def generate_hash(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()


class TargetDatabase:
    def __init__(self, database):
        self.connect_kwargs = {}
        if database.startswith("postgresql://"):
            self.database = database
            module_name = "psycopg2"
            self.insert = "INSERT"
            self.conflict = "ON CONFLICT DO NOTHING"
        elif database.startswith("phoenixdb://"):
            module_name = "phoenixdb"
            self.database = database[12:]
            self.insert = "UPSERT"
            self.conflict = ""
            self.connect_kwargs["autocommit"] = True
        else:
            module_name = "sqlite3"
            self.database = os.path.expanduser(database)
            database_dir = os.path.dirname(self.database)
            self.insert = "INSERT OR REPLACE"
            self.conflict = ""

        try:
            self.module = importlib.import_module(module_name, package=None)
        except ModuleNotFoundError:
            logging.error("Failed to load required module - %s", module_name)
            sys.exit(1)

        if self.module.paramstyle == "qmark":
            self.param = "?"
        else:
            self.param = "%s"

        if module_name == "sqlite3" and not os.path.isfile(self.database):
            logging.debug("Creating database file - %s", self.database)

            if database_dir and not os.path.isdir(database_dir):
                try:
                    os.makedirs(database_dir)
                except OSError as e:
                    logging.error("Failed to create directory - %s", str(e))
                    sys.exit(1)

        self.connect()
        self.execute("CREATE TABLE IF NOT EXISTS targets (url VARCHAR PRIMARY KEY, source VARCHAR, scanned INTEGER DEFAULT 0)")
        self.execute("CREATE TABLE IF NOT EXISTS fingerprints (fingerprint VARCHAR PRIMARY KEY)")
        self.execute("CREATE TABLE IF NOT EXISTS blocklist (item VARCHAR PRIMARY KEY)")

    def connect(self, retries=3):
        for i in range(retries):
            try:
                self.db = self.module.connect(self.database, **self.connect_kwargs)
                break
            except self.module.Error as e:
                retry_conditions = ["Connection timed out"]
                if i < retries-1 and any(error in str(e) for error in retry_conditions):
                    logging.warning(f"Database connection failed (retrying) - {str(e)}")
                    continue
                else:
                    logging.error(f"Database connection failed (will not retry) - {str(e)}")
                    sys.exit(1)

    def close(self):
        self.db.close()

    def execute(self, *sql, many=False, fetchone=False, fetchall=False, retries=3):
        if len(sql) == 2:
            statement, arguments = sql
        else:
            statement = sql[0]
            arguments = ""

        for i in range(retries):
            try:
                with self.db, closing(self.db.cursor()) as c:
                    result = None
                    if many:
                        c.executemany(statement, arguments)
                    else:
                        c.execute(statement, arguments)
                    if fetchone:
                        result = c.fetchone()
                    elif fetchall:
                        result = c.fetchall()
                    return result
            except self.module.Error as e:
                retry_conditions = [
                    "connection already closed",
                    "server closed the connection unexpectedly"
                ]
                if i < retries-1 and any(error in str(e) for error in retry_conditions):
                    logging.warning(f"Database execution failed (retrying) - {str(e)}")
                    self.connect()
                    continue
                else:
                    logging.error(f"Database execution failed (will not retry) - {str(e)}")
                    sys.exit(1)

    def get_urls(self, unscanned_only=False, source=False, randomize=False):
        fields = "url"
        if source is True:
            fields += ",source"

        sql = f"SELECT {fields} FROM targets"
        if unscanned_only:
            sql += " WHERE scanned != 1"

        if source and source is not True:
            if "WHERE" in sql:
                sql += " AND "
            else:
                sql += " WHERE "
            sql += "source = %s" % self.param
            rows = self.execute(sql, (source,), fetchall=True)
        else:
            rows = self.execute(sql, fetchall=True)
        urls = [" | ".join(row) for row in rows]

        if randomize:
            random.shuffle(urls)

        return urls

    def get_next_target(self, random=False):
        sql = "SELECT url FROM targets WHERE scanned != 1"
        if random:
            sql += " ORDER BY RANDOM()"

        while True:
            row = self.execute(sql, fetchone=True)
            if not row:
                target = None
                break
            url = row[0]
            target = Target(url)
            fingerprint = generate_fingerprint(target)
            self.mark_scanned(url)
            if self.get_scanned(fingerprint):
                logging.debug("Skipping (matches fingerprint of previous scan): %s", target.url)
                continue
            else:
                self.add_fingerprint(fingerprint)
                break

        return target

    def add_target(self, url, source=None):
        self.execute("%s INTO targets (url, source) VALUES (%s, %s) %s" % (self.insert, self.param, self.param, self.conflict), (url, source))

    def add_targets(self, urls, source=None, chunk_size=1000):
        for x in range(0, len(urls), chunk_size):
            urls_chunk = urls[x:x+chunk_size]
            self.execute("%s INTO targets (url, source) VALUES (%s, %s) %s" % (self.insert, self.param, self.param, self.conflict), [(url, source) for url in urls_chunk], many=True)

    def delete_target(self, url):
        self.execute("DELETE FROM targets WHERE url=(%s)" % self.param, (url,))

    def get_scanned(self, fingerprint):
        row = self.execute("SELECT fingerprint FROM fingerprints WHERE fingerprint = (%s)" % self.param, (fingerprint,), fetchone=True)
        if row:
            return True
        else:
            return False

    def add_fingerprint(self, fingerprint):
        self.execute("%s INTO fingerprints VALUES (%s)" % (self.insert, self.param), (fingerprint,))

    def mark_scanned(self, url):
        self.execute("UPDATE targets SET scanned = 1 WHERE url = %s" % (self.param,), (url,))

    def flush_fingerprints(self):
        logging.info("Flushing fingerprints")
        self.execute("DELETE FROM fingerprints")
        self.execute("UPDATE targets SET scanned = 0")

    def flush_targets(self):
        logging.info("Flushing targets")
        self.execute("DELETE FROM targets")

    def prune(self, blocklists, randomize=False):
        fingerprints = set()

        urls = self.get_urls()

        if randomize:
            random.shuffle(urls)

        for url in urls:
            target = Target(url)

            fingerprint = generate_fingerprint(target)
            if fingerprint in fingerprints or self.get_scanned(fingerprint):
                logging.debug("Marking scanned (matches fingerprint of another target): %s", target.url)
                self.mark_scanned(target.url)
                continue

            if True in [blocklist.match(target) for blocklist in blocklists]:
                logging.debug("Deleting (matches blocklist pattern): %s", target.url)
                self.delete_target(target.url)
                continue

            fingerprints.add(fingerprint)


class Target:
    def __init__(self, url):
        self.url = url
        self.hash = ""
        self.starttime = generate_timestamp()

        url_parts = urlparse(url)
        self.host = url_parts.hostname

        try:
            resolved_ip = socket.gethostbyname(self.host)
            self.ip = ipaddress.ip_address(resolved_ip)
        except socket.gaierror:
            self.ip = None
            pass
        except Exception:
            logging.exception("Failed to resolve hostname: %s", self.host)

    def get_hash(self):
        if not self.hash:
            self.hash = generate_hash(self.url)
        return self.hash

    def write_report(self, scanner_args, vulnerabilities):
        vulns = {}
        vulns["vulnerabilities"] = vulnerabilities
        vulns["starttime"] = str(self.starttime)
        vulns["endtime"] = str(self.endtime)
        vulns["url"] = self.url
        vulns["label"] = scanner_args.label

        if scanner_args.report_filename:
            report_filename = scanner_args.report_filename
        else:
            report_filename = self.get_hash() + ".json"

        filename = os.path.join(scanner_args.report_dir, report_filename)

        if scanner_args.report_append:
            report_mode = "a"
        else:
            report_mode = "w"

        indent = scanner_args.report_indent
        if indent and indent.isdigit():
                indent = int(indent)

        with open(filename, report_mode) as outfile:
            json.dump(vulns, outfile, indent=indent, sort_keys=True)
            outfile.write('\n')
            logging.info("Report saved to: %s" % outfile.name)


class Blocklist:
    def __init__(self, blocklist):
        self.connect_kwargs = {}
        self.ip_set = set()
        self.host_set = set()
        self.regex_set = set()

        if blocklist.startswith("postgresql://"):
            self.database = blocklist
            module_name = "psycopg2"
            self.insert = "INSERT"
            self.conflict = "ON CONFLICT DO NOTHING"
        elif blocklist.startswith("phoenixdb://"):
            self.database = blocklist[12:]
            module_name = "phoenixdb"
            self.insert = "UPSERT"
            self.conflict = ""
            self.connect_kwargs["autocommit"] = True
        elif blocklist.startswith("sqlite3://"):
            self.database = os.path.expanduser(blocklist[10:])
            module_name = "sqlite3"
            database_dir = os.path.dirname(self.database)
            self.insert = "INSERT OR REPLACE"
            self.conflict = ""
            if database_dir and not os.path.isdir(database_dir):
                try:
                    os.makedirs(database_dir)
                except OSError as e:
                    logging.error("Failed to create directory - %s", str(e))
                    sys.exit(1)
        else:
            self.database = False
            self.filename = blocklist
            try:
                self.blocklist_file = open(self.filename, "r")
            except Exception as e:
                logging.error("Failed to read blocklist file - %s", str(e))
                sys.exit(1)

        if self.database:
            self.module = importlib.import_module(module_name, package=None)

            if self.module.paramstyle == "qmark":
                self.param = "?"
            else:
                self.param = "%s"

            self.connect()
            self.execute("CREATE TABLE IF NOT EXISTS blocklist (item VARCHAR PRIMARY KEY)")

        self.parse_list(self.read_items())

    def connect(self, retries=3):
        if self.database:
            for i in range(retries):
                try:
                    self.db = self.module.connect(self.database, **self.connect_kwargs)
                    break
                except self.module.Error as e:
                    retry_conditions = ["Connection timed out"]
                    if i < retries-1 and any(error in str(e) for error in retry_conditions):
                        logging.warning(f"Blocklist database connection failed (retrying) - {str(e)}")
                        continue
                    else:
                        logging.error(f"Blocklist database connection failed (will not retry) - {str(e)}")
                        sys.exit(1)

        else:
            try:
                self.blocklist_file = open(self.filename, "a")
            except Exception as e:
                logging.error("Failed to read blocklist file - %s", str(e))
                sys.exit(1)

    def close(self):
        if self.database:
            self.db.close()
        else:
            self.blocklist_file.close()

    def execute(self, *sql, many=False, fetchone=False, fetchall=False, retries=3):
        if len(sql) == 2:
            statement, arguments = sql
        else:
            statement = sql[0]
            arguments = ""

        for i in range(retries):
            try:
                with self.db, closing(self.db.cursor()) as c:
                    result = None
                    if many:
                        c.executemany(statement, arguments)
                    else:
                        c.execute(statement, arguments)
                    if fetchone:
                        result = c.fetchone()
                    elif fetchall:
                        result = c.fetchall()
                    return result
            except self.module.Error as e:
                retry_conditions = [
                    "connection already closed",
                    "server closed the connection unexpectedly"
                ]
                if i < retries-1 and any(error in str(e) for error in retry_conditions):
                    logging.warning(f"Database execution failed (retrying) - {str(e)}")
                    self.connect()
                    continue
                else:
                    logging.error(f"Database execution failed (will not retry) - {str(e)}")
                    sys.exit(1)

    def parse_list(self, items):
        for item in items:
            if item.startswith("ip:"):
                ip = item.split(":")[1]
                try:
                    ip_net = ipaddress.ip_network(ip)
                except ValueError as e:
                    logging.error("Could not parse blocklist item as ip - %s", str(e))
                self.ip_set.add(ip_net)
            elif item.startswith("host:"):
                self.host_set.add(item.split(":")[1])
            elif item.startswith("regex:"):
                self.regex_set.add(item.split(":")[1])
            else:
                logging.warning("Could not parse blocklist item - %s", item)

        pattern = "|".join(self.regex_set)
        if pattern:
            self.regex = re.compile(pattern)
        else:
            self.regex = None

    def get_parsed_items(self):
        parsed_ip_set = set()
        for ip_net in self.ip_set:
            if ip_net.num_addresses == 1:
                parsed_ip_set.add(str(ip_net[0]))
            else:
                parsed_ip_set.add(str(ip_net))

        return ["ip:" + item for item in parsed_ip_set] + \
               ["host:" + item for item in self.host_set] + \
               ["regex:" + item for item in self.regex_set]

    def read_items(self):
        if self.database:
            rows = self.execute("SELECT item FROM blocklist", fetchall=True)
            items = [row[0] for row in rows]
        else:
            items = self.blocklist_file.read().splitlines()

        return items

    def add(self, item):
        self.connect()

        if item.startswith("ip:"):
            ip = item.split(":")[1]
            try:
                ip_net = ipaddress.ip_network(ip)
            except ValueError as e:
                logging.error("Could not parse blocklist item as ip - %s", str(e))
                sys.exit(1)
            self.ip_set.add(ip_net)
        elif item.startswith("host:"):
            self.host_set.add(item.split(":")[1])
        elif item.startswith("regex:"):
            self.regex_set.add(item.split(":")[1])
        else:
            logging.error("Could not parse blocklist item - %s", item)
            sys.exit(1)

        if self.database:
            self.execute("%s INTO blocklist VALUES (%s)" % (self.insert, self.param), (item,))
        else:
            logging.warning("Add ignored (not implemented for file-based blocklist)")

        self.close()

    def delete(self, item):
        self.connect()

        if self.database:
            self.execute("DELETE FROM blocklist WHERE item=(%s)" % self.param, (item,))
        else:
            logging.warning("Delete ignored (not implemented for file-based blocklist)")

        self.close()

    def match(self, target):
        if self.regex and self.regex.match(target.url):
            return True

        if target.host in self.host_set:
            return True

        for ip_net in self.ip_set:
            if target.ip and target.ip in ip_net:
                return True

        return False

    def flush(self):
        logging.info("Flushing blocklist")
        if self.database:
            self.execute("DELETE FROM blocklist")
        else:
            try:
                os.unlink(self.filename)
            except OSError as e:
                logging.error("Failed to delete blocklist file - %s", str(e))
                sys.exit(1)

        self.regex = None
        self.regex_set = set()
        self.ip_set = set()
        self.host_set = set()


if __name__ == "__main__":
    main()
