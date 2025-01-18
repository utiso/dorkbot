#!/usr/bin/env python3
import importlib
import ipaddress
import logging
import os
import re
import sys
from contextlib import closing


class Blocklist:
    def __init__(self, blocklist):
        self.connect_kwargs = {}
        self.ip_set = set()
        self.host_set = set()
        self.regex_set = set()

        if blocklist.startswith("postgresql://"):
            self.database = blocklist
            module_name = "psycopg2"
            self.insert = "INSERT"
            self.conflict = "ON CONFLICT DO NOTHING"
        elif blocklist.startswith("phoenixdb://"):
            self.database = blocklist[12:]
            module_name = "phoenixdb"
            self.insert = "UPSERT"
            self.conflict = ""
            self.connect_kwargs["autocommit"] = True
        elif blocklist.startswith("sqlite3://"):
            self.database = os.path.expanduser(blocklist[10:])
            module_name = "sqlite3"
            database_dir = os.path.dirname(self.database)
            self.insert = "INSERT OR REPLACE"
            self.conflict = ""
            if database_dir and not os.path.isdir(database_dir):
                try:
                    os.makedirs(database_dir)
                except OSError as e:
                    logging.error("Failed to create directory - %s", str(e))
                    sys.exit(1)
        else:
            self.database = False
            self.filename = blocklist
            try:
                self.blocklist_file = open(self.filename, "r")
            except Exception as e:
                logging.error("Failed to read blocklist file - %s", str(e))
                sys.exit(1)

        if self.database:
            self.module = importlib.import_module(module_name, package=None)

            if self.module.paramstyle == "qmark":
                self.param = "?"
            else:
                self.param = "%s"

            self.connect()
            self.execute("CREATE TABLE IF NOT EXISTS blocklist (item VARCHAR PRIMARY KEY)")

        self.parse_list(self.read_items())

    def connect(self, retries=3):
        if self.database:
            for i in range(retries):
                try:
                    self.db = self.module.connect(self.database, **self.connect_kwargs)
                    break
                except self.module.Error as e:
                    retry_conditions = ["Connection timed out"]
                    if i < retries - 1 and any(error in str(e) for error in retry_conditions):
                        logging.warning(f"Blocklist database connection failed (retrying) - {str(e)}")
                        continue
                    else:
                        logging.error(f"Blocklist database connection failed (will not retry) - {str(e)}")
                        sys.exit(1)

        else:
            try:
                self.blocklist_file = open(self.filename, "a")
            except Exception as e:
                logging.error("Failed to read blocklist file - %s", str(e))
                sys.exit(1)

    def close(self):
        if self.database:
            self.db.close()
        else:
            self.blocklist_file.close()

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

    def parse_list(self, items):
        for item in items:
            if item.startswith("ip:"):
                ip = item.split(":")[1]
                try:
                    ip_net = ipaddress.ip_network(ip)
                except ValueError as e:
                    logging.error("Could not parse blocklist item as ip - %s", str(e))
                self.ip_set.add(ip_net)
            elif item.startswith("host:"):
                self.host_set.add(item.split(":")[1])
            elif item.startswith("regex:"):
                self.regex_set.add(item.split(":")[1])
            else:
                logging.warning("Could not parse blocklist item - %s", item)

        pattern = "|".join(self.regex_set)
        if pattern:
            self.regex = re.compile(pattern)
        else:
            self.regex = None

    def get_parsed_items(self):
        parsed_ip_set = set()
        for ip_net in self.ip_set:
            if ip_net.num_addresses == 1:
                parsed_ip_set.add(str(ip_net[0]))
            else:
                parsed_ip_set.add(str(ip_net))

        return ["ip:" + item for item in parsed_ip_set] + \
               ["host:" + item for item in self.host_set] + \
               ["regex:" + item for item in self.regex_set]

    def read_items(self):
        if self.database:
            rows = self.execute("SELECT item FROM blocklist", fetchall=True)
            items = [row[0] for row in rows]
        else:
            items = self.blocklist_file.read().splitlines()

        return items

    def add(self, item):
        self.connect()

        if item.startswith("ip:"):
            ip = item.split(":")[1]
            try:
                ip_net = ipaddress.ip_network(ip)
            except ValueError as e:
                logging.error("Could not parse blocklist item as ip - %s", str(e))
                sys.exit(1)
            self.ip_set.add(ip_net)
        elif item.startswith("host:"):
            self.host_set.add(item.split(":")[1])
        elif item.startswith("regex:"):
            self.regex_set.add(item.split(":")[1])
        else:
            logging.error("Could not parse blocklist item - %s", item)
            sys.exit(1)

        if self.database:
            self.execute("%s INTO blocklist (item) VALUES (%s)" % (self.insert, self.param), (item,))
        else:
            logging.warning("Add ignored (not implemented for file-based blocklist)")

        self.close()

    def delete(self, item):
        self.connect()

        if self.database:
            self.execute("DELETE FROM blocklist WHERE item=(%s)" % self.param, (item,))
        else:
            logging.warning("Delete ignored (not implemented for file-based blocklist)")

        self.close()

    def match(self, target):
        if self.regex and self.regex.match(target.url):
            return True

        if target.host in self.host_set:
            return True

        for ip_net in self.ip_set:
            if target.ip and target.ip in ip_net:
                return True

        return False

    def flush(self):
        logging.info("Flushing blocklist")
        if self.database:
            self.execute("DELETE FROM blocklist")
        else:
            try:
                os.unlink(self.filename)
            except OSError as e:
                logging.error("Failed to delete blocklist file - %s", str(e))
                sys.exit(1)

        self.regex = None
        self.regex_set = set()
        self.ip_set = set()
        self.host_set = set()
