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
            index(db, indexer_module, indexer_args)
        if args.scanner:
            scanner_module = load_module("scanners", args.scanner)
            scanner_args = parse_options(args.scanner_options)
            scan(db, scanner_module, scanner_args)
        db.close()

    else:
        parser.print_usage()

def load_module(category, name):
    module = "%s.%s" % (category, name)
    try:
        importlib.import_module(module)
    except ImportError:
        print("ERROR: module not found", file=sys.stderr)
        sys.exit(1)

    return sys.modules[module]

def get_args_parser():
    dorkbot_dir = os.path.dirname(os.path.abspath(__file__))
    default_options = {
        "config": os.path.join(dorkbot_dir, "config", "dorkbot.ini"),
        "database": os.path.join(dorkbot_dir, "databases", "dorkbot.db"),
    }

    initial_parser = argparse.ArgumentParser(
        description="dorkbot", add_help=False)
    initial_parser.add_argument("-c", "--config", \
        default=default_options["config"], \
        help="Configuration file")
    args, other_args = initial_parser.parse_known_args()

    if os.path.isfile(args.config):
        config = configparser.SafeConfigParser()
        config.read(args.config)
        options = config.items("dorkbot")
        default_options.update(dict(options))

    parser = argparse.ArgumentParser(parents=[initial_parser])
    parser.set_defaults(**default_options)
    parser.add_argument("-d", "--database", \
        help="SQLite3 database file")
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
    return args, parser

def index(db, indexer, args):
    results = indexer.run(args)

    for result in results:
        url = result.geturl().decode("utf-8")
        print(url)
        db.add_target(url)

def scan(db, scanner, args):
    dorkbot_dir = os.path.dirname(os.path.abspath(__file__))
    default_blacklist_file = os.path.join(dorkbot_dir, "config", "blacklist.txt")
    default_report_dir = os.path.join(dorkbot_dir, "reports")

    blacklist = get_blacklist(args.get("blacklist", default_blacklist_file))
    report_dir = args.get("report_dir", default_report_dir)
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
        if database.startswith("postgresql://"):
            module_name = "psycopg2"
        else:
            module_name = "sqlite3"
            database = os.path.expanduser(database)

        self.module = importlib.import_module(module_name, package=None)

        if self.module.paramstyle == "qmark":
            self.param = "?"
        else:
            self.param = "%s"

        try:
            self.db = self.module.connect(database)
        except self.module.Error as e:
            print("ERROR loading database - %s" % e, file=sys.stderr)
            sys.exit(1)

        try:
            c = self.db.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS targets (id INTEGER PRIMARY KEY, url TEXT UNIQUE)")
            c.execute("CREATE TABLE IF NOT EXISTS fingerprints (id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)")
            self.db.commit()
            c.close()
        except self.module.Error as e:
            print("ERROR loading database - %s" % e, file=sys.stderr)
            sys.exit(1)
       
    def get_targets(self):
        try:
            c = self.db.cursor()
            c.execute("SELECT url FROM targets")
            targets = [row[0] for row in c.fetchall()]
            c.close()
        except self.module.Error as e:
            print("ERROR getting targets - %s" % e, file=sys.stderr)
            sys.exit(1)

        return targets

    def get_next_target(self):
        try:
            c = self.db.cursor()
            c.execute("SELECT url FROM targets LIMIT 1")
            row = c.fetchone()
            c.close()
        except self.module.Error as e:
            print("ERROR getting next target - %s" % e, file=sys.stderr)
            sys.exit(1)

        if row: return row[0]
        else: return None

    def get_random_target(self):
        try:
            c = self.db.cursor()
            c.execute("SELECT url FROM targets ORDER BY RANDOM() LIMIT 1")
            row = c.fetchone()
            c.close()
        except self.module.Error as e:
            print("ERROR getting random target - %s" % e, file=sys.stderr)
            sys.exit(1)

        if row: return row[0]
        else: return None

    def add_target(self, url):
        try:
            c = self.db.cursor()
            c.execute("INSERT INTO targets (url) VALUES (%s)" % self.param, (url,))
            self.db.commit()
            c.close()
        except self.module.IntegrityError:
            pass
        except self.module.Error as e:
            print("ERROR adding target - %s" % e, file=sys.stderr)
            sys.exit(1)

    def delete_target(self, url):
        try:
            c = self.db.cursor()
            c.execute("DELETE FROM targets WHERE url=(%s)" % self.param, (url,))
            self.db.commit()
            c.close()
        except self.module.Error as e:
            print("ERROR deleting target - %s" % e, file=sys.stderr)
            sys.exit(1)

    def get_scanned(self, fingerprint):
        try:
            c = self.db.cursor()
            c.execute("SELECT scanned FROM fingerprints WHERE fingerprint = (%s)" % self.param, (fingerprint,))
            row = c.fetchone()
            c.close()
        except self.module.Error as e:
            print("ERROR looking up fingerprint - %s" % e, file=sys.stderr)
            sys.exit(1)

        if row: return row[0]
        else: return False

    def add_fingerprint(self, fingerprint):
        try:
            c = self.db.cursor()
            c.execute("INSERT INTO fingerprints (fingerprint) VALUES (%s)" % self.param, (fingerprint,))
            self.db.commit()
            c.close()
        except self.module.IntegrityError:
            pass
        except self.module.Error as e:
            print("ERROR adding fingerprint - %s" % e, file=sys.stderr)
            sys.exit(1)

    def flush_fingerprints(self):
        try:
            c = self.db.cursor()
            c.execute("DELETE FROM fingerprints")
            self.db.commit()
            c.close()
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

