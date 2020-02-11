![Image of Dorkbot](https://security.utexas.edu/sites/default/files/Artboard%203_0.png)

dorkbot
=======

Scan Google (or other) search results for vulnerabilities.

dorkbot is a modular command-line tool for performing vulnerability scans against sets of webpages returned by Google search queries or other supported sources. It is broken up into two sets of modules:

* *Indexers* - modules that return a list of targets
* *Scanners* - modules that perform a vulnerability scan against each target

Targets are stored in a local database file until they are scanned, at which point a standard JSON report is produced containing any vulnerabilities found. Indexing and scanning processes can be run separately or combined in a single command (up to one of each).

Usage
=====
<pre>
usage: dorkbot.py [-h] [-c CONFIG] [-r DIRECTORY] [--log LOG] [-v] [-V]
                  [-d DATABASE] [-u] [-l] [--add-target TARGET]
                  [--delete-target TARGET] [--flush-targets] [-i INDEXER]
                  [-o INDEXER_OPTION] [-s SCANNER] [-p SCANNER_OPTION] [-f]
                  [-b BLACKLIST] [--list-blacklist]
                  [--add-blacklist-item ITEM] [--delete-blacklist-item ITEM]
                  [--flush-blacklist]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Configuration file
  -r DIRECTORY, --directory DIRECTORY
                        Dorkbot directory (default location of db, tools,
                        reports)
  --log LOG             Path to log file
  -v, --verbose         Enable verbose logging (DEBUG output)
  -V, --version         Print version

database:
  -d DATABASE, --database DATABASE
                        Database file/uri
  -u, --prune           Delete unscannable targets (blacklist /
                        fingerprinting)

targets:
  -l, --list-targets    List targets in database
  --add-target TARGET   Add a url to the target database
  --delete-target TARGET
                        Delete a url from the target database
  --flush-targets       Delete all targets

indexing:
  -i INDEXER, --indexer INDEXER
                        Indexer module to use
  -o INDEXER_OPTION, --indexer-option INDEXER_OPTION
                        Pass an option to the indexer (can be used multiple
                        times)

scanning:
  -s SCANNER, --scanner SCANNER
                        Scanner module to use
  -p SCANNER_OPTION, --scanner-option SCANNER_OPTION
                        Pass an option to the scanner (can be used multiple
                        times)

fingerprints:
  -f, --flush-fingerprints
                        Delete all fingerprints of previously-scanned items

blacklist:
  -b BLACKLIST, --blacklist BLACKLIST
                        Blacklist file/uri
  --list-blacklist      List blacklist entries
  --add-blacklist-item ITEM
                        Add an ip/host/regex pattern to the blacklist
  --delete-blacklist-item ITEM
                        Delete an item from the blacklist
  --flush-blacklist     Delete all blacklist items
</pre>

Requirements
============
Python 3.x (cross-platform)
[psycopg2](http://initd.org/psycopg/) (if using PostgreSQL)

Tools
=====
* [PhantomJS](http://phantomjs.org/)
* [Arachni](http://www.arachni-scanner.com/)
* [Wapiti](http://wapiti.sourceforge.net/)

As needed, dorkbot will search for tools in the following order:
* Directory specified via relevant module option
* Located in *tools* directory (within current directory, by default), with the subdirectory named after the tool
* Available in the user's PATH (e.g. installed system-wide)

Quickstart
==========
Create a Google [Custom Search Engine](https://www.google.com/cse/) and note the search engine ID, e.g. 012345678901234567891:abc12defg3h.
<pre>$ mkdir tools</pre>, download Arachni and extract it as tools/arachni, or <pre>$ pip3 install wapiti3</pre>
<pre>$ sudo apt install phantomjs</pre>
<pre>$ ./dorkbot.py -i google -o engine=012345678901234567891:abc12defg3h,query="filetype:php inurl:id"</pre>
<pre>$ ./dorkbot.py -s arachni</pre> OR <pre>$ ./dorkbot.py -s wapiti</pre>

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
</pre>

Blacklist
=========
The blacklist is a list of ip addresses, hostnames, or regular expressions of url patterns that should *not* be scanned. If a target url matches any item in this list it will be skipped and removed from the database. By default the blacklist is stored in the dorkbot database, but a separate database or file can be specified by passing the appropriate connection uri or file path to --blacklist. Note: --add-blacklist-item / --delete-blacklist-item are not implemented for file-based blacklists, and --flush-blacklist deletes the file.

Supported external blacklists:
* postgresql://[server info]
* phoenixdb://[server info]
* sqlite3:///path/to/blacklist.db
* /path/to/blacklist.txt

Example blacklist items:
<pre>
regex:^[^\?]+$
regex:.*login.*
regex:^https?://[^.]*.example.com/.*
host:www.google.com
ip:127.0.0.1
</pre>

The first item will remove any target that doesn't contain a question mark, in other words any url that doesn't contain any GET parameters to test. The second attempts to avoid login functions, and the third blacklists all target urls on example.com. The fourth excludes targets with a hostname of www.google.com and the fifth excludes targets whose host resolves to 127.0.0.1.

Indexer Modules
===============
### google ###
Search for targets in a Google Custom Search Engine (CSE) via custom search element.

Requirements: [PhantomJS](http://phantomjs.org/)

Options:
* **engine** - CSE id
* **query** - search query
* phantomjs_dir - phantomjs base directory containing bin/phantomjs (default: tools/phantomjs/)
* domain - limit searches to specified domain

### google_api ###
Search for targets in a Google Custom Search Engine (CSE) via JSON API.

Requirements: none

Options:
* **key** - API key
* **engine** - CSE id
* **query** - search query
* domain - limit searches to specified domain

### commoncrawl ###
Search for targets within commoncrawl.org results.

Requirements: none

Options:
* **domain** - pull all results for given domain or subdomain
* index - search a specific index, e.g. CC-MAIN-2019-22 (default: latest)
* filter - query filter to apply to the search
* retries - number of times to retry fetching results on error
* threads - number concurrent requests to commoncrawl.org

### wayback ###
Search for targets within archive.org results.

Requirements: none

Options:
* **domain** - pull all results for given domain or subdomain
* filter - query filter to apply to the search
* from - beginning timestamp
* to - end timestamp

### bing_api ###
Search for targets via Bing Web Search API.

Requirements: none

Options:
* **key** - API key
* **query** - search query

### stdin ###
Read targets from standard input, one per line.

Requirements: none

Options: none

Scanner Modules
===============
### (general options) ###
These options are applicable regardless of module chosen

* report_dir - directory to save vulnerability report (default: reports/)
* label - friendly name field to include in vulnerability report
* count - number of urls to scan, or -1 to scan all urls (default: -1)
* random - scan urls in random order

### arachni ###
Scan targets with Arachni command-line scanner.

Requirements: [Arachni](http://www.arachni-scanner.com/)

Options:
* arachni_dir - arachni base directory containing bin/arachni and bin/arachni_reporter (default: tools/arachni/)
* args - space-delimited list of additional arguments, e.g. args="--http-user-agent Dorkbot/1.0 --timeout 00:15:00"

### wapiti ###
Scan targets with Wapiti command-line scanner.

Requirements: [Wapiti](http://wapiti.sourceforge.net/)

Options:
* wapiti_dir - wapiti base directory containing bin/wapiti (default: tools/wapiti/)
* args - space-delimited list of additional arguments

Prune
=====
The prune flag iterates through all targets, computes the fingerprints in memory, and deletes any target matching a blacklist item or fingerprint. The result is a database of only scannable urls. It honors (a subset of) the options specified in SCANNER_OPTIONS as follows:

* random - evaluate urls in random order when computing fingerprints

