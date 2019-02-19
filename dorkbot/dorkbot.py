#!/usr/bin/env python
from __future__ import print_function
import argparse
try:
    import ConfigParser as configparser
except ImportError:
    import configparser
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
from contextlib import closing
import datetime
import hashlib
import importlib
import json
import os
import re
import sys

def main():
    args, parser = get_args_parser()

    if args.flush or args.list or args.indexer or args.scanner:
        db = TargetDatabase(args.database)
        if args.flush: db.flush_fingerprints()
        if args.list:
            for target in db.get_targets(): print(target)
        if args.indexer:
            indexer_module = load_module("indexers", args.indexer)
            indexer_args = parse_options(args.indexer_options)
            indexer_args["dorkbot_dir"] = args.directory
            index(db, indexer_module, indexer_args)
        if args.scanner:
            scanner_module = load_module("scanners", args.scanner)
            scanner_args = parse_options(args.scanner_options)
            scanner_args["dorkbot_dir"] = args.directory
            scan(db, scanner_module, scanner_args)
        db.close()

    else:
        parser.print_usage()

def load_module(category, name):
    module_name = "%s.%s" % (category, name)
    if __package__: module_name = "." + module_name
    try:
        module = importlib.import_module(module_name, package=__package__)
    except ImportError:
        print("ERROR: module not found", file=sys.stderr)
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
    parser.add_argument("-o", "--indexer-options", \
        help="Indexer-specific options (opt1=val1,opt2=val2,..)")
    parser.add_argument("-p", "--scanner-options", \
        help="Scanner-specific options (opt1=val1,opt2=val2,..)")
    parser.add_argument("-s", "--scanner", \
        help="Scanner module to use")

    args = parser.parse_args(other_args)
    args.directory = initial_args.directory
    return args, parser

def index(db, indexer, args):
    for url in indexer.run(args):
        db.add_target(url)
        print(url)

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
            print("ERROR creating report directory - %s" % e, file=sys.stderr)
            sys.exit(1)

    count = int(args.get("count", "-1"))
    label = args.get("label", "")
    if "log" in args: log = open(os.path.abspath(args["log"]), "a", 1)
    else: log = sys.stdout

    scanned = 0
    while scanned < count or count == -1:
        if "random" in args: url = db.get_random_target()
        else: url = db.get_next_target()
        if not url: break

        target = Target(url)

        if db.get_scanned(target.fingerprint):
            print(target.starttime, "Skipping (matches fingerprint of previous scan): %s" % target.url, file=log)
            db.delete_target(target.url)
            continue

        if blacklist.match(target.url):
            print(target.starttime, "Skipping (matches blacklist pattern): %s" % target.url, file=log)
            db.delete_target(target.url)
            continue

        print(target.starttime, "Scanning: %s" % target.url, file=log)
        db.delete_target(target.url)
        db.add_fingerprint(target.fingerprint)
        results = scanner.run(args, target)
        scanned += 1

        if results == False:
            print(target.starttime, "ERROR scanning %s" % target.url, file=log)
            continue

        target.endtime = target.get_timestamp()
        target.write_report(report_dir, label, results)

    if "log" in args: log.close()

def get_blacklist(blacklist_file):
    pattern = "$^"
    try:
        if os.path.isfile(blacklist_file):
            with open(blacklist_file, "r") as f:
                pattern = "|".join(f.read().splitlines())
        blacklist = re.compile(pattern)
    except Exception as e:
        print("ERROR reading blacklist - %s" % e, file=sys.stderr)
        sys.exit(1)

    return blacklist

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
        kwargs = {}
        if database.startswith("postgresql://"):
            module_name = "psycopg2"
            self.insert = "INSERT"
        elif database.startswith("phoenixdb://"):
            module_name = "phoenixdb"
            database = database[12:]
            self.insert = "UPSERT"
            kwargs["autocommit"] = True
        else:
            module_name = "sqlite3"
            database = os.path.expanduser(database)
            database_dir = os.path.dirname(database)
            self.insert = "INSERT"
            if database_dir and not os.path.exists(database_dir):
                try:
                    os.makedirs(database_dir)
                except OSError as e:
                    print("ERROR creating directory - %s" % e, file=sys.stderr)
                    sys.exit(1)


        self.module = importlib.import_module(module_name, package=None)

        if self.module.paramstyle == "qmark":
            self.param = "?"
        else:
            self.param = "%s"

        try:
            self.db = self.module.connect(database, **kwargs)
        except self.module.Error as e:
            print("ERROR loading database - %s" % e, file=sys.stderr)
            sys.exit(1)

        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("CREATE TABLE IF NOT EXISTS targets (url VARCHAR PRIMARY KEY)")
                c.execute("CREATE TABLE IF NOT EXISTS fingerprints (fingerprint VARCHAR PRIMARY KEY)")
        except self.module.Error as e:
            print("ERROR loading database - %s" % e, file=sys.stderr)
            sys.exit(1)
       
    def get_targets(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT url FROM targets")
                targets = [row[0] for row in c.fetchall()]
        except self.module.Error as e:
            print("ERROR getting targets - %s" % e, file=sys.stderr)
            sys.exit(1)

        return targets

    def get_next_target(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT url FROM targets LIMIT 1")
                row = c.fetchone()
        except self.module.Error as e:
            print("ERROR getting next target - %s" % e, file=sys.stderr)
            sys.exit(1)

        if row: return row[0]
        else: return None

    def get_random_target(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT url FROM targets ORDER BY RANDOM() LIMIT 1")
                row = c.fetchone()
        except self.module.Error as e:
            print("ERROR getting random target - %s" % e, file=sys.stderr)
            sys.exit(1)

        if row: return row[0]
        else: return None

    def add_target(self, url):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("%s INTO targets VALUES (%s)" % (self.insert, self.param), (url,))
        except self.module.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                return
            pass
        except self.module.Error as e:
            print("ERROR adding target - %s" % e, file=sys.stderr)
            sys.exit(1)

    def delete_target(self, url):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM targets WHERE url=(%s)" % self.param, (url,))
        except self.module.Error as e:
            print("ERROR deleting target - %s" % e, file=sys.stderr)
            sys.exit(1)

    def get_scanned(self, fingerprint):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("SELECT fingerprint FROM fingerprints WHERE fingerprint = (%s)" % self.param, (fingerprint,))
                row = c.fetchone()
        except self.module.Error as e:
            print("ERROR looking up fingerprint - %s" % e, file=sys.stderr)
            sys.exit(1)

        if row: return row[0]
        else: return False

    def add_fingerprint(self, fingerprint):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("%s INTO fingerprints VALUES (%s)" % (self.insert, self.param), (fingerprint,))
        except self.module.Error as e:
            print("ERROR adding fingerprint - %s" % e, file=sys.stderr)
            sys.exit(1)

    def flush_fingerprints(self):
        try:
            with self.db, closing(self.db.cursor()) as c:
                c.execute("DELETE FROM fingerprints")
        except self.module.Error as e:
            print("ERROR flushing fingerprints - %s" % e, file=sys.stderr)
            sys.exit(1)

    def close(self):
        self.db.close()

class Target:
    def __init__(self, url):
        self.url = url
        self.hash = self.generate_hash()
        self.fingerprint = self.generate_fingerprint()
        self.starttime = self.get_timestamp()

    def generate_hash(self):
        return hashlib.md5(self.url.encode("utf-8")).hexdigest()

    def generate_fingerprint(self):
        url_parts = urlparse(self.url)
        netloc = url_parts.netloc
        depth = str(url_parts.path.count("/"))
        params = []
        for param in url_parts.query.split("&"):
            split = param.split("=", 1)
            if len(split) == 2 and split[1]:
                params.append(split[0])
        fingerprint = "|".join((netloc, depth, ",".join(sorted(params))))
        return fingerprint

    def get_timestamp(self):
        return datetime.datetime.now(UTC()).isoformat()

    def write_report(self, report_dir, label, vulnerabilities):
        vulns = {}
        vulns["vulnerabilities"] = vulnerabilities
        vulns["starttime"] = str(self.starttime)
        vulns["endtime"] = str(self.endtime)
        vulns["url"] = self.url
        vulns["label"] = label

        filename = os.path.join(report_dir, self.hash + ".json")

        with open(filename, "w") as outfile:
            json.dump(vulns, outfile, indent=4, sort_keys=True)
            print("Report saved to: %s" % outfile.name)

class UTC(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return datetime.timedelta(0)

if __name__ == "__main__":
    main()

