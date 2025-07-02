#!/usr/bin/env python3
if __package__:
    from dorkbot.database import Database
    from dorkbot.target import Target
    from dorkbot.util import generate_fingerprint, get_parsed_url
else:
    from database import Database
    from target import Target
    from util import generate_fingerprint, get_parsed_url
import logging
import os


class TargetDatabase(Database):
    def __init__(self, address, drop_tables=False, create_tables=False, retries=0, retry_on=[]):
        protocols = ["postgresql://", "sqlite3://"]
        if not any(address.startswith(protocol) for protocol in protocols):
            address = f"sqlite3://{address}"
        Database.__init__(self, address, retries, retry_on)

        if self.database and address.startswith("sqlite3://"):
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

    def get_urls(self, args):
        options = {"unscanned_only": args.unscanned_only, "count": args.count}
        sql, parameters = self.get_targets_query(args, **options)
        rows = self.execute(sql, parameters, fetch=True) or []
        urls = []
        for row in rows:
            url = row[0]
            if args.source is True:
                url += f" | {row[-1]}"
            urls.append(url)
        return urls

    def get_targets_query(self, args, unscanned_only=False, count_only=False, count=0):
        fields = ["t.url", "t.id", "t.fingerprint_id", "f.fingerprint"]
        join = [("LEFT", "fingerprints f ON f.id = t.fingerprint_id")]
        where = []
        parameters = ()

        if unscanned_only:
            where.extend(["t.scanned = '0'", "(t.fingerprint_id IS NULL OR f.scanned = '0')"])

        if args.source:
            fields.append("s.source")
            if args.source is True:
                join_type = "LEFT"
            else:
                join_type = "INNER"
                where.append("s.source = %s" % self.param)
                parameters = (args.source,)
            join.append((join_type, "sources s ON s.id = t.source_id"))

        sql = "SELECT "
        if count_only:
            sql += "COUNT(*)"
        else:
            for i, field in enumerate(fields):
                sql += "" if i == 0 else ", "
                sql += field
        sql += " FROM targets t"
        for join_type, join_criteria in join:
            sql += f" {join_type} JOIN {join_criteria}"
        for i, clause in enumerate(where):
            sql += " WHERE " if i == 0 else " AND "
            sql += clause
        if not count_only:
            sql += " ORDER BY "
            sql += "RANDOM()" if args.random else "t.id ASC"
        sql += f" LIMIT {count}" if count else ""

        return sql, parameters

    def matches_blocklists(self, url, blocklists, args=None):
        target = Target(url)
        for blocklist in blocklists:
            try:
                if match := blocklist.match(target):
                    logging.debug(f"Matches blocklist: {url} ({match=})")
                    return match
            except Exception:
                if args and args.delete_on_error:
                    self.delete_target(url)
                    return None
        return False

    def get_next_target(self, args, blocklists=[]):
        options = {"unscanned_only": True}
        sql, parameters = self.get_targets_query(args, **options)
        target = None
        fingerprints = {}
        while True:
            row = self.execute(sql, parameters, fetch=1)
            if not row:
                break
            url, target_id, fingerprint_id, fingerprint, *_ = row

            if match := self.matches_blocklists(url, blocklists, args=args):
                self.delete_target(url)
                continue
            elif match is None:
                continue

            if fingerprint_id:
                logging.debug(f"Found unique fingerprint: {url}")
                if not args.test:
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
                        fingerprint_id = self.add_fingerprint(fingerprint, scanned=(not args.test))
                        target = url
                self.update_target_fingerprint(target_id, fingerprint_id)

            if target:
                break
        return target

    def add_target(self, url, source=None, blocklists=[]):
        match = self.matches_blocklists(url, blocklists)
        if match or match is None:
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
        if source:
            source_id = self.get_source_id(source)
            if not source_id:
                source_id = self.add_source(source)
        else:
            source_id = None

        valid_urls = []
        for url in urls:
            match = self.matches_blocklists(url, blocklists)
            if not match and match is not None:
                valid_urls.append(get_parsed_url(url))

        logging.debug(f"Adding {len(valid_urls)} targets")
        for x in range(0, len(valid_urls), chunk_size):
            urls_chunk = valid_urls[x:x + chunk_size]
            self.execute("%s INTO targets (url, source_id) VALUES (%s, %s) %s"
                         % (self.insert, self.param, self.param, self.conflict),
                         [(url, source_id) for url in urls_chunk])

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
        return [row[0] for row in rows] if rows else []

    def get_target_count(self, args, unscanned_only=False):
        sql, parameters = self.get_targets_query(args, unscanned_only, count_only=True)
        row = self.execute(sql, parameters, fetch=1)
        return 0 if not row else row[0]

    def get_fingerprint_count(self):
        row = self.execute("SELECT COUNT(*) FROM fingerprints", fetch=1)
        return 0 if not row else row[0]

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

    def prune(self, blocklists, args):
        logging.info("Pruning database")
        options = {"unscanned_only": args.unscanned_only, "count": args.count}
        sql, parameters = self.get_targets_query(args, **options)
        targets = self.execute(sql, parameters, fetch=True)
        if not targets:
            return
        targets.reverse()
        fingerprints = {}
        while targets:
            url, target_id, fingerprint_id, fingerprint, *_ = targets.pop()

            if self.matches_blocklists(url, blocklists, args=args):
                self.delete_target(url)
                continue

            if fingerprint_id:
                if fingerprint in fingerprints:
                    fingerprint_id, fingerprint_count = fingerprints[fingerprint]
                    if args.fingerprint_max and fingerprint_count >= args.fingerprint_max:
                        logging.debug(f"Deleting (exceeds max fingerprint count): {url}")
                        self.delete_target(url)
                    else:
                        logging.debug(f"Skipping (matches existing fingerprint): {url}")
                        fingerprints[fingerprint] = (fingerprint_id, fingerprint_count + 1)
                        self.mark_target_scanned(target_id)
                else:
                    logging.debug(f"Found unique fingerprint: {url}")
                    fingerprints[fingerprint] = (fingerprint_id, 1)

            else:
                logging.debug(f"Computing fingerprint: {url}")
                fingerprint = generate_fingerprint(url)

                if fingerprint in fingerprints:
                    fingerprint_id, fingerprint_count = fingerprints[fingerprint]
                    if args.fingerprint_max and fingerprint_count >= args.fingerprint_max:
                        logging.debug(f"Deleting (exceeds max fingerprint count): {url}")
                        self.delete_target(url)
                    else:
                        logging.debug(f"Skipping (matches existing fingerprint): {url}")
                        fingerprints[fingerprint] = (fingerprint_id, fingerprint_count + 1)
                        self.mark_target_scanned(target_id)
                else:
                    fingerprint_id = self.get_fingerprint_id(fingerprint)
                    if fingerprint_id:
                        logging.debug(f"Skipping (matches existing fingerprint): {url}")
                    else:
                        logging.debug(f"Found unique fingerprint: {url}")
                        fingerprint_id = self.add_fingerprint(fingerprint, scanned=False)
                    fingerprints[fingerprint] = (fingerprint_id, 1)

                self.update_target_fingerprint(target_id, fingerprint_id)

    def get_fingerprintless_query(self, args):
        join, where = [], []

        if args.source and args.source is not True:
            join.append(("INNER", "sources s ON s.id = t.source_id"))
            where.append("s.source = %s" % self.param)
            parameters = (args.source,)
        else:
            parameters = ()

        sql = "SELECT t.url, t.id FROM targets t"
        for join_type, join_criteria in join:
            sql += f" {join_type} JOIN {join_criteria}"
        sql += " WHERE t.fingerprint_id IS NULL"
        for clause in where:
            sql += f" AND {clause}"
        sql += f" LIMIT {args.count}" if args.count else ""

        return sql, parameters

    def generate_fingerprints(self, args):
        logging.info("Generating fingerprints")
        sql, parameters = self.get_fingerprintless_query(args)
        targets = self.execute(sql, parameters, fetch=True)
        if targets:
            targets.reverse()
        fingerprints = {}
        while targets:
            url, target_id = targets.pop()
            fingerprint = generate_fingerprint(url)
            if fingerprint in fingerprints:
                fingerprint_id, fingerprint_count = fingerprints[fingerprint]
                if args.fingerprint_max and fingerprint_count >= args.fingerprint_max:
                    logging.debug(f"Deleting (exceeds max fingerprint count): {url}")
                    self.delete_target(url)
                    continue
                else:
                    fingerprints[fingerprint] = (fingerprint_id, fingerprint_count + 1)
            else:
                fingerprint_id = self.get_fingerprint_id(fingerprint)
                if fingerprint_id:
                    fingerprints[fingerprint] = (fingerprint_id, 1)
                else:
                    fingerprint_id = self.add_fingerprint(fingerprint, scanned=False)
                    fingerprints[fingerprint] = (fingerprint_id, 1)
            self.update_target_fingerprint(target_id, fingerprint_id)
