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
import pkgutil
import re
import sqlite3
import sys

def main():
    args, parser = get_args_parser()

    if args.flush or args.list or args.indexer or args.scanner:
        db = load_database(args.database)
        if args.flush:
            flush_fingerprints(db)
        if args.list:
            list_targets(db)
        if args.indexer:
            for _, module, _ in pkgutil.iter_modules(["indexers"]):
                importlib.import_module("indexers.%s" % module)
            index(db, args.indexer, parse_options(args.indexer_options))
        if args.scanner:
            for _, module, _ in pkgutil.iter_modules(["scanners"]):
                importlib.import_module("scanners.%s" % module)
            scan(db, args.scanner, parse_options(args.scanner_options), args.vulndir, get_blacklist(args.blacklist), int(args.target_count))
        db.close()

    else:
        parser.print_usage()

def get_args_parser():
    dorkbot_dir = os.path.dirname(os.path.abspath(__file__))
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
    parser.add_argument("-l", "--list", action="store_true", \
        help="List targets in database")
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

def list_targets(db):
    try:
        c = db.cursor()
        c.execute("SELECT url FROM targets")
        rows = c.fetchall()
        for row in rows:
            print(row[0])
        c.close()
    except sqlite3.OperationalError as e:
        if "no such table: targets" in str(e):
            sys.exit(0)
        else:
            print("ERROR fetching targets - %s" % e, file=sys.stderr)
            sys.exit(1)

def index(db, indexer, options):
    try:
        indexer_module = sys.modules["indexers.%s" % indexer]
    except KeyError:
        print("ERROR: indexer module not found", file=sys.stderr)
        sys.exit(1)

    results = indexer_module.run(options)

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

def scan(db, scanner, options, vulndir, blacklist, count):
    try:
        scanner_module = sys.modules["scanners.%s" % scanner]
    except KeyError:
        print("ERROR: scanner module not found", file=sys.stderr)
        sys.exit(1)

    deletable = []
    scanned = 0
    c = db.cursor()
    c.execute("SELECT id,url FROM targets")
    while True:
        row = c.fetchone()
        if not row or (count >= 0 and scanned >= count):
            break
        id_ = int(row[0])
        url = row[1]
        fingerprint = get_fingerprint(url)
        if last_scanned(db, fingerprint):
            print("Skipping (matches fingerprint of previous scan): %s" % url)
            deletable.append(id_)
            continue
        if blacklist.match(url):
            print("Skipping (blacklisted): %s" % url)
            deletable.append(id_)
            continue

        results = scanner_module.run(options, url)
        deletable.append(id_)
        if results == False:
            continue
        if results:
            url_md5 = hashlib.md5(url.encode("utf-8")).hexdigest()
            filename = os.path.join(vulndir, url_md5 + "-" + scanner + ".json")
            create_vuln_report(filename, url, results)
        log_scan(db, fingerprint)
        scanned += 1
    for target in deletable:
        c.execute("DELETE FROM targets where id=(?)", (target,))
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
        options = dict(option.split("=") for option in options_string.split(","))

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

def create_vuln_report(filename, url, results):
    vulns = {}
    vulns["vulnerabilities"] = results
    vulns["date"] = str(datetime.datetime.now(UTC()).replace(microsecond=0))
    vulns["url"] = url
    with open(filename, "w") as outfile:
        json.dump(vulns, outfile, indent=4, sort_keys=True)
        print("Vulnerabilities found. Report saved to: %s" % outfile.name)

def log_scan(db, fingerprint):
    c = db.cursor()
    try:
        c.execute("INSERT INTO fingerprints (fingerprint) VALUES (?)", (fingerprint,))
    except sqlite3.IntegrityError:
        pass
    ##db.commit()
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

