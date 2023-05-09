![Image of Dorkbot](https://security.utexas.edu/sites/default/files/Artboard%203_0.png)

dorkbot
=======

Scan Google (or other) search results for vulnerabilities.

dorkbot is a modular command-line tool for performing vulnerability scans against sets of webpages returned by Google search queries or other supported sources. It is broken up into two sets of modules:

* *Indexers* - modules that return a list of targets
* *Scanners* - modules that perform a vulnerability scan against each target

Targets are stored in a database as they are indexed. Once scanned, a standard JSON report is produced containing any vulnerabilities found. Indexing and scanning processes can be run separately or combined in a single command (up to one of each).

Quickstart
==========
* Create a Google API credential via the [Developer Console](https://console.developers.google.com)
* Create a Google [Custom Search Engine](https://www.google.com/cse/) and note the search engine ID, e.g. 012345678901234567891:abc12defg3h
<pre>$ pip3 install dorkbot wapiti3</pre>
<pre>$ dorkbot -i google_api -o key=your_api_credential_here -o engine=your_engine_id_here -o query="filetype:php inurl:id"</pre>
<pre>$ dorkbot -s wapiti</pre>

Help
====
<pre>
 -h, --help            Show program (or specified module) help
</pre>
<pre>
  --show-defaults       Show default values in help output
</pre>

Usage
=====
<pre>
usage: dorkbot.py [-c CONFIG] [-r DIRECTORY] [--source [SOURCE]]
                  [--show-defaults] [--count COUNT] [--random] [-h]
                  [--log LOG] [-v] [-V] [-d DATABASE] [-u] [-l]
                  [--list-unscanned] [--add-target TARGET]
                  [--delete-target TARGET] [--flush-targets] [-i INDEXER]
                  [-o INDEXER_ARG] [-s SCANNER] [-p SCANNER_ARG] [-f]
                  [-b BLOCKLIST] [--list-blocklist]
                  [--add-blocklist-item ITEM] [--delete-blocklist-item ITEM]
                  [--flush-blocklist]

options:
  -c CONFIG, --config CONFIG
                        Configuration file
  -r DIRECTORY, --directory DIRECTORY
                        Dorkbot directory (default location of db, tools,
                        reports)
  --source [SOURCE]     Label associated with targets
  --show-defaults       Show default values in help output
  -h, --help            Show program (or specified module) help
  --log LOG             Path to log file
  -v, --verbose         Enable verbose logging (DEBUG output)
  -V, --version         Print version

global scanner options:
  --count COUNT         number of urls to scan, or -1 to scan all urls
  --random              retrieve urls in random order

database:
  -d DATABASE, --database DATABASE
                        Database file/uri
  -u, --prune           Apply fingerprinting and blocklist without scanning

targets:
  -l, --list-targets    List targets in database
  --list-unscanned      List unscanned targets in database
  --add-target TARGET   Add a url to the target database
  --delete-target TARGET
                        Delete a url from the target database
  --flush-targets       Delete all targets

indexing:
  -i INDEXER, --indexer INDEXER
                        Indexer module to use
  -o INDEXER_ARG, --indexer-arg INDEXER_ARG
                        Pass an argument to the indexer module (can be used
                        multiple times)

scanning:
  -s SCANNER, --scanner SCANNER
                        Scanner module to use
  -p SCANNER_ARG, --scanner-arg SCANNER_ARG
                        Pass an argument to the scanner module (can be used
                        multiple times)

fingerprints:
  -f, --flush-fingerprints
                        Delete all fingerprints of previously-scanned items

blocklist:
  -b BLOCKLIST, --blocklist BLOCKLIST
                        Blocklist file/uri
  --list-blocklist      List blocklist entries
  --add-blocklist-item ITEM
                        Add an ip/host/regex pattern to the blocklist
  --delete-blocklist-item ITEM
                        Delete an item from the blocklist
  --flush-blocklist     Delete all blocklist items
</pre>

Tools / Dependencies
=====
* [psycopg2-binary](https://pypi.org/project/psycopg2-binary/) or [psycopg2](https://pypi.org/project/psycopg2/) (if using PostgreSQL)
* [phoenixdb](https://pypi.org/project/phoenixdb/) (if using PhoenixDB)
* [PhantomJS](http://phantomjs.org/) (if using non-api google indexer)
* [Arachni](http://www.arachni-scanner.com/)
* [Wapiti](http://wapiti.sourceforge.net/)

As needed, dorkbot will search for tools in the following order:
* Directory specified via relevant module option
* Located in *tools* directory (within current directory, by default), with the subdirectory named after the tool
* Available in the user's PATH (e.g. installed system-wide)

Files
=====
All SQLite3 databases, tools, and reports are saved in the dorkbot directory, which by default is the current directory. You can force a specific directory with the --directory flag. Default file paths within this directory are as follows:

* SQLite3 database file: *dorkbot.db*
* External tools directory: *tools/*
* Scan report output directory: *reports/*

Configuration files are by default read from *~/.config/dorkbot/* (Linux / MacOS) or in the Application Data folder (Windows), honoring $XDG_CONFIG_HOME / %APPDATA%. Default file paths within this directory are as follows:

* Dorkbot configuration file: *dorkbot.ini*

Config File
===========
The configuration file (dorkbot.ini) can be used to prepopulate certain command-line flags.

Example dorkbot.ini:
<pre>
[dorkbot]
database=/opt/dorkbot/dorkbot.db
[indexers.wayback]
domain=example.com
from=2022
[scanners.arachni]
arachni_dir=/opt/arachni
report_dir=/tmp/reports
</pre>

Blocklist
=========
The blocklist is a list of ip addresses, hostnames, or regular expressions of url patterns that should *not* be scanned. If a target url matches any item in this list it will be skipped and removed from the database. By default the blocklist is stored in the dorkbot database, but a separate database or file can be specified by passing the appropriate connection uri or file path to --blocklist. Note: --add-blocklist-item / --delete-blocklist-item are not implemented for file-based blocklists, and --flush-blocklist deletes the file.

Supported external blocklists:
* postgresql://[server info]
* phoenixdb://[server info]
* sqlite3:///path/to/blocklist.db
* /path/to/blocklist.txt

Example blocklist items:
<pre>
regex:^[^\?]+$
regex:.*login.*
regex:^https?://[^.]*.example.com/.*
host:www.google.com
ip:127.0.0.1
</pre>

The first item will remove any target that doesn't contain a question mark, in other words any url that doesn't contain any GET parameters to test. The second attempts to avoid login functions, and the third blocklists all target urls on example.com. The fourth excludes targets with a hostname of www.google.com and the fifth excludes targets whose host resolves to 127.0.0.1.

Prune
=====
The prune flag iterates through all targets, computes the fingerprints in memory, and marks subsequent matching targets as scanned. Additionally it deletes any target matching a blocklist item. The result is a database where --list-unscanned returns only scannable urls. It honors the **random** flag to compute fingerprints in random order.

General Options
===============
These options are applicable regardless of module chosen:
<pre>
  --source [SOURCE]     Label associated with targets
  --count COUNT         number of urls to scan, or -1 to scan all urls
  --random              retrieve urls in random order
</pre>

Indexer Modules
===============
### google ###
<pre>
  Searches google.com via scraping

  --engine ENGINE       CSE id
  --query QUERY         search query
  --phantomjs-dir PHANTOMJS_DIR
                        phantomjs base dir containing bin/phantomjs
  --domain DOMAIN       limit searches to specified domain
</pre>

### google_api ###
<pre>
  Searches google.com

  --key KEY             API key
  --engine ENGINE       CSE id
  --query QUERY         search query
  --domain DOMAIN       limit searches to specified domain
</pre>

### pywb ###
<pre>
  Searches a given pywb server's crawl data

  --server SERVER       pywb server url
  --domain DOMAIN       pull all results for given domain or subdomain
  --cdx-api-suffix CDX_API_SUFFIX
                        suffix after index for index api
  --index INDEX         search a specific index
  --filter FILTER       query filter to apply to the search
  --retries RETRIES     number of times to retry fetching results on error
  --threads THREADS     number of concurrent requests to wayback.org
</pre>

### commoncrawl ###
<pre>
  Searches commoncrawl.org crawl data

  --domain DOMAIN       pull all results for given domain or subdomain
  --index INDEX         search a specific index, e.g. CC-MAIN-2019-22 (default: latest)
  --filter FILTER       query filter to apply to the search
  --retries RETRIES     number of times to retry fetching results on error
  --threads THREADS     number of concurrent requests to commoncrawl.org
</pre>

### wayback ###
<pre>
  Searches archive.org crawl data

  --domain DOMAIN       pull all results for given domain or subdomain
  --filter FILTER       query filter to apply to the search
  --from FROM           beginning timestamp
  --to TO               end timestamp
  --retries RETRIES     number of times to retry fetching results on error
  --threads THREADS     number of concurrent requests to wayback.org
</pre>

### bing_api ###
<pre>
  Searches bing.com

  --key KEY             API key
  --query QUERY         search query
</pre>

### stdin ###
<pre>
  Accepts urls from stdin, one per line
</pre>

Scanner Modules
===============
### arachni ###
<pre>
  Scans with the arachni command-line scanner

  --arachni-dir ARACHNI_DIR
                        arachni base dir containing bin/arachni and bin/arachni_reporter
  --args ARGS           space-delimited list of additional arguments
  --report-dir REPORT_DIR
                        directory to save vulnerability report
  --label LABEL         friendly name field to include in vulnerability report
</pre>

### wapiti ###
<pre>
  Scans with the wapiti3 command-line scanner

  --wapiti-dir WAPITI_DIR
                        wapiti base dir containing bin/wapiti
  --args ARGS           space-delimited list of additional arguments
  --report-dir REPORT_DIR
                        directory to save vulnerability report
  --label LABEL         friendly name field to include in vulnerability report
</pre>

