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

def main():
    args, parser = get_args_parser()

    initialize_logger(args.logfile)

    if args.flush or args.list or args.indexer or args.prune or args.scanner:
        db = TargetDatabase(args.database)
        if args.flush: db.flush_fingerprints()
        if args.list:
            for target in db.get_targets(): print(target)
        db.close()

        if args.indexer:
            indexer_module = load_module("indexers", args.indexer)
            indexer_args = parse_options(args.indexer_options)
            indexer_args["dorkbot_dir"] = args.directory
            index(db, indexer_module, indexer_args)
        if args.prune:
            prune_args = parse_options(args.scanner_options)
            prune_args["dorkbot_dir"] = args.directory
            prune(db, prune_args)
        if args.scanner:
            scanner_module = load_module("scanners", args.scanner)
            scanner_args = parse_options(args.scanner_options)
            scanner_args["dorkbot_dir"] = args.directory
            scan(db, scanner_module, scanner_args)

    else:
        parser.print_usage()

def initialize_logger(logfile):
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

    log_formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    if logfile:
        log_filehandler = logging.FileHandler(logfile, mode="a", encoding="utf-8")
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
    default_dorkbot_dir = os.path.join(config_dir, "dorkbot")

    initial_parser = argparse.ArgumentParser(
        description="dorkbot", add_help=False)
    initial_parser.add_argument("-c", "--config", \
        help="Configuration file")
    initial_parser.add_argument("-r", "--directory", \
        default=default_dorkbot_dir, \
        help="Dorkbot directory (default location of config, db, tools, reports)")
    initial_args, other_args = initial_parser.parse_known_args()

    defaults = {
        "database": os.path.join(initial_args.directory, "dorkbot.db"),
        "config": os.path.join(initial_args.directory, "dorkbot.ini"),
    }

    if initial_args.config:
        config_file = initial_args.config
    else:
        config_file = defaults["config"]

    if os.path.isfile(config_file):
        config = configparser.SafeConfigParser()
        config.read(config_file)
        options = config.items("dorkbot")
        defaults.update(dict(options))

    parser = argparse.ArgumentParser(parents=[initial_parser])
    parser.set_defaults(**defaults)
    parser.add_argument("-d", "--database", \
        help="Database file/uri")
    parser.add_argument("-f", "--flush", action="store_true", \
        help="Flush table of fingerprints of previously-scanned items")
    parser.add_argument("-i", "--indexer", \
        help="Indexer module to use")
    parser.add_argument("-l", "--list", action="store_true", \
        help="List targets in database")
    parser.add_argument("--logfile", \
        help="Log file")
    parser.add_argument("-o", "--indexer-options", \
        help="Indexer-specific options (opt1=val1,opt2=val2,..)")
    parser.add_argument("-p", "--scanner-options", \
        help="Scanner-specific options (opt1=val1,opt2=val2,..)")
    parser.add_argument("-s", "--scanner", \
        help="Scanner module to use")
    parser.add_argument("-u", "--prune", action="store_true", \
        help="Delete unscannable targets (blacklist / fingerprinting)")
    parser.add_argument("-V", "--version", action="version", \
        version="%(prog)s " + __version__, help="Print version")

    args = parser.parse_args(other_args)
    args.directory = initial_args.directory
    return args, parser

def index(db, indexer, args):
    urls = indexer.run(args)
    db.connect()
    db.add_targets(urls)
    db.close()
    for url in urls:
        print(url)

def prune(db, args):
    defaults = {
        "blacklist": os.path.join(args["dorkbot_dir"], "blacklist.txt")
    }

    blacklist = get_blacklist(args.get("blacklist", defaults["blacklist"]))
    fingerprints = set()

    db.connect()
    urls = db.get_targets()

    if "random" in args:
        random.shuffle(urls)

    for url in urls:
        target = Target(url)

        fingerprint = generate_fingerprint(url)
        if fingerprint in fingerprints or db.get_scanned(fingerprint):
            logging.info("Skipping (matches fingerprint of previous scan): %s", target.url)
            db.delete_target(target.url)
            continue

        if blacklist.match(target.url):
            logging.info("Skipping (matches blacklist pattern): %s", target.url)
            db.delete_target(target.url)
            continue

        fingerprints.add(fingerprint)

    db.close()

def scan(db, scanner, args):
    defaults = {
        "blacklist": os.path.join(args["dorkbot_dir"], "blacklist.txt"),
        "reports": os.path.join(args["dorkbot_dir"], "reports")
    }

    blacklist = get_blacklist(args.get("blacklist", defaults["blacklist"]))

    report_dir = args.get("report_dir", defaults["reports"])
    if not os.path.exists(report_dir):
        try:
            os.makedirs(report_dir)
        except OSError as e:
            logging.error("Failed to create report directory - %s", str(e))
            sys.exit(1)

    count = int(args.get("count", "-1"))
    label = args.get("label", "")

    scanned = 0
    while scanned < count or count == -1:
        db.connect()
        if "random" in args: url = db.get_random_target()
        else: url = db.get_next_target()
        if not url: break

        target = Target(url)

        fingerprint = generate_fingerprint(url)
        if db.get_scanned(fingerprint):
            logging.info("Skipping (matches fingerprint of previous scan): %s", target.url)
            db.delete_target(target.url)
            continue

        if blacklist.match(target.url):
            logging.info("Skipping (matches blacklist pattern): %s", target.url)
            db.delete_target(target.url)
            continue

        logging.info("Scanning: %s", target.url)
        db.delete_target(target.url)
        db.add_fingerprint(fingerprint)
        db.close()
        results = scanner.run(args, target)
        scanned += 1

        if results == False:
            logging.error("Scan failed: %s", target.url)
            continue

        target.endtime = generate_timestamp()
        target.write_report(report_dir, label, results)

def get_blacklist(blacklist_file):
    pattern = "$^"
    try:
        if os.path.isfile(blacklist_file):
            with open(blacklist_file, "r") as f:
                pattern = "|".join(f.read().splitlines())
        blacklist = re.compile(pattern)
    except Exception as e:
        logging.error("Failed to read blacklist - %s", str(e))
        sys.exit(1)

    return blacklist

def generate_fingerprint(url):
    url_parts = urlparse(url)
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

def parse_options(options_string):
    options = dict()

    if options_string:
        for option in options_string.split(","):
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
            if database_dir and not os.path.exists(database_dir):
                try:
                    os.makedirs(database_dir)
                except OSError as e:
                    logging.error("Failed to create directory - %s", str(e))
                    sys.exit(1)


        self.module = importlib.import_module(module_name, package=None)

        if self.module.paramstyle == "qmark":
            self.param = "?"
        else:
            self.param = "%s"

        self.connect()
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("CREATE TABLE IF NOT EXISTS targets (url VARCHAR PRIMARY KEY)")
                c.execute("CREATE TABLE IF NOT EXISTS fingerprints (fingerprint VARCHAR PRIMARY KEY)")
        except self.module.Error as e:
            logging.error("Failed to load database - %s", str(e))
            sys.exit(1)

    def connect(self):
        try:
            self.db = self.module.connect(self.database, **self.connect_kwargs)
        except self.module.Error as e:
            loging.error("Error loading database - %s", str(e))
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
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM fingerprints")
        except self.module.Error as e:
            logging.error("Failed to flush fingerprints - %s", str(e))
            sys.exit(1)

class Target:
    def __init__(self, url):
        self.url = url
        self.hash = ""
        self.starttime = generate_timestamp()

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

if __name__ == "__main__":
    main()

