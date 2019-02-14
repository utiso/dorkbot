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
page.onError = function(msg) { console.log(msg); }

function getNumPages() {
   return page.evaluate(function() {
        return document.getElementsByClassName('gsc-cursor-page').length;
    });
}

function getCurrentPage() {
    return page.evaluate(function() {
        var page = document.getElementsByClassName('gsc-cursor-current-page');
        if (page.length == 0) { return -1; }
        else { return parseInt(page[0].innerHTML); }
    });
}

function hasResults() {
    return page.evaluate(function() {
        var results = document.getElementsByClassName('gsc-webResult');
        if (results.length == 2 && results[1].innerText == 'No Results\n') { return false; }
        else { return true; }
    });
}

function printLinks() {
    page.evaluate(function() {
        var results = document.getElementsByClassName('gsc-webResult');
        for (var i = 1; i < results.length; i++) {
            result = results[i].getElementsByTagName('a');
            console.log(result[0]);
        }
    });
}

function goToPage(desiredPage) {
    var pageTimeout = 10000;
    var start = new Date().getTime();
    var id = setInterval(function() {
        if (new Date().getTime() - start > pageTimeout) {
            console.error('Timed out while waiting for results to load.');
            phantom.exit(1);
        }
        else if (hasResults() == false) { phantom.exit(0); }
        else {
            var currentPage = getCurrentPage();

            if (currentPage == desiredPage) {
                clearInterval(id);
                printLinks();
                if (desiredPage != getNumPages()) { goToPage(desiredPage + 1); }
                else { phantom.exit(0); }
            }

            else if (currentPage != -1) {
                page.evaluate(function(desiredPage) {
                    var pages = document.getElementsByClassName('gsc-cursor-page');
                    var pageToClick = pages[desiredPage - 1];
                    pageToClick.click();
                }, desiredPage);
            }
        }
    }, 50);
}

goToPage(1);

