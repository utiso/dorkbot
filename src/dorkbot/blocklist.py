#!/usr/bin/env python3
import ipaddress
import logging
import os
import re
if __package__:
    from dorkbot.database import Database
else:
    from database import Database


class Blocklist(Database):
    def __init__(self, address, drop_tables=False, create_tables=False, retries=0, retry_on=[]):
        Database.__init__(self, address, retries, retry_on)
        self.ip_set = set()
        self.host_set = set()
        self.regex_set = set()

        if self.database:
            if address.startswith("sqlite3://"):
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(self.database)), exist_ok=True)
                except OSError as e:
                    logging.error(f"Failed to create parent directory for database file - {str(e)}")
                    raise

            self.connect()

            if drop_tables:
                logging.debug("Dropping tables")
                self.execute("DROP TABLE IF EXISTS blocklist")

            if create_tables:
                self.execute("CREATE TABLE IF NOT EXISTS blocklist"
                             f" (id {self.id_type},"
                             " item VARCHAR)")

        else:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.address)), exist_ok=True)
                self.blocklist_file = open(self.address, "r")
            except OSError as e:
                logging.error(f"Failed to open database file - {str(e)}")
                raise

        self.parse_list(self.read_items())

    def connect(self):
        if self.database:
            Database.connect(self)
        else:
            try:
                self.blocklist_file = open(self.address, "a")
            except Exception as e:
                logging.error(f"Failed to read blocklist file - {str(e)}")
                raise

    def close(self):
        if self.database:
            self.db.close()
        else:
            self.address.close()

    def parse_list(self, items):
        for item in items:
            if item.startswith("ip:"):
                ip = item.split(":")[1]
                try:
                    ip_net = ipaddress.ip_network(ip)
                except ValueError as e:
                    logging.error(f"Could not parse blocklist item as ip - {str(e)}")
                    continue
                self.ip_set.add(ip_net)
            elif item.startswith("host:"):
                self.host_set.add(item.split(":")[1])
            elif item.startswith("regex:"):
                self.regex_set.add(item.split(":")[1])
            else:
                logging.warning(f"Could not parse blocklist item - {item}")

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
            rows = self.execute("SELECT item FROM blocklist ORDER BY id ASC", fetch=True)
            items = [row[0] for row in rows] if rows else []
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
                logging.error(f"Could not parse blocklist item as ip - {str(e)}")
                raise
            self.ip_set.add(ip_net)
        elif item.startswith("host:"):
            self.host_set.add(item.split(":")[1])
        elif item.startswith("regex:"):
            self.regex_set.add(item.split(":")[1])
        else:
            logging.error("Could not parse blocklist item - %s", item)
            raise

        self.execute("%s INTO blocklist (item) VALUES (%s)" % (self.insert, self.param), (item,))
        self.close()

    def delete(self, item):
        self.connect()
        self.execute("DELETE FROM blocklist WHERE item=(%s)" % self.param, (item,))
        self.close()

    def match(self, target):
        if self.regex:
            if match := self.regex.match(target.url):
                return match.expand(r"\g<0>")

        if host := target.get_host():
            if host in self.host_set:
                return host

        if ip := target.get_ip():
            for ip_net in self.ip_set:
                if ip in ip_net:
                    return ip_net

        return False

    def flush(self):
        logging.info("Flushing blocklist")
        if self.database:
            self.execute("DELETE FROM blocklist")
        else:
            try:
                os.unlink(self.address)
            except OSError as e:
                logging.error(f"Failed to delete blocklist file - {str(e)}")
                raise

        self.regex = None
        self.regex_set = set()
        self.ip_set = set()
        self.host_set = set()
