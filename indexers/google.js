var system = require('system');
var engine = system.args[1];
var query = system.args[2];
var site = system.args[3];
var sitesearch = site ? ' as_sitesearch="' + site + '"' : '';
var address = 'http://localhost/?q=' + query;
var html = '' + 
    '<html>' + 
    '<head>' +
    '<title>search</title>' +
    '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />' +
    '<script>' +
    '(function() {' +
    '   var cx = "' + engine + '";' +
    '   var gcse = document.createElement("script");' +
    '   gcse.type = "text/javascript";' +
    '   gcse.async = true;' +
    '   gcse.src = "https://cse.google.com/cse.js?cx=" + cx;' +
    '   var s = document.getElementsByTagName("script")[0];' +
    '   s.parentNode.insertBefore(gcse, s);' +
    '})();' +
    '</script>' +
    '</head>' +
    '<body>' +
    '<gcse:search' + sitesearch + '></gcse:search>' +
    '</script>' +
    '</body>' +
    '</html>' +
'';

var page = require('webpage').create();
page.setContent(html, address);
page.onConsoleMessage = function(msg) { console.log(msg); }
page.onError = function(msg) {
    //console.log('Error: ' + msg);
    phantom.exit();
}
//page.onLoadFinished = function() { page.evaluate(getResults); }

function getResults() {
  var previousPage = 0;
  var intervalId = setInterval(function() {
    function getNumPages() {
        var gsc_cursor_page = document.getElementsByClassName('gsc-cursor-page');
        var numPages = gsc_cursor_page.length;
        return numPages;
    }

    function getCurrentPage() {
        var gsc_cursor_current_page = document.getElementsByClassName('gsc-cursor-current-page');
        var currentPage = parseInt(gsc_cursor_current_page[0].innerHTML);
        return currentPage;
    }

    function goToPage(pageNum) {
        previousPage = pageNum - 1;
        var gsc_cursor_page = document.getElementsByClassName('gsc-cursor-page');
        var targetPage = gsc_cursor_page[pageNum-1];
//        try {
            targetPage.click();
//        } catch (e) {
//            console.log('Could not click: ' + e.message);
//            throw(e);
//        }
    }

    function printLinks() {
        var gs_title = document.getElementsByClassName('gs-title');
        for (var link = 0; link+5 < gs_title.length; link++) {
            if (gs_title[link].tagName === 'A') {
                console.log(gs_title[link].href);
                link+=2;
            }
        }
    }

    var pageTimeout = 10000;

    function loadPage(isPageLoaded, beginPrintLinks) {
        var loaded = false;
        var start = new Date().getTime();
        var id = setInterval(function() {
	    if (new Date().getTime() - start > pageTimeout && loaded == false) {
	        clearInterval(id);
	        throw "page timeout";
	    }
            else if (loaded == true) {
                clearInterval(id);
                beginPrintLinks();
            }
            else {
                loaded = isPageLoaded();
            }
        }, 100);
    }

    loadPage(function() {
        return ( function() {
            var currentPage = getCurrentPage();
            return currentPage != previousPage;

        } ) ();
    }, function() {
        var numPages = getNumPages();
        var currentPage = getCurrentPage();

        if (currentPage > numPages) {
            console.log('No more pages..');
            clearInterval(intervalId);
            phantom.exit();
            return;
        }
        else if (currentPage != previousPage) {
            //console.log('Page ' + currentPage + ' of ' + numPages);
            printLinks();
        }

        goToPage(currentPage+1);
    });
  }, 100);
}

var searchTimeout = 15000;

function loadSearch(isSearchLoaded, beginReadResults) {
    var loaded = false;
    var start = new Date().getTime();
    var id = setInterval(function() {
        if (new Date().getTime() - start > searchTimeout && loaded == false) {
            clearInterval(id);
            page.evaluate(function () { throw "search timeout"; });
        }
        else if (loaded == true) {
            clearInterval(id);
            beginReadResults();
        }
        else {
            loaded = isSearchLoaded();
        }
    }, 100);
}

loadSearch(function() {
    return page.evaluate(function() {
        var currentPage = document.getElementsByClassName('gsc-cursor-current-page');
        return currentPage.length != 0;

        });
    }, function() {
        page.evaluate(getResults);
});

/*
page.onLoadFinished = function() {
  setTimeout(function() {
    console.log('test');
    page.render('page.png');
  }, 2000);
}
*/

