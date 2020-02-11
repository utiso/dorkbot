#!/usr/bin/env python3
if __package__:
    from ._version import __version__
else:
    from _version import __version__
import argparse
import configparser
from urllib.parse import urlparse
from contextlib import closing
import datetime
import hashlib
import importlib
import json
import os
import re
import sys
import io
import random
import logging
import socket

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
       or args.flush_fingerprints:

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
        if args.add_target: db.add_target(args.add_target)
        if args.delete_target: db.delete_target(args.delete_target)
        if args.list_targets:
            for target in db.get_targets(): print(target)
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

def initialize_logger(log_file, verbose):
    log = logging.getLogger()

    if verbose:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    log_formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    if log_file:
        log_filehandler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
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
        help="Delete unscannable targets (blacklist / fingerprinting)")

    targets = parser.add_argument_group('targets')
    targets.add_argument("-l", "--list-targets", action="store_true", \
        help="List targets in database")
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
    urls = indexer.run(options)

    targets = []
    for url in urls:
        if not blacklist.match(Target(url)): targets.append(url)

    db.connect()
    db.add_targets(targets)
    db.close()

def prune(db, blacklist, args, options):
    fingerprints = set()

    logging.info("Pruning database")
    db.connect()
    urls = db.get_targets()

    if "random" in options:
        random.shuffle(urls)

    for url in urls:
        target = Target(url)

        fingerprint = generate_fingerprint(target)
        if fingerprint in fingerprints or db.get_scanned(fingerprint):
            logging.debug("Skipping (matches fingerprint of previous scan): %s", target.url)
            db.delete_target(target.url)
            continue

        if blacklist.match(target):
            logging.debug("Skipping (matches blacklist pattern): %s", target.url)
            db.delete_target(target.url)
            continue

        fingerprints.add(fingerprint)

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
        if "random" in options: url = db.get_random_target()
        else: url = db.get_next_target()
        if not url: break

        target = Target(url)

        fingerprint = generate_fingerprint(target)
        if db.get_scanned(fingerprint):
            logging.debug("Skipping (matches fingerprint of previous scan): %s", target.url)
            db.delete_target(target.url)
            continue

        if blacklist.match(target):
            logging.debug("Skipping (matches blacklist pattern): %s", target.url)
            db.delete_target(target.url)
            continue

        logging.info("Scanning: %s", target.url)
        db.delete_target(target.url)
        db.add_fingerprint(fingerprint)
        db.close()
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
    params = []
    for param in url_parts.query.split("&"):
        split = param.split("=", 1)
        if len(split) == 2 and split[1]:
            params.append(split[0])
    fingerprint = "|".join((netloc, depth, ",".join(sorted(params))))
    return fingerprint

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
            options.update({key:value})

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

        self.module = importlib.import_module(module_name, package=None)

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
                c.execute("CREATE TABLE IF NOT EXISTS targets (url VARCHAR PRIMARY KEY)")
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
       
    def get_targets(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT url FROM targets")
                targets = [row[0] for row in c.fetchall()]
        except self.module.Error as e:
            logging.error("Failed to get targets - %s", str(e))
            sys.exit(1)

        return targets

    def get_next_target(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT url FROM targets LIMIT 1")
                row = c.fetchone()
        except self.module.Error as e:
            logging.error("Failed to get next target - %s", str(e))
            sys.exit(1)

        if row: return row[0]
        else: return None

    def get_random_target(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT url FROM targets ORDER BY RANDOM() LIMIT 1")
                row = c.fetchone()
        except self.module.Error as e:
            logging.error("Failed to get random target - %s", str(e))
            sys.exit(1)

        if row: return row[0]
        else: return None

    def add_target(self, url):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("%s INTO targets VALUES (%s) %s" % (self.insert, self.param, self.conflict), (url,))
        except self.module.Error as e:
            logging.error("Failed to add target - %s", str(e))
            sys.exit(1)

    def add_targets(self, urls):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.executemany("%s INTO targets VALUES (%s) %s" % (self.insert, self.param, self.conflict), [(url,) for url in urls])
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

    def get_scanned(self, fingerprint):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT fingerprint FROM fingerprints WHERE fingerprint = (%s)" % self.param, (fingerprint,))
                row = c.fetchone()
        except self.module.Error as e:
            logging.error("Failed to look up fingerprint - %s", str(e))
            sys.exit(1)

        if row: return row[0]
        else: return False

    def add_fingerprint(self, fingerprint):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("%s INTO fingerprints VALUES (%s)" % (self.insert, self.param), (fingerprint,))
        except self.module.Error as e:
            logging.error("Failed to add fingerprint - %s", str(e))
            sys.exit(1)

    def flush_fingerprints(self):
        logging.info("Flushing fingerprints")
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM fingerprints")
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

class Target:
    def __init__(self, url):
        self.url = url
        self.hash = ""
        self.starttime = generate_timestamp()

        url_parts = urlparse(url)
        self.host = url_parts.hostname
        self.ip = socket.gethostbyname(self.host)

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
        self.ip_list = []
        self.host_list = []
        self.regex_list = []

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
                self.ip_list.append(item.split(":")[1])
            elif item.startswith("host:"):
                self.host_list.append(item.split(":")[1])
            elif item.startswith("regex:"):
                self.regex_list.append(item.split(":")[1])
            else:
                logging.warning("Could not parse blacklist item - %s", item)

        pattern = "|".join(self.regex_list)
        if pattern:
            self.regex = re.compile(pattern)
        else:
            self.regex = None

    def get_parsed_items(self):
        return ["ip:" + item for item in self.ip_list] + \
               ["host:" + item for item in self.host_list] + \
               ["regex:" + item for item in self.regex_list]
       
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
            self.ip_list.append(item.split(":")[1])
        elif item.startswith("host:"):
            self.host_list.append(item.split(":")[1])
        elif item.startswith("regex:"):
            self.regex_list.append(item.split(":")[1])
        else:
            logging.warning("Could not parse blacklist item - %s", item)
            return

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
        elif target.host in self.host_list:
            return True
        elif target.ip in self.ip_list:
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
        self.ip_list = []
        self.host_list = []

if __name__ == "__main__":
    main()

