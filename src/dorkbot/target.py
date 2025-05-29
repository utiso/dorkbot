#!/usr/bin/env python3
if __package__:
    from dorkbot.util import generate_timestamp, generate_hash
else:
    from util import generate_timestamp, generate_hash
import ipaddress
import json
import logging
import os
import socket
from urllib.parse import urlparse


class Target:
    def __init__(self, url):
        self.url = url
        self.host = None
        self.ip = None
        self.hash = None
        self.starttime = generate_timestamp()
        self.endtime = ""

        try:
            self.host = urlparse(self.url).hostname
        except Exception:
            logging.debug(f"Failed to parse host from url: {self.url}")
            raise

        if not self.host:
            return

        try:
            self.ip = ipaddress.ip_address(socket.gethostbyname(self.host))
        except Exception:
            logging.debug(f"Failed to resolve ip address for host: {self.host}")
            raise

    def get_hash(self):
        if not self.hash:
            self.hash = generate_hash(self.url)
        return self.hash

    def write_report(self, scanner_args, vulnerabilities):
        vulns = {}
        vulns["vulnerabilities"] = vulnerabilities
        vulns["starttime"] = str(self.starttime)
        vulns["endtime"] = str(self.endtime)
        vulns["url"] = self.url
        vulns["label"] = scanner_args.label

        if scanner_args.report_filename:
            report_filename = scanner_args.report_filename
        else:
            report_filename = self.get_hash() + ".json"

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
                json.dump(vulns, outfile, indent=indent, sort_keys=True)
                outfile.write('\n')
                logging.info("Report saved to: %s" % outfile.name)
        except OSError as e:
            logging.error(f"Failed to write report - {str(e)}")
            raise
