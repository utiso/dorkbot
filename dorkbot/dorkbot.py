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
    args, parser = get_args_parser()
    initialize_logger(args.log, args.verbose)
    indexer_options = parse_options(args.indexer_option)
    scanner_options = parse_options(args.scanner_option)

    if args.directory and not os.path.isdir(args.directory):
        logging.debug("Creating directory - %s", args.directory)
        try:
            os.makedirs(args.directory)
        except OSError as e:
            logging.error("Failed to create directory - %s", str(e))
            sys.exit(1)

    if args.indexer or args.prune or args.scanner \
            or args.list_targets or args.flush_targets \
            or args.add_target or args.delete_target \
            or args.list_blacklist or args.flush_blacklist \
            or args.add_blacklist_item or args.delete_blacklist_item \
            or args.flush_fingerprints or args.list_unscanned:

        db = TargetDatabase(args.database)
        if args.blacklist:
            blacklist = Blacklist(args.blacklist)
        else:
            pattern = "^[^:]+://.*$"
            regex = re.compile(pattern)
            if (regex.match(args.database)):
                blacklist = Blacklist(args.database)
            else:
                blacklist = Blacklist("sqlite3://" + args.database)

        if args.flush_targets: db.flush_targets()
        if args.flush_blacklist: blacklist.flush()
        if args.flush_fingerprints: db.flush_fingerprints()
        if args.add_target: db.add_target(args.add_target, indexer_options.get("source"))
        if args.delete_target: db.delete_target(args.delete_target)
        if args.list_targets or args.list_unscanned:
            try:
                for url in db.get_urls(unscanned_only=args.list_unscanned, source=indexer_options.get("source")): print(url)
            except BrokenPipeError:
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, sys.stdout.fileno())
                sys.exit(1)
        db.close()

        if args.add_blacklist_item: blacklist.add(args.add_blacklist_item)
        if args.delete_blacklist_item: blacklist.delete(args.delete_blacklist_item)
        if args.list_blacklist:
            for item in blacklist.get_parsed_items(): print(item)

        if args.indexer:
            index(db, blacklist, load_module("indexers", args.indexer), args, indexer_options)

        if args.prune:
            prune(db, blacklist, args, scanner_options)

        if args.scanner:
            scan(db, blacklist, load_module("scanners", args.scanner), args, scanner_options)

    else:
        parser.print_usage()

    logging.shutdown()


def initialize_logger(log_file, verbose):
    log = logging.getLogger()

    if verbose:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    log_formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    if log_file:
        log_filehandler = WatchedFileHandler(log_file, mode="a", encoding="utf-8")
        log_filehandler.setLevel(logging.DEBUG)
        log_filehandler.setFormatter(log_formatter)
        log.addHandler(log_filehandler)
    else:
        log_streamhandler = logging.StreamHandler()
        log_streamhandler.setLevel(logging.DEBUG)
        log_streamhandler.setFormatter(log_formatter)
        log.addHandler(log_streamhandler)


def load_module(category, name):
    module_name = "%s.%s" % (category, name)
    if __package__: module_name = "." + module_name
    try:
        module = importlib.import_module(module_name, package=__package__)
    except ImportError:
        logging.error("Module not found")
        sys.exit(1)

    return module


def get_args_parser():
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
    initial_args, other_args = initial_parser.parse_known_args()

    defaults = {
        "database": os.path.join(initial_args.directory, "dorkbot.db"),
    }

    if os.path.isfile(initial_args.config):
        config = configparser.SafeConfigParser()
        config.read(initial_args.config)
        options = config.items("dorkbot")
        defaults.update(dict(options))

    parser = argparse.ArgumentParser(parents=[initial_parser])
    parser.set_defaults(**defaults)
    parser.add_argument("--log", \
                        help="Path to log file")
    parser.add_argument("-v", "--verbose", action="store_true", \
                        help="Enable verbose logging (DEBUG output)")
    parser.add_argument("-V", "--version", action="version", \
                        version="%(prog)s " + __version__, help="Print version")

    database = parser.add_argument_group('database')
    database.add_argument("-d", "--database", \
                          help="Database file/uri")
    database.add_argument("-u", "--prune", action="store_true", \
                          help="Apply fingerprinting and blacklist without scanning")

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
    indexing.add_argument("-o", "--indexer-option", action="append", \
                          help="Pass an option to the indexer (can be used multiple times)")

    scanning = parser.add_argument_group('scanning')
    scanning.add_argument("-s", "--scanner", \
                          help="Scanner module to use")
    scanning.add_argument("-p", "--scanner-option", action="append", \
                          help="Pass an option to the scanner (can be used multiple times)")

    fingerprints = parser.add_argument_group('fingerprints')
    fingerprints.add_argument("-f", "--flush-fingerprints", action="store_true", \
                              help="Delete all fingerprints of previously-scanned items")

    blacklist = parser.add_argument_group('blacklist')
    blacklist.add_argument("-b", "--blacklist", \
                           help="Blacklist file/uri")
    blacklist.add_argument("--list-blacklist", action="store_true", \
                           help="List blacklist entries")
    blacklist.add_argument("--add-blacklist-item", metavar="ITEM", \
                           help="Add an ip/host/regex pattern to the blacklist")
    blacklist.add_argument("--delete-blacklist-item", metavar="ITEM", \
                           help="Delete an item from the blacklist")
    blacklist.add_argument("--flush-blacklist", action="store_true", \
                           help="Delete all blacklist items")

    args = parser.parse_args(other_args)
    args.directory = initial_args.directory
    return args, parser


def index(db, blacklist, indexer, args, options):
    indexer_name = indexer.__name__.split(".")[-1]
    indexer_options = ",".join(["%s=%s" % (key, val) for key, val in options.items()])
    logging.info("Indexing: %s %s", indexer_name, indexer_options)
    options["directory"] = args.directory
    urls, module_source = indexer.run(options)
    source = options.get("source", module_source)

    targets = []
    for url in urls:
        if not blacklist.match(Target(url)): targets.append(url)

    db.connect()
    db.add_targets(targets, source)
    db.close()


def prune(db, blacklist, args, options):
    if "random" in options:
        randomize = True
    else:
        randomize = False

    logging.info("Pruning database")

    db.connect()
    db.prune(blacklist, randomize)
    db.close()


def scan(db, blacklist, scanner, args, options):
    options["directory"] = args.directory
    report_dir = options.get("reports", os.path.join(args.directory, "reports"))
    if not os.path.isdir(report_dir):
        try:
            os.makedirs(report_dir)
        except OSError as e:
            logging.error("Failed to create report directory - %s", str(e))
            sys.exit(1)

    count = int(options.get("count", "-1"))
    label = options.get("label", "")

    scanned = 0
    while scanned < count or count == -1:
        db.connect()
        target = db.get_next_target(random=options.get("random", False))
        if not target:
            break

        if blacklist.match(target):
            logging.debug("Deleting (matches blacklist pattern): %s", target.url)
            db.delete_target(target.url)
            continue

        db.close()

        logging.info("Scanning: %s", target.url)
        results = scanner.run(options, target)
        scanned += 1

        if results == False:
            logging.error("Scan failed: %s", target.url)
            continue

        target.endtime = generate_timestamp()
        target.write_report(report_dir, label, results)


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


def parse_options(options_list):
    options = dict()

    if options_list:
        for option in options_list:
            if "=" in option:
                key, value = option.split("=", 1)
            else:
                key, value = option, True
            options.update({key: value})

    return options


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
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("CREATE TABLE IF NOT EXISTS targets (url VARCHAR PRIMARY KEY, source VARCHAR, scanned INTEGER DEFAULT 0)")
                c.execute("CREATE TABLE IF NOT EXISTS fingerprints (fingerprint VARCHAR PRIMARY KEY)")
                c.execute("CREATE TABLE IF NOT EXISTS blacklist (item VARCHAR PRIMARY KEY)")
        except self.module.Error as e:
            logging.error("Failed to load database - %s", str(e))
            sys.exit(1)

    def connect(self):
        try:
            self.db = self.module.connect(self.database, **self.connect_kwargs)
        except self.module.Error as e:
            logging.error("Error loading database - %s", str(e))
            sys.exit(1)

    def close(self):
        self.db.close()

    def get_urls(self, unscanned_only=False, source=False):
        fields = "url"
        if source is True:
            fields += ",source"

        sql = f"SELECT {fields} FROM targets"
        if unscanned_only:
            sql += " WHERE scanned != 1"

        try:
            with self.db, closing(self.db.cursor()) as c:
                if source and source is not True:
                    if "WHERE" in sql:
                        sql += " AND "
                    else:
                        sql += " WHERE "
                    sql += "source = %s" % self.param
                    c.execute(sql, (source,))
                else:
                    c.execute(sql)
                urls = [" | ".join(row) for row in c.fetchall()]
        except self.module.Error as e:
            logging.error("Failed to get targets - %s", str(e))
            sys.exit(1)

        return urls

    def get_next_target(self, random=False):
        sql = "SELECT url FROM targets WHERE scanned != 1"
        if random:
            sql += " ORDER BY RANDOM()"

        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute(sql)
                while True:
                    row = c.fetchone()
                    if not row:
                        target = None
                        break
                    url = row[0]
                    target = Target(url)
                    fingerprint = generate_fingerprint(target)
                    self.mark_scanned(url, c)
                    if self.get_scanned(fingerprint, c):
                        logging.debug("Skipping (matches fingerprint of previous scan): %s", target.url)
                        continue
                    else:
                        c.execute("%s INTO fingerprints VALUES (%s)" % (self.insert, self.param), (fingerprint,))
                        break
        except self.module.Error as e:
            logging.error("Failed to get next target - %s", str(e))
            sys.exit(1)

        return target

    def add_target(self, url, source=None):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("%s INTO targets (url, source) VALUES (%s, %s) %s" % (self.insert, self.param, self.param, self.conflict), (url, source))
        except self.module.Error as e:
            logging.error("Failed to add target - %s", str(e))
            sys.exit(1)

    def add_targets(self, urls, source=None):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.executemany("%s INTO targets (url, source) VALUES (%s, %s) %s" % (self.insert, self.param, self.param, self.conflict),
                              [(url, source) for url in urls])
        except self.module.Error as e:
            logging.error("Failed to add target - %s", str(e))
            sys.exit(1)

    def delete_target(self, url):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM targets WHERE url=(%s)" % self.param, (url,))
        except self.module.Error as e:
            logging.error("Failed to delete target - %s", str(e))
            sys.exit(1)

    def get_scanned(self, fingerprint, cursor):
        for i in range(3):
            try:
                cursor.execute("SELECT fingerprint FROM fingerprints WHERE fingerprint = (%s)" % self.param, (fingerprint,))
                row = cursor.fetchone()
                break
            except self.module.Error as e:
                if "connection already closed" in str(e) or "server closed the connection unexpectedly" in str(e):
                    logging.warning("Failed to look up fingerprint (retrying) - %s", str(e))
                    self.connect()
                    continue
                else:
                    logging.error("Failed to look up fingerprint - %s", str(e))
                    sys.exit(1)

        if row:
            return row[0]
        else:
            return False

    def mark_scanned(self, url, cursor):
        for i in range(3):
            try:
                cursor.execute("UPDATE targets SET scanned = 1 WHERE url = %s" % (self.param,), (url,))
            except self.module.Error as e:
                if "connection already closed" in str(e) or "server closed the connection unexpectedly" in str(e):
                    logging.warning("Failed to mark target as scanned (retrying) - %s", str(e))
                    self.connect()
                    continue
                else:
                    logging.error("Failed to mark target as scanned - %s", str(e))
                    sys.exit(1)

    def flush_fingerprints(self):
        logging.info("Flushing fingerprints")
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM fingerprints")
                c.execute("UPDATE targets SET scanned = 0")
        except self.module.Error as e:
            logging.error("Failed to flush fingerprints - %s", str(e))
            sys.exit(1)

    def flush_targets(self):
        logging.info("Flushing targets")
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM targets")
        except self.module.Error as e:
            logging.error("Failed to flush targets - %s", str(e))
            sys.exit(1)

    def prune(self, blacklist, randomize=False):
        fingerprints = set()

        urls = self.get_urls()

        if randomize:
            random.shuffle(urls)

        for url in urls:
            target = Target(url)

            fingerprint = generate_fingerprint(target)
            with self.db, closing(self.db.cursor()) as c:
                if fingerprint in fingerprints or self.get_scanned(fingerprint, c):
                    logging.debug("Marking scanned (matches fingerprint of another target): %s", target.url)
                    self.mark_scanned(target.url, c)
                    continue

            if blacklist.match(target):
                logging.debug("Deleting (matches blacklist pattern): %s", target.url)
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

    def write_report(self, report_dir, label, vulnerabilities):
        vulns = {}
        vulns["vulnerabilities"] = vulnerabilities
        vulns["starttime"] = str(self.starttime)
        vulns["endtime"] = str(self.endtime)
        vulns["url"] = self.url
        vulns["label"] = label

        filename = os.path.join(report_dir, self.get_hash() + ".json")

        with open(filename, "w") as outfile:
            json.dump(vulns, outfile, indent=4, sort_keys=True)
            print("Report saved to: %s" % outfile.name)


class Blacklist:
    def __init__(self, blacklist):
        self.connect_kwargs = {}
        self.ip_set = set()
        self.host_set = set()
        self.regex_set = set()

        if blacklist.startswith("postgresql://"):
            self.database = blacklist
            module_name = "psycopg2"
            self.insert = "INSERT"
            self.conflict = "ON CONFLICT DO NOTHING"
        elif blacklist.startswith("phoenixdb://"):
            self.database = blacklist[12:]
            module_name = "phoenixdb"
            self.insert = "UPSERT"
            self.conflict = ""
            self.connect_kwargs["autocommit"] = True
        elif blacklist.startswith("sqlite3://"):
            self.database = os.path.expanduser(blacklist[10:])
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
            self.filename = blacklist
            try:
                self.blacklist_file = open(self.filename, "r")
            except Exception as e:
                logging.error("Failed to read blacklist file - %s", str(e))
                sys.exit(1)

        if self.database:
            self.module = importlib.import_module(module_name, package=None)

            if self.module.paramstyle == "qmark":
                self.param = "?"
            else:
                self.param = "%s"

            self.connect()
            try:
                with self.db, closing(self.db.cursor()) as c:
                    c.execute("CREATE TABLE IF NOT EXISTS blacklist (item VARCHAR PRIMARY KEY)")
            except self.module.Error as e:
                logging.error("Failed to load blacklist database - %s", str(e))
                sys.exit(1)

        self.parse_list(self.read_items())

    def connect(self):
        if self.database:
            try:
                self.db = self.module.connect(self.database, **self.connect_kwargs)
            except self.module.Error as e:
                logging.error("Error loading database - %s", str(e))
                sys.exit(1)
        else:
            try:
                self.blacklist_file = open(self.filename, "a")
            except Exception as e:
                logging.error("Failed to read blacklist file - %s", str(e))
                sys.exit(1)

    def close(self):
        if self.database:
            self.db.close()
        else:
            self.blacklist_file.close()

    def parse_list(self, items):
        for item in items:
            if item.startswith("ip:"):
                ip = item.split(":")[1]
                try:
                    ip_net = ipaddress.ip_network(ip)
                except ValueError as e:
                    logging.error("Could not parse blacklist item as ip - %s", str(e))
                self.ip_set.add(ip_net)
            elif item.startswith("host:"):
                self.host_set.add(item.split(":")[1])
            elif item.startswith("regex:"):
                self.regex_set.add(item.split(":")[1])
            else:
                logging.warning("Could not parse blacklist item - %s", item)

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
            try:
                with self.db, closing(self.db.cursor()) as c:
                    c.execute("SELECT item FROM blacklist")
                    items = [row[0] for row in c.fetchall()]
            except self.module.Error as e:
                logging.error("Failed to get targets - %s", str(e))
                sys.exit(1)
        else:
            items = self.blacklist_file.read().splitlines()

        return items

    def add(self, item):
        self.connect()

        if item.startswith("ip:"):
            ip = item.split(":")[1]
            try:
                ip_net = ipaddress.ip_network(ip)
            except ValueError as e:
                logging.error("Could not parse blacklist item as ip - %s", str(e))
                sys.exit(1)
            self.ip_set.add(ip_net)
        elif item.startswith("host:"):
            self.host_set.add(item.split(":")[1])
        elif item.startswith("regex:"):
            self.regex_set.add(item.split(":")[1])
        else:
            logging.error("Could not parse blacklist item - %s", item)
            sys.exit(1)

        if self.database:
            try:
                with self.db, closing(self.db.cursor()) as c:
                    c.execute("%s INTO blacklist VALUES (%s)" % (self.insert, self.param), (item,))
            except self.module.Error as e:
                logging.error("Failed to add blacklist item - %s", str(e))
                sys.exit(1)
        else:
            logging.warning("Add ignored (not implemented for file-based blacklist)")

        self.close()

    def delete(self, item):
        self.connect()

        if self.database:
            try:
                with self.db, closing(self.db.cursor()) as c:
                    c.execute("DELETE FROM blacklist WHERE item=(%s)" % self.param, (item,))
            except self.module.Error as e:
                logging.error("Failed to delete blacklist item - %s", str(e))
                sys.exit(1)
        else:
            logging.warning("Delete ignored (not implemented for file-based blacklist)")

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
        logging.info("Flushing blacklist")
        if self.database:
            try:
                with self.db, closing(self.db.cursor()) as c:
                    c.execute("DELETE FROM blacklist")
            except self.module.Error as e:
                logging.error("Failed to flush blacklist - %s", str(e))
                sys.exit(1)
        else:
            try:
                os.unlink(self.filename)
            except OSError as e:
                logging.error("Failed to delete blacklist file - %s", str(e))
                sys.exit(1)

        self.regex = None
        self.regex_set = set()
        self.ip_set = set()
        self.host_set = set()


if __name__ == "__main__":
    main()
