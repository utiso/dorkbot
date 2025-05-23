#!/usr/bin/env python3
if __package__:
    from dorkbot.util import get_database_module
else:
    from util import get_database_module
import logging
import os
import time
from contextlib import closing


class Database:
    def __init__(self, address, retries, retry_on):
        self.address = address
        self.retries = retries
        self.retry_on = retry_on

        if address.startswith("postgresql://"):
            self.module = get_database_module(address)
            self.database = address
            self.id_type = "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
            self.insert = "INSERT"
            self.conflict = "ON CONFLICT DO NOTHING"
            self.param = "%s"
            self.connect_kwargs = {}

        elif address.startswith("sqlite3://"):
            self.module = get_database_module(address)
            self.database = os.path.expanduser(address[10:])
            self.id_type = "INTEGER PRIMARY KEY"
            self.insert = "INSERT OR REPLACE"
            self.conflict = ""
            self.param = "?"
            self.connect_kwargs = {}

        else:
            self.database = None

    def connect(self):
        for i in range(self.retries + 1):
            try:
                self.db = self.module.connect(self.database, **self.connect_kwargs)
                break
            except self.module.Error as e:
                if i < self.retries and any(string in str(e) for string in self.retry_on):
                    logging.warning(f"Database connection failed (attempt {i + 1} of {self.retries}) - {str(e)}")
                    time.sleep(2 ** (5 + i))
                    continue
                else:
                    logging.error(f"Database connection failed - {str(e)}")
                    raise

    def close(self):
        self.db.close()

    def execute(self, *sql, fetch=0):
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
                if i < self.retries and any(error in str(e) for error in self.retry_on):
                    logging.warning(f"Database execution failed (attempt {i + 1} of {self.retries}) - {str(e)}")
                    self.close()
                    time.sleep(2 ** (5 + i))
                    self.connect()
                    continue
                else:
                    logging.error(f"Database execution failed - {str(e)}")
                    raise
