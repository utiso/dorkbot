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
usage: dorkbot.py [-h] [-c CONFIG] [-d DATABASE] [-f] [-i INDEXER] [-l]
                  [-o INDEXER_OPTIONS] [-p SCANNER_OPTIONS] [-s SCANNER]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Configuration file
  -d DATABASE, --database DATABASE
                        SQLite3 database file or postgresql:// URI
  -f, --flush           Flush table of fingerprints of previously-scanned
                        items
  -i INDEXER, --indexer INDEXER
                        Indexer module to use
  -l, --list            List targets in database
  -o INDEXER_OPTIONS, --indexer-options INDEXER_OPTIONS
                        Indexer-specific options (opt1=val1,opt2=val2,..)
  -p SCANNER_OPTIONS, --scanner-options SCANNER_OPTIONS
                        Scanner-specific options (opt1=val1,opt2=val2,..)
  -s SCANNER, --scanner SCANNER
                        Scanner module to use
</pre>

Requirements
============
Python 2.7.x / 3.x (cross-platform)
[psycopg2](http://initd.org/psycopg/) (if using PostgreSQL)

Tools
=====
* [PhantomJS](http://phantomjs.org/)
* [Arachni](http://www.arachni-scanner.com/)
* [Wapiti](http://wapiti.sourceforge.net/)
* [cc.py](https://github.com/si9int/cc.py)

As needed, dorkbot will search for tools in the following order:
* Directory specified via relevant module option
* Located in dorkbot's *tools* directory, with the subdirectory named after the tool
* Available in the user's PATH (e.g. installed system-wide)

Quickstart
==========
Create a Google [Custom Search Engine](https://www.google.com/cse/) and note the search engine ID, e.g. 012345678901234567891:abc12defg3h.
Download either Arachni or Wapiti, unpack it into the tools directory, and rename the subdirectory to *arachni* or *wapiti* as appropriate.
<pre>$ sudo apt install phantomjs</pre>
<pre>$ ./dorkbot.py -i google -o engine=012345678901234567891:abc12defg3h,query="filetype:php inurl:id"</pre>
<pre>$ ./dorkbot.py -s arachni</pre> OR <pre>$ ./dorkbot.py -s wapiti</pre>

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

### cc_py ###
Search for targets within commoncrawl.org results via cc.py.

Requirements: [cc.py](https://github.com/si9int/cc.py)

Options:
* **domain** - pull all results for given domain or subdomain
* cc_py_dir - cc.py base directory containing the file cc.py (default: tools/cc.py/)
* year - limit results to data sets from given year (17 or 18, defaults to all)

### stdin ###
Read targets from standard input, one per line.

Requirements: none

Options: none

Scanner Modules
===============
### (general options) ###
These options are applicable regardless of module chosen

* blacklist - file containing (regex) patterns to blacklist from scans (default: config/blacklist.txt)
* report_dir - directory to save vulnerability report (default: reports/)
* log - log file to append scan activity (default: prints to stdout)
* label - friendly name field to include in vulnerability report
* count - number of urls to scan, or -1 to scan all urls (default: -1)
* random - scan urls in random order

### arachni ###
Scan targets with Arachni command-line scanner.

Requirements: [Arachni](http://www.arachni-scanner.com/)

Options:
* arachni_dir - arachni base directory containing bin/arachni and bin/arachni_reporter (default: tools/arachni/)
* checks - space-delimited list of vulnerability checks to perform (default: "active/\*")
* timeout - maximum scan time in hours:minutes:seconds (default: disabled)
* single-thread - set browser pool and max concurrency to one each
* throttle - maximum requests per second (default: disabled)

### wapiti ###
Scan targets with Wapiti command-line scanner.

Requirements: [Wapiti](http://wapiti.sourceforge.net/)

Options:
* wapiti_dir - wapiti base directory containing bin/wapiti (default: tools/wapiti/)
* modules - space-delimited list of modules to perform (default: "blindsql exec file permanentxss sql xss")

