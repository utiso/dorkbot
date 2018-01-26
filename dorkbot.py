#!/usr/bin/env python
from __future__ import print_function
import argparse
try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import datetime
from dateutil import tz
import hashlib
import importlib
import json
import os
import pkgutil
import re
import sqlite3
import sys

def main():
    dorkbot_dir = os.path.dirname(os.path.abspath(__file__))
    default_options = {
        "config": os.path.join(dorkbot_dir, "config", "dorkbot.ini"),
        "blacklist": os.path.join(dorkbot_dir, "config", "blacklist.txt"),
        "database": os.path.join(dorkbot_dir, "databases", "dorkbot.db"),
        "vulndir": os.path.join(dorkbot_dir, "vulnerabilities")
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
    parser.add_argument("-v", "--vulndir", \
        help="Directory to store vulnerability output reports")

    args = parser.parse_args(other_args)

    if args.list or args.indexer or args.scanner:
        db = load_database(args.database)

        if args.list:
            list(db)

        if args.indexer:
            index(db, args.indexer, args.indexer_options)

        if args.scanner:
            scan(db, args.scanner, args.scanner_options, args.vulndir, args.blacklist)

        db.close()
    else:
        parser.print_usage()

def load_database(database_file):
    try:
        db = sqlite3.connect(os.path.expanduser(database_file))
        return db
    except sqlite3.OperationalError as e:
        print("ERROR loading database - %s" % e, file=sys.stderr)
        sys.exit(1)

def get_targets(db):
    try:
        c = db.cursor()
        c.execute("SELECT url, query FROM targets")
        rows = c.fetchall()
        targets = []
        for row in rows:
            targets.append(row[0] + "?" + row[1])
        c.close()
        return targets
    except sqlite3.OperationalError as e:
        if "no such table: targets" in str(e):
            sys.exit(0)
        else:
            print("ERROR fetching targets - %s" % e, file=sys.stderr)
            sys.exit(1)

def get_blacklist(blacklist_file):
    pattern = "$^"
    if os.path.isfile(blacklist_file):
        with open(blacklist_file, 'r') as f:
            pattern = '|'.join(f.read().splitlines())

    return re.compile(pattern)

def list(db):
    for target in get_targets(db):
        print(target)

def index(db, indexer, indexer_options):
    for _, module, _ in pkgutil.iter_modules(["indexers"]):
        importlib.import_module("indexers.%s" % module)

    try:
        indexer_module = sys.modules["indexers.%s" % indexer]
    except KeyError:
        print("ERROR: indexer module not found", file=sys.stderr)
        sys.exit(1)

    options = dict()
    if indexer_options:
        options = dict(option.split("=") for option in indexer_options.split(","))

    results = indexer_module.run(options)

    c = db.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS targets (id INTEGER PRIMARY KEY, url TEXT UNIQUE, query TEXT)")
    for result in results:
        url = result.geturl().decode('utf8')
        print(url)
        url_parts = url.split('?', 1)
        if len(url_parts) == 1:
            url_parts.append("")
        try:
            c.execute("INSERT INTO targets (url, query) VALUES (?, ?)", url_parts)
        except sqlite3.IntegrityError:
            continue
    db.commit()
    c.close()

def scan(db, scanner, scanner_options, vulndir, blacklist_file):
    for _, module, _ in pkgutil.iter_modules(["scanners"]):
        importlib.import_module("scanners.%s" % module)

    try:
        scanner_module = sys.modules["scanners.%s" % scanner]
    except KeyError:
        print("ERROR: scanner module not found", file=sys.stderr)
        sys.exit(1)

    options = dict()
    if scanner_options:
        options = dict(option.split("=") for option in scanner_options.split(","))

    for url in get_targets(db):
        blacklist = get_blacklist(blacklist_file)
        if blacklist.match(url):
            print("Skipping (blacklisted): %s" % url)
        else:
            results = scanner_module.run(options, url)
            if results:
                vulns = {}
                vulns['vulnerabilities'] = results
                vulns['date'] = str(datetime.datetime.now(tz=tz.tzlocal()).replace(microsecond=0))
                vulns['url'] = url
                url_md5 = hashlib.md5(url.encode("utf-8")).hexdigest()
                with open(os.path.join(vulndir, url_md5 + "-" + scanner + ".json"), 'w') as outfile:
                    json.dump(vulns, outfile, indent=4, sort_keys=True)
                    print("Vulnerabilities found. Report saved to: %s" % outfile.name)

if __name__ == "__main__":
    main()

