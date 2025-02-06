import datetime
import hashlib
import importlib
import importlib.util
import logging
import os
import sys
from urllib.parse import urlparse


def generate_fingerprint(url):
    url_parts = urlparse(url)
    netloc = url_parts.netloc
    depth = str(url_parts.path.count("/"))
    page = url_parts.path.split("/")[-1]
    params = []
    for param in url_parts.query.split("&"):
        split = param.split("=", 1)
        if len(split) == 2 and split[1]:
            params.append(split[0])
    fingerprint = "|".join((netloc, depth, page, ",".join(sorted(params))))
    return generate_hash(fingerprint)


def generate_timestamp():
    return datetime.datetime.now().astimezone().isoformat()


def generate_hash(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def get_database_module(address):
    module_name = None

    if address.startswith("postgresql://"):
        for module in ["psycopg", "psycopg2"]:
            module_spec = importlib.util.find_spec(module)
            if module_spec:
                module_name = module
                break
        if not module_name:
            logging.error("Missing postgresql module - try pip install psycopg[binary] or psycopg2-binary")
            sys.exit(1)

    elif address.startswith("sqlite3://"):
        module = "sqlite3"
        module_spec = importlib.util.find_spec(module)
        if module_spec:
            module_name = module
        else:
            logging.error("Missing sqlite3 module - try pip install sqlite3")
            sys.exit(1)

    return importlib.import_module(module_name, package=None)


def get_database_attributes(address):
    attributes = {}

    if address.startswith("postgresql://"):
        attributes.update({
            "module": get_database_module(address),
            "database": address,
            "id_type": "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
            "insert": "INSERT",
            "conflict": "ON CONFLICT DO NOTHING",
            "param": "%s",
            "connect_kwargs": {},
        })

    elif address.startswith("sqlite3://"):
        attributes.update({
            "module": get_database_module(address),
            "database": os.path.expanduser(address[10:]),
            "id_type": "INTEGER PRIMARY KEY",
            "insert": "INSERT OR REPLACE",
            "conflict": "",
            "param": "?",
            "connect_kwargs": {},
        })

    else:
        attributes.update({
            "database": False,
            "filename": address,
        })

    return attributes
