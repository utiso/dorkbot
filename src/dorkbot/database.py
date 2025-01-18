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
import sys
from contextlib import closing


class TargetDatabase:
    def __init__(self, database, drop_tables=False, create_tables=False):
        self.connect_kwargs = {}
        if database.startswith("postgresql://"):
            module_name = "psycopg2"
            self.database = database
            self.id_type = "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
            self.insert = "INSERT"
            self.conflict = "ON CONFLICT DO NOTHING"
        elif database.startswith("phoenixdb://"):
            module_name = "phoenixdb"
            self.database = database[12:]
            self.id_type = "INTEGER PRIMARY KEY"
            self.insert = "UPSERT"
            self.conflict = ""
            self.connect_kwargs["autocommit"] = True
        else:
            module_name = "sqlite3"
            self.database = os.path.expanduser(database)
            database_dir = os.path.dirname(self.database)
            self.id_type = "INTEGER PRIMARY KEY"
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

        if drop_tables:
            self.execute("DROP TABLE IF EXISTS targets")
            self.execute("DROP TABLE IF EXISTS sources")
            self.execute("DROP TABLE IF EXISTS fingerprints")
            self.execute("DROP TABLE IF EXISTS blocklist")

        if create_tables:
            self.execute("CREATE TABLE IF NOT EXISTS targets"
                         f" (id {self.id_type},"
                         " url VARCHAR UNIQUE,"
                         " source_id INTEGER,"
                         " fingerprint_id INTEGER,"
                         " scanned INTEGER DEFAULT 0)")
            self.execute("CREATE TABLE IF NOT EXISTS sources"
                         f" (id {self.id_type},"
                         " source VARCHAR UNIQUE)")
            self.execute("CREATE TABLE IF NOT EXISTS fingerprints"
                         f" (id {self.id_type},"
                         " fingerprint VARCHAR UNIQUE,"
                         " scanned INTEGER DEFAULT 0)")
            self.execute("CREATE TABLE IF NOT EXISTS blocklist"
                         f" (id {self.id_type},"
                         " item VARCHAR UNIQUE)")

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

    def execute(self, *sql, many=False, fetchone=False, fetchall=False, lastrowid=False, retries=3):
        if len(sql) == 2:
            statement, arguments = sql
            if not arguments:
                arguments = ""
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
                    elif lastrowid:
                        result = c.lastrowid
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

    def get_urls(self, unscanned_only=False, source=False, random=False):
        if source and source is not True:
            sql = "SELECT t.url FROM sources s" \
                  + " INNER JOIN targets t on t.source_id = s.id"
            if unscanned_only:
                sql += " LEFT JOIN fingerprints f on f.id = t.fingerprint_id" \
                    + " WHERE t.scanned = '0' AND (t.fingerprint_id IS NULL OR f.scanned = '0')" \
                    + " AND s.source = %s" % self.param
            else:
                sql += " WHERE s.source = %s" % self.param
            if random:
                sql += " ORDER BY RANDOM()"
            parameters = (source,)

        else:
            if source is True:
                sql = "SELECT t.url, s.source FROM targets t" \
                      + " LEFT JOIN sources s on s.id = t.source_id"
            else:
                sql = "SELECT t.url FROM targets t"
            if unscanned_only:
                sql += " LEFT JOIN fingerprints f on f.id = t.fingerprint_id" \
                    + " WHERE t.scanned = '0' AND (t.fingerprint_id IS NULL OR f.scanned = '0')"
            if random:
                sql += " ORDER BY RANDOM()"
            parameters = None

        rows = self.execute(sql, parameters, fetchall=True)
        urls = [" | ".join([str(column or "") for column in row]) for row in rows]
        return urls

    def get_next_target(self, source=False, random=False):
        sql = "SELECT t.url, t.id, f.id FROM targets t" \
            + " LEFT JOIN fingerprints f on f.id = t.fingerprint_id" \
            + " WHERE (t.fingerprint_id IS NULL AND t.scanned = '0') OR f.scanned = '0'"
        if source and source is not True:
            + " AND s.source = %s" % self.param
            parameters = (source,)
        else:
            parameters = None
        if random:
            sql += " ORDER BY RANDOM()"

        target = None
        while True:
            row = self.execute(sql, parameters, fetchone=True)
            if not row:
                break

            url = row[0]
            target_id = row[1]
            fingerprint_id = row[2]

            if not fingerprint_id:
                fingerprint = generate_fingerprint(url)
                fingerprint_id = self.get_fingerprint_id(fingerprint)
                if fingerprint_id:
                    self.update_target_fingerprint(target_id, fingerprint_id)
                    logging.debug("Skipping (matches scanned fingerprint): %s", url)
                    continue
                else:
                    self.mark_target_scanned(target_id)
                    self.add_fingerprint(fingerprint, scanned=True)
            else:
                self.mark_fingerprint_scanned(fingerprint_id)

            target = url
            break
        return target

    def add_target(self, url, source=None):
        if source:
            source_id = get_source_id(source)  # noqa:F821
            if not source_id:
                source_id = add_source(source, return_id=True)  # noqa:F821
        else:
            source_id = None

        target_id = self.execute("%s INTO targets (url, source_id) VALUES (%s, %s) %s"
                                 % (self.insert, self.param, self.param, self.conflict),
                                 (url, source_id), lastrowid=True)
        return target_id

    def add_targets(self, urls, source=None, chunk_size=1000):
        if source:
            source_id = get_source_id(source)  # noqa:F821
            if not source_id:
                source_id = add_source(source, return_id=True)  # noqa:F821
        else:
            source_id = None

        for x in range(0, len(urls), chunk_size):
            urls_chunk = urls[x:x + chunk_size]
            self.execute("%s INTO targets (url, source_id) VALUES (%s, %s) %s"
                         % (self.insert, self.param, self.param, self.conflict),
                         [(url, source) for url in urls_chunk], many=True)

    def mark_target_scanned(self, target_id):
        self.execute("UPDATE targets SET scanned = 1 WHERE id = %s" % self.param, (target_id,))

    def delete_target(self, url):
        self.execute("DELETE FROM targets WHERE url = %s" % self.param, (url,))

    def flush_targets(self):
        logging.info("Flushing targets")
        self.execute("DELETE FROM targets")
        self.execute("DELETE FROM sources")

    def add_source(self, source):
        source_id = self.execute("%s INTO sources (source) VALUES (%s) %s"
                                 % (self.insert, self.param, self.conflict),
                                 (source,), lastrowid=True)
        return source_id

    def add_fingerprint(self, fingerprint, scanned=False):
        fingerprint_id = self.execute("%s INTO fingerprints (fingerprint, scanned) VALUES (%s, %s) %s"
                                      % (self.insert, self.param, self.param, self.conflict),
                                      (fingerprint, 1 if scanned else 0), lastrowid=True)
        return fingerprint_id

    def update_target_fingerprint(self, target_id, fingerprint_id):
        self.execute("UPDATE targets SET fingerprint_id = %s WHERE id = %s"
                     % (self.param, self.param), (fingerprint_id, target_id))

    def flush_fingerprints(self):
        logging.info("Flushing fingerprints")
        self.execute("UPDATE targets SET fingerprint_id = NULL")
        self.execute("DELETE FROM fingerprints")

    def reset_scanned(self):
        logging.info("Resetting scanned")
        self.execute("UPDATE targets SET scanned = 0")
        self.execute("UPDATE fingerprints SET scanned = 0")

    def get_fingerprint_id(self, fingerprint):
        row = self.execute("SELECT id FROM fingerprints WHERE fingerprint = %s"
                           % self.param, (fingerprint,), fetchone=True)
        if row:
            return row[0]
        else:
            return False

    def mark_fingerprint_scanned(self, fingerprint_id):
        self.execute("UPDATE fingerprints SET scanned = 1 WHERE id = %s" % self.param, (fingerprint_id,))

    def prune(self, blocklists, random):
        self.generate_fingerprints()
        sql = "SELECT t.url, t.id, f.id FROM targets t" \
            + " LEFT JOIN fingerprints f on f.id = t.fingerprint_id" \
            + " WHERE t.scanned = '0' AND (t.fingerprint_id IS NULL OR f.scanned = '0')"
        if random:
            sql += " ORDER BY RANDOM()"

        fingerprints = set()
        rows = self.execute(sql, fetchall=True)
        for row in rows:
            url = row[0]
            target_id = row[1]
            fingerprint_id = row[2]

            if not fingerprint_id:
                fingerprint = generate_fingerprint(url)
                fingerprint_id = self.get_fingerprint_id(fingerprint)
                if fingerprint_id:
                    fingerprints.add(fingerprint_id)
                    self.mark_target_scanned(target_id)
                    self.update_target_fingerprint(target_id, fingerprint_id)
                    logging.debug("Skipping (matches scanned fingerprint): %s", url)
                    continue
                else:
                    fingerprint_id = self.add_fingerprint(fingerprint, scanned=False)
                    self.update_target_fingerprint(target_id, fingerprint_id)
            else:
                if fingerprint_id in fingerprints:
                    self.mark_target_scanned(target_id)
                else:
                    fingerprints.add(fingerprint_id)

            if True in [blocklist.match(Target(url)) for blocklist in blocklists]:
                logging.debug("Deleting (matches blocklist pattern): %s", url)
                self.delete_target(url)
                continue

    def generate_fingerprints(self):
        sql = "SELECT t.url, t.id FROM targets t WHERE t.fingerprint_id IS NULL"

        fingerprints = {}
        rows = self.execute(sql, fetchall=True)
        for row in rows:
            url = row[0]
            target_id = row[1]

            fingerprint = generate_fingerprint(url)

            if fingerprint in fingerprints:
                self.update_target_fingerprint(target_id, fingerprints[fingerprint])
                continue

            fingerprint_id = self.get_fingerprint_id(fingerprint)
            if fingerprint_id:
                fingerprints[fingerprint] = fingerprint_id
                self.update_target_fingerprint(target_id, fingerprint_id)
            else:
                fingerprint_id = self.add_fingerprint(fingerprint, scanned=False)
                fingerprints[fingerprint] = fingerprint_id
                self.update_target_fingerprint(target_id, fingerprint_id)
