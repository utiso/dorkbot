import datetime
import hashlib
import importlib
import importlib.util
import ipaddress
import json
import logging
import os
import socket
from urllib.parse import parse_qsl, quote, urlencode, urlparse


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


def parse_host(url):
    host = None
    try:
        host = urlparse(url).hostname
    except Exception:
        logging.debug(f"Failed to parse host from url: {url}")
        raise
    return host


def resolve_ip(host):
    ip = None
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(host))
    except Exception:
        logging.debug(f"Failed to resolve ip address for host: {host}")
        raise
    return ip


def get_parsed_url(url):
    url_parts = urlparse(url)
    quoted_path = quote(url_parts.path)
    encoded_query = urlencode(parse_qsl(url_parts.query, keep_blank_values=True))
    parsed_url = url_parts._replace(path=quoted_path, query=encoded_query)
    return parsed_url.geturl()


def get_database_module(address):
    module_name = None

    if address.startswith("postgresql://"):
        for module in ["psycopg", "psycopg2"]:
            module_spec = importlib.util.find_spec(module)
            if module_spec:
                module_name = module
                break
        if not module_name:
            logging.error("Missing postgresql module - try: pip install psycopg[binary]")
            raise

    elif address.startswith("sqlite3://"):
        module = "sqlite3"
        module_spec = importlib.util.find_spec(module)
        if module_spec:
            module_name = module
        else:
            logging.error("Missing sqlite3 module - try: pip install sqlite3")
            raise

    else:
        logging.error(f"Unknown database protocol for address: {address}")
        raise ImportError

    return importlib.import_module(module_name, package=None)


def generate_report(url, start_time, end_time, label, vulnerabilities):
    vulns = {}
    vulns["vulnerabilities"] = vulnerabilities
    vulns["starttime"] = start_time
    vulns["endtime"] = end_time
    vulns["url"] = url
    vulns["label"] = label
    return vulns


def write_report(report, scanner_args, hash=None):
    if scanner_args.report_filename:
        report_filename = scanner_args.report_filename
    else:
        if not hash:
            hash = generate_hash(report["url"])
        report_filename = hash + ".json"

    filename = os.path.join(scanner_args.report_dir, report_filename)

    if scanner_args.report_append:
        report_mode = "a"
    else:
        report_mode = "w"

    indent = scanner_args.report_indent
    if indent and indent.isdigit():
        indent = int(indent)

    try:
        os.makedirs(os.path.abspath(scanner_args.report_dir), exist_ok=True)
        with open(filename, report_mode) as outfile:
            json.dump(report, outfile, indent=indent, sort_keys=True)
            outfile.write('\n')
            logging.info("Report saved to: %s" % outfile.name)
    except OSError as e:
        logging.error(f"Failed to write report - {str(e)}")
        raise
