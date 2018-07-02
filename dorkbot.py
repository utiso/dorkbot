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
import sqlite3
import sys

def main():
    dorkbot_dir = os.path.dirname(os.path.abspath(__file__))
    args, parser = get_args_parser(dorkbot_dir)

    if args.log:
        log = open(os.path.abspath(args.log), "a")
    else:
        log = sys.stderr

    if args.flush or args.list or args.indexer or args.scanner:
        db = load_database(args.database)
        if args.flush:
            flush_fingerprints(db)
        if args.list:
            for target in get_targets(db):
                print(target)
        if args.indexer:
            index(db, args.indexer, parse_options(args.indexer_options))
        if args.scanner:
            scan(db, args.scanner, parse_options(args.scanner_options), args.vulndir, get_blacklist(args.blacklist), int(args.target_count), args.label, log)
        db.close()

    else:
        parser.print_usage()

    if args.log:
        log.close()

def load_module(category, name):
    module = "%s.%s" % (category, name)
    try:
        importlib.import_module(module)
    except ImportError:
        print("ERROR: module not found", file=sys.stderr)
        sys.exit(1)

    return sys.modules[module]

def get_args_parser(dorkbot_dir):
    default_options = {
        "config": os.path.join(dorkbot_dir, "config", "dorkbot.ini"),
        "blacklist": os.path.join(dorkbot_dir, "config", "blacklist.txt"),
        "database": os.path.join(dorkbot_dir, "databases", "dorkbot.db"),
        "vulndir": os.path.join(dorkbot_dir, "vulnerabilities"),
        "count": "-1"
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
    parser.add_argument("-b", "--blacklist", \
        help="File containing (regex) patterns to blacklist from scans")
    parser.add_argument("-d", "--database", \
        help="SQLite3 database file")
    parser.add_argument("-f", "--flush", action="store_true", \
        help="Flush table of fingerprints of previously-scanned items")
    parser.add_argument("-i", "--indexer", \
        help="Indexer module to use")
    parser.add_argument("--label", \
        help="Label to add to vulnerability report")
    parser.add_argument("-l", "--list", action="store_true", \
        help="List targets in database")
    parser.add_argument("--log", \
        help="Log file to append scan activity")
    parser.add_argument("-n", "--target-count", \
        default=default_options["count"], \
        help="Number of targets to scan")
    parser.add_argument("-o", "--indexer-options", \
        help="Indexer-specific options (opt1=val1,opt2=val2,..)")
    parser.add_argument("-p", "--scanner-options", \
        help="Scanner-specific options (opt1=val1,opt2=val2,..)")
    parser.add_argument("-s", "--scanner", \
        help="Scanner module to use")
    parser.add_argument("-v", "--vulndir", \
        help="Directory to store vulnerability output reports")

    args = parser.parse_args(other_args)
    return args, parser

def load_database(database_file):
    try:
        db = sqlite3.connect(os.path.expanduser(database_file))
        c = db.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS targets (id INTEGER PRIMARY KEY, url TEXT UNIQUE)")
        c.execute("CREATE TABLE IF NOT EXISTS fingerprints (id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)")
        c.close()
        return db
    except sqlite3.OperationalError as e:
        print("ERROR loading database - %s" % e, file=sys.stderr)
        sys.exit(1)

def flush_fingerprints(db):
    c = db.cursor()
    c.execute("DELETE FROM fingerprints")
    c.close()
    db.commit()

def get_targets(db):
    try:
        c = db.cursor()
        c.execute("SELECT url FROM targets")
        targets = [row[0] for row in c.fetchall()]
        c.close()
        return targets
    except sqlite3.OperationalError as e:
        if "no such table: targets" in str(e):
            sys.exit(0)
        else:
            print("ERROR fetching targets - %s" % e, file=sys.stderr)
            sys.exit(1)

def index(db, indexer, options):
    module = load_module("indexers", indexer)

    results = module.run(options)

    c = db.cursor()
    for result in results:
        url = result.geturl().decode("utf-8")
        print(url)
        try:
            c.execute("INSERT INTO targets (url) VALUES (?)", (url,))
        except sqlite3.IntegrityError:
            continue
    db.commit()
    c.close()

def scan(db, scanner, options, vulndir, blacklist, count, label, log):
    module = load_module("scanners", scanner)

    scanned = 0
    for url in get_targets(db):
        if count >= 0 and scanned >= count:
            break
        fingerprint = get_fingerprint(url)
        if last_scanned(db, fingerprint):
            print("Skipping (matches fingerprint of previous scan): %s" % url, file=log)
            delete_target(db, url)
            continue
        if blacklist.match(url):
            print("Skipping (blacklisted): %s" % url, file=log)
            delete_target(db, url)
            continue

        print("Scanning: %s" % url, file=log)
        if "simulate" in options:
            continue
        results = module.run(options, url)
        delete_target(db, url)
        if results:
            url_md5 = hashlib.md5(url.encode("utf-8")).hexdigest()
            filename = os.path.join(vulndir, url_md5 + ".json")
            create_vuln_report(filename, url, results, label)
        log_scan(db, fingerprint)
        scanned += 1

def delete_target(db, url):
    c = db.cursor()
    c.execute("DELETE FROM targets WHERE url=(?)", (url,))
    c.close()
    db.commit()

def get_blacklist(blacklist_file):
    pattern = "$^"
    if os.path.isfile(blacklist_file):
        with open(blacklist_file, "r") as f:
            pattern = "|".join(f.read().splitlines())

    return re.compile(pattern)

def get_fingerprint(url):
    url_parts = urlparse(url)
    netloc = url_parts.netloc
    depth = str(url_parts.path.count("/"))
    params = sorted([param.split("=")[0] for param in url_parts.query.split("&")])

    fingerprint = "|".join((netloc, depth, ",".join(params)))

    return fingerprint

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

def last_scanned(db, fingerprint):
    c = db.cursor()
    c.execute("SELECT scanned FROM fingerprints WHERE fingerprint = (?)", (fingerprint,))
    row = c.fetchone()
    c.close()

    if row:
        return row[0]
    else:
        return False

def create_vuln_report(filename, url, results, label):
    vulns = {}
    vulns["vulnerabilities"] = results
    vulns["date"] = str(datetime.datetime.now(UTC()).replace(microsecond=0))
    vulns["url"] = url
    if label:
        vulns["label"] = label
    else:
        vulns["label"] = ""
    with open(filename, "w") as outfile:
        json.dump(vulns, outfile, indent=4, sort_keys=True)
        print("Vulnerabilities found. Report saved to: %s" % outfile.name)

def log_scan(db, fingerprint):
    c = db.cursor()
    try:
        c.execute("INSERT INTO fingerprints (fingerprint) VALUES (?)", (fingerprint,))
    except sqlite3.IntegrityError:
        pass
    db.commit()
    c.close()

class UTC(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return datetime.timedelta(0)

if __name__ == "__main__":
    main()

