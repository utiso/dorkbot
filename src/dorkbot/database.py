#!/usr/bin/env python3
if __package__:
    from dorkbot.target import Target
    from dorkbot.util import generate_fingerprint
else:
    from target import Target
    from util import generate_fingerprint
import importlib
import logging
import os
import random
import sys
from contextlib import closing


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
                if i < retries - 1 and any(error in str(e) for error in retry_conditions):
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
                if i < retries - 1 and any(error in str(e) for error in retry_conditions):
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
        self.execute("%s INTO targets (url, source) VALUES (%s, %s) %s"
                     % (self.insert, self.param, self.param, self.conflict), (url, source))

    def add_targets(self, urls, source=None, chunk_size=1000):
        for x in range(0, len(urls), chunk_size):
            urls_chunk = urls[x:x + chunk_size]
            self.execute("%s INTO targets (url, source) VALUES (%s, %s) %s"
                         % (self.insert, self.param, self.param, self.conflict),
                         [(url, source) for url in urls_chunk], many=True)

    def delete_target(self, url):
        self.execute("DELETE FROM targets WHERE url=(%s)" % self.param, (url,))

    def get_scanned(self, fingerprint):
        row = self.execute("SELECT fingerprint FROM fingerprints WHERE fingerprint = (%s)"
                           % self.param, (fingerprint,), fetchone=True)
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
