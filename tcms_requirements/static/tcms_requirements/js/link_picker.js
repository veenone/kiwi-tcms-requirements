/* TestCase browser for the requirement link form.
 *
 * Search box feeds into Kiwi's native jsonRPC("TestCase.filter", ...)
 * with a debounce. Results render as rows; clicking picks the case.
 *
 * Depends on Kiwi's globally-loaded `jsonRPC` helper. Falls back to a
 * manual numeric input if it isn't present (e.g. standalone testing).
 */
(function ($) {
    "use strict";

    var query = document.getElementById("link-picker-query");
    var results = document.getElementById("link-picker-results");
    var selected = document.getElementById("link-picker-selected");
    var hiddenId = document.getElementById("id_case_id");
    var submitBtn = document.getElementById("link-submit");

    if (!query || !results || !selected || !hiddenId || !submitBtn) { return; }

    function clearChildren(node) {
        while (node && node.firstChild) { node.removeChild(node.firstChild); }
    }

    // If Kiwi's jsonRPC helper isn't on the page, surface a manual id
    // entry box so the form still works.
    if (typeof jsonRPC !== "function") {
        var wrap = query.parentNode;
        clearChildren(wrap);
        var fallback = document.createElement("input");
        fallback.type = "number";
        fallback.min = "1";
        fallback.className = "form-control";
        fallback.placeholder = "Enter TestCase id (e.g. 42)";
        fallback.addEventListener("input", function () {
            var val = parseInt(fallback.value, 10);
            if (val > 0) {
                pickCase({ id: val, summary: "TC-" + val, author__username: "" });
            }
        });
        wrap.appendChild(fallback);
        return;
    }

    var debounceTimer = null;

    query.addEventListener("input", function () {
        if (debounceTimer) { clearTimeout(debounceTimer); }
        debounceTimer = setTimeout(search, 250);
    });

    // Initial load — show the most recent 50.
    search();

    function search() {
        var raw = (query.value || "").trim();
        var rpcQuery = {};
        if (raw) {
            if (/^\d+$/.test(raw)) {
                rpcQuery.pk = parseInt(raw, 10);
            } else {
                rpcQuery.summary__icontains = raw;
            }
        }
        renderLoading();
        jsonRPC("TestCase.filter", rpcQuery, function (rows) {
            renderResults(rows || []);
        }, function () {
            renderError();
        });
    }

    function renderLoading() {
        clearChildren(results);
        var p = document.createElement("p");
        p.className = "text-muted";
        var em = document.createElement("em");
        em.textContent = "Searching...";
        p.appendChild(em);
        results.appendChild(p);
    }

    function renderError() {
        clearChildren(results);
        var p = document.createElement("p");
        p.className = "text-danger";
        p.textContent = "TestCase search failed. Check the server log.";
        results.appendChild(p);
    }

    function renderResults(rows) {
        clearChildren(results);
        if (!rows.length) {
            var none = document.createElement("p");
            none.className = "text-muted";
            var em = document.createElement("em");
            em.textContent = "No test cases match.";
            none.appendChild(em);
            results.appendChild(none);
            return;
        }
        var slice = rows.slice(0, 50);
        var table = document.createElement("table");
        table.className = "table table-condensed table-hover link-picker-table";

        var thead = document.createElement("thead");
        var tr = document.createElement("tr");
        ["ID", "Summary", "Author", "Automated"].forEach(function (h) {
            var th = document.createElement("th");
            th.textContent = h;
            tr.appendChild(th);
        });
        thead.appendChild(tr);
        table.appendChild(thead);

        var tbody = document.createElement("tbody");
        slice.forEach(function (row) {
            var tr2 = document.createElement("tr");
            tr2.style.cursor = "pointer";
            tr2.addEventListener("click", function () { pickCase(row); });
            appendCell(tr2, "TC-" + row.id);
            appendCell(tr2, row.summary || "—");
            appendCell(tr2, row.author__username || row.author_username || "—");
            appendCell(tr2, row.is_automated ? "automated" : "manual");
            tbody.appendChild(tr2);
        });
        table.appendChild(tbody);
        results.appendChild(table);
    }

    function pickCase(row) {
        hiddenId.value = row.id;
        clearChildren(selected);

        var strong = document.createElement("strong");
        strong.textContent = "TC-" + row.id;
        selected.appendChild(strong);
        selected.appendChild(document.createTextNode(" " + (row.summary || "")));

        if (row.author__username || row.author_username) {
            var small = document.createElement("div");
            small.className = "text-muted";
            small.textContent = "author: " + (row.author__username || row.author_username);
            selected.appendChild(small);
        }
        submitBtn.disabled = false;
    }

    function appendCell(tr, text) {
        var td = document.createElement("td");
        td.textContent = text == null ? "" : text;
        tr.appendChild(td);
    }
})(typeof $ !== "undefined" ? $ : null);
