#!/usr/bin/env python3
if __package__:
    from dorkbot.target import Target
    from dorkbot.util import generate_fingerprint, get_database_attributes, get_parsed_url
else:
    from target import Target
    from util import generate_fingerprint, get_database_attributes, get_parsed_url
import logging
import os
import time
from contextlib import closing


class TargetDatabase:
    def __init__(self, address, drop_tables=False, create_tables=False):
        protocols = ["postgresql://", "sqlite3://"]
        if not any(address.startswith(protocol) for protocol in protocols):
            address = f"sqlite3://{address}"
        for key, value in get_database_attributes(address).items():
            setattr(self, key, value)

        if address.startswith("sqlite3://"):
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.database)), exist_ok=True)
            except OSError as e:
                logging.error(f"Failed to create parent directory for database file - {str(e)}")
                raise

        self.connect()

        if drop_tables:
            logging.debug("Dropping tables")
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

    def connect(self):
        for i in range(self.retries + 1):
            try:
                self.db = self.module.connect(self.database, **self.connect_kwargs)
                break
            except self.module.Error as e:
                retry_conditions = ["Connection timed out", "unexpectedly", "Temporary"]
                if i < self.retries and any(error in str(e) for error in retry_conditions):
                    logging.warning(f"Database connection failed (attempt {i + 1} of {self.retries}) - {str(e)}")
                    time.sleep(2**i)
                    continue
                else:
                    logging.error(f"Database connection failed - {str(e)}")
                    raise

    def close(self):
        self.db.close()

    def execute(self, *sql, fetch=False):
        statement, parameters = (sql[0], sql[1] if len(sql) == 2 else ())

        for i in range(self.retries + 1):
            try:
                with closing(self.db.cursor()) as c:
                    result = None
                    if isinstance(parameters, list):
                        c.executemany(statement, parameters)
                    else:
                        c.execute(statement, parameters)
                    if fetch is True:
                        result = c.fetchall()
                    elif fetch == 1:
                        result = c.fetchone()
                    elif fetch > 1:
                        result = c.fetchmany(fetch)
                self.db.commit()
                return result
            except self.module.Error as e:
                retry_conditions = ["connection", "SSL", "query_wait_timeout"]
                if i < self.retries and any(error in str(e) for error in retry_conditions):
                    logging.warning(f"Database execution failed (attempt {i + 1} of {self.retries}) - {str(e)}")
                    self.close()
                    time.sleep(2**i)
                    self.connect()
                    continue
                else:
                    logging.error(f"Database execution failed - {str(e)}")
                    raise

    def get_urls(self, unscanned_only=False, source=False, random=False, count=False):
        if source and source is not True:
            sql = "SELECT t.url FROM targets t" \
                  + " INNER JOIN sources s on s.id = t.source_id"
        elif source is True:
            sql = "SELECT t.url, s.source FROM targets t" \
                  + " LEFT JOIN sources s on s.id = t.source_id"
        else:
            sql = "SELECT t.url FROM targets t"

        if unscanned_only:
            sql += " LEFT JOIN fingerprints f on f.id = t.fingerprint_id" \
                + " WHERE t.scanned = '0' AND (t.fingerprint_id IS NULL OR f.scanned = '0')"

        if source and source is not True:
            if unscanned_only:
                sql += " AND s.source = %s" % self.param
            else:
                sql += " WHERE s.source = %s" % self.param
            parameters = (source,)
        else:
            parameters = ()

        if random:
            sql += " ORDER BY RANDOM()"
        else:
            sql += " ORDER BY t.id ASC"

        if count > 0:
            sql += f" LIMIT {count}"

        rows = self.execute(sql, parameters, fetch=True)
        urls = [" | ".join([str(column or "") for column in row]) for row in rows]
        return urls

    def get_unscanned_query(self, source=False, random=False):
        sql = "SELECT t.url, t.id, f.id, f.fingerprint FROM targets t"
        if source and source is not True:
            sql += " INNER JOIN sources s on s.id = t.source_id"
        sql += " LEFT JOIN fingerprints f on f.id = t.fingerprint_id" \
            + " WHERE t.scanned = '0' AND (t.fingerprint_id IS NULL OR f.scanned = '0')"
        if source and source is not True:
            sql += " AND s.source = %s" % self.param
            parameters = (source,)
        else:
            parameters = ()
        if random:
            sql += " ORDER BY RANDOM()"
        else:
            sql += " ORDER BY t.id ASC"
        return sql, parameters

    def get_next_target(self, blocklists=[], source=False, random=False, test=False):
        sql, parameters = self.get_unscanned_query(source=source, random=random)
        target = None
        fingerprints = {}
        while True:
            row = self.execute(sql, parameters, fetch=1)
            if not row:
                break
            url, target_id, fingerprint_id, fingerprint = row

            if True in [blocklist.match(Target(url)) for blocklist in blocklists]:
                logging.debug(f"Deleting (matches blocklist pattern): {url}")
                self.delete_target(url)

            elif fingerprint_id:
                logging.debug(f"Found unique fingerprint: {url}")
                if not test:
                    self.mark_fingerprint_scanned(fingerprint_id)
                target = url

            else:
                logging.debug(f"Computing fingerprint: {url}")
                fingerprint = generate_fingerprint(url)

                if fingerprint in fingerprints:
                    logging.debug(f"Skipping (matches existing fingerprint): {url}")
                    fingerprint_id = fingerprints[fingerprint]
                else:
                    fingerprint_id = self.get_fingerprint_id(fingerprint)
                    if fingerprint_id:
                        logging.debug(f"Skipping (matches scanned fingerprint): {url}")
                        fingerprints[fingerprint] = fingerprint_id
                    else:
                        logging.debug(f"Found unique fingerprint: {url}")
                        fingerprint_id = self.add_fingerprint(fingerprint, scanned=(not test))
                        target = url
                self.update_target_fingerprint(target_id, fingerprint_id)

            if target:
                break
        return target

    def add_target(self, url, source=None, blocklists=[]):
        if True in [blocklist.match(Target(url)) for blocklist in blocklists]:
            logging.debug(f"Ignoring (matches blocklist pattern): {url}")
            return

        logging.debug(f"Adding target {url}")
        if source:
            source_id = self.get_source_id(source)
            if not source_id:
                source_id = self.add_source(source)
        else:
            source_id = None

        self.execute("%s INTO targets (url, source_id) VALUES (%s, %s) %s"
                     % (self.insert, self.param, self.param, self.conflict),
                     (get_parsed_url(url), source_id))

    def add_targets(self, urls, source=None, blocklists=[], chunk_size=1000):
        logging.debug(f"Adding {len(urls)} targets")
        if source:
            source_id = self.get_source_id(source)
            if not source_id:
                source_id = self.add_source(source)
        else:
            source_id = None

        for x in range(0, len(urls), chunk_size):
            urls_chunk = urls[x:x + chunk_size]
            urls_chunk_add = []
            for url in urls_chunk:
                if True in [blocklist.match(Target(url)) for blocklist in blocklists]:
                    logging.debug(f"Ignoring (matches blocklist pattern): {url}")
                else:
                    urls_chunk_add.append(get_parsed_url(url))

            self.execute("%s INTO targets (url, source_id) VALUES (%s, %s) %s"
                         % (self.insert, self.param, self.param, self.conflict),
                         [(url, source_id) for url in urls_chunk_add])

    def mark_target_scanned(self, target_id):
        self.execute("UPDATE targets SET scanned = 1 WHERE id = %s" % self.param, (target_id,))

    def delete_target(self, url):
        logging.debug(f"Deleting target {url}")
        self.execute("DELETE FROM targets WHERE url = %s" % self.param, (url,))

    def flush_targets(self):
        logging.info("Flushing targets")
        self.execute("DELETE FROM targets")
        self.execute("DELETE FROM sources")

    def add_source(self, source):
        logging.debug(f"Adding source {source}")
        row = self.execute("%s INTO sources (source) VALUES (%s) %s RETURNING id"
                           % (self.insert, self.param, self.conflict),
                           (source,), fetch=1)
        return row if not row else row[0]

    def get_source_id(self, source):
        row = self.execute("SELECT id FROM sources WHERE source = %s"
                           % self.param, (source,), fetch=1)
        return row if not row else row[0]

    def get_sources(self):
        rows = self.execute("SELECT source FROM sources ORDER BY id ASC", fetch=True)
        return [row[0] for row in rows]

    def add_fingerprint(self, fingerprint, scanned=False):
        logging.debug(f"Adding fingerprint {fingerprint}")
        row = self.execute("%s INTO fingerprints (fingerprint, scanned) VALUES (%s, %s) %s RETURNING id"
                           % (self.insert, self.param, self.param, self.conflict),
                           (fingerprint, 1 if scanned else 0), fetch=1)
        return row if not row else row[0]

    def update_target_fingerprint(self, target_id, fingerprint_id):
        logging.debug(f"Updating target fingerprint id {target_id}->{fingerprint_id}")
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
                           % self.param, (fingerprint,), fetch=1)
        return row if not row else row[0]

    def mark_fingerprint_scanned(self, fingerprint_id):
        self.execute("UPDATE fingerprints SET scanned = 1 WHERE id = %s" % self.param, (fingerprint_id,))

    def prune(self, blocklists, source, random):
        logging.info("Pruning database")
        sql, parameters = self.get_unscanned_query(source=source, random=random)
        targets = self.execute(sql, parameters, fetch=True)
        if not targets:
            return
        targets.reverse()
        fingerprints = {}
        while targets:
            url, target_id, fingerprint_id, fingerprint = targets.pop()

            if True in [blocklist.match(Target(url)) for blocklist in blocklists]:
                logging.debug(f"Deleting (matches blocklist pattern): {url}")
                self.delete_target(url)

            elif fingerprint_id:
                if fingerprint in fingerprints:
                    logging.debug(f"Skipping (matches existing fingerprint): {url}")
                    self.mark_target_scanned(target_id)
                else:
                    logging.debug(f"Found unique fingerprint: {url}")
                    fingerprints[fingerprint] = fingerprint_id

            else:
                logging.debug(f"Computing fingerprint: {url}")
                fingerprint = generate_fingerprint(url)

                if fingerprint in fingerprints:
                    logging.debug(f"Skipping (matches existing fingerprint): {url}")
                    fingerprint_id = fingerprints[fingerprint]
                    self.mark_target_scanned(target_id)
                else:
                    fingerprint_id = self.get_fingerprint_id(fingerprint)
                    if fingerprint_id:
                        logging.debug(f"Skipping (matches existing fingerprint): {url}")
                    else:
                        logging.debug(f"Found unique fingerprint: {url}")
                        fingerprint_id = self.add_fingerprint(fingerprint, scanned=False)
                    fingerprints[fingerprint] = fingerprint_id

                self.update_target_fingerprint(target_id, fingerprint_id)

    def get_fingerprintless_query(self, source=False):
        sql = "SELECT t.url, t.id FROM targets t"
        if source and source is not True:
            sql += " INNER JOIN sources s on s.id = t.source_id"
        sql += " WHERE t.fingerprint_id IS NULL"
        if source and source is not True:
            sql += " AND s.source = %s" % self.param
            parameters = (source,)
        else:
            parameters = ()
        return sql, parameters

    def generate_fingerprints(self, source):
        logging.info("Generating fingerprints")
        sql, parameters = self.get_fingerprintless_query(source=source)
        targets = self.execute(sql, parameters, fetch=True)
        targets.reverse()
        fingerprints = {}
        while targets:
            url, target_id = targets.pop()
            fingerprint = generate_fingerprint(url)
            if fingerprint in fingerprints:
                fingerprint_id = fingerprints[fingerprint]
            else:
                fingerprint_id = self.get_fingerprint_id(fingerprint)
                if fingerprint_id:
                    fingerprints[fingerprint] = fingerprint_id
                else:
                    fingerprint_id = self.add_fingerprint(fingerprint, scanned=False)
                    fingerprints[fingerprint] = fingerprint_id
            self.update_target_fingerprint(target_id, fingerprint_id)
