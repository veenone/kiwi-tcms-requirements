/* TestCase browser for the requirement link form.
 *
 * Kiwi's jsonRPC helper is an ES-module export (bundle-internal), so it
 * isn't available as a global from outside the bundle. We POST directly
 * to /json-rpc/ ourselves — same wire format, no dependency on Kiwi's
 * internals being exposed.
 *
 * UX:
 *   - Search box with 250ms debounce
 *   - Numeric query → TestCase.filter({pk: N})
 *   - Text query → TestCase.filter({summary__icontains: ...})
 *   - Empty query → 50 most-recent cases
 *   - Row click → picks the case; reveals "Link" submit button
 */
(function () {
    "use strict";

    var query = document.getElementById("link-picker-query");
    var results = document.getElementById("link-picker-results");
    var selected = document.getElementById("link-picker-selected");
    var hiddenId = document.getElementById("id_case_id");
    var submitBtn = document.getElementById("link-submit");

    if (!query || !results || !selected || !hiddenId || !submitBtn) { return; }

    var debounceTimer = null;

    query.addEventListener("input", function () {
        if (debounceTimer) { clearTimeout(debounceTimer); }
        debounceTimer = setTimeout(search, 250);
    });

    // Initial load — show the most recent 50.
    search();

    function clearChildren(node) {
        while (node && node.firstChild) { node.removeChild(node.firstChild); }
    }

    function csrfToken() {
        var name = "csrftoken=";
        var parts = (document.cookie || "").split("; ");
        for (var i = 0; i < parts.length; i++) {
            if (parts[i].indexOf(name) === 0) {
                return decodeURIComponent(parts[i].substring(name.length));
            }
        }
        return "";
    }

    function jsonRPC(method, params) {
        // `.filter()` takes a dict; normalise to a one-element list as Kiwi's
        // client does, otherwise modernrpc rejects the call.
        var rpcParams = Array.isArray(params) ? params : [params];
        var csrf = csrfToken();
        return fetch("/json-rpc/", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: method,
                params: rpcParams,
                id: "tcmsreq-link-picker"
            })
        }).then(function (resp) {
            if (!resp.ok) { throw new Error("HTTP " + resp.status); }
            return resp.json();
        }).then(function (payload) {
            if (payload.error) {
                throw new Error(payload.error.message || "JSON-RPC error");
            }
            return payload.result;
        });
    }

    function search() {
        var raw = (query.value || "").trim();
        var rpcQuery = {};
        if (raw) {
            // "TC-42" or "42" → filter by pk. Otherwise substring on summary.
            var cleaned = raw.replace(/^TC-/i, "");
            if (/^\d+$/.test(cleaned)) {
                rpcQuery.pk = parseInt(cleaned, 10);
            } else {
                rpcQuery.summary__icontains = raw;
            }
        }
        renderLoading();
        jsonRPC("TestCase.filter", rpcQuery).then(function (rows) {
            renderResults(rows || []);
        }).catch(function (err) {
            renderError(err && err.message ? err.message : "request failed");
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

    function renderError(message) {
        clearChildren(results);
        var p = document.createElement("p");
        p.className = "text-danger";
        p.textContent = "TestCase search failed: " + message;
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
        var headerRow = document.createElement("tr");
        ["ID", "Summary", "Author", "Automated"].forEach(function (h) {
            var th = document.createElement("th");
            th.textContent = h;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        var tbody = document.createElement("tbody");
        slice.forEach(function (row) {
            var tr = document.createElement("tr");
            tr.style.cursor = "pointer";
            tr.addEventListener("click", function () { pickCase(row); });
            appendCell(tr, "TC-" + row.id);
            appendCell(tr, row.summary || "—");
            appendCell(tr, row.author__username || row.author_username || "—");
            appendCell(tr, row.is_automated ? "automated" : "manual");
            tbody.appendChild(tr);
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
            var meta = document.createElement("div");
            meta.className = "text-muted";
            meta.textContent = "author: " + (row.author__username || row.author_username);
            selected.appendChild(meta);
        }
        submitBtn.disabled = false;
    }

    function appendCell(tr, text) {
        var td = document.createElement("td");
        td.textContent = text == null ? "" : text;
        tr.appendChild(td);
    }
})();
