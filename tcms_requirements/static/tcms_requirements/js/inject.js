/* kiwitcms-requirements injected bundle.
 *
 * Loaded into every HTML response by the InjectRequirementsBundleMiddleware.
 * Detects the page via body[id], renders the "Requirements" card on
 * TestCase detail pages, and no-ops everywhere else.
 *
 * Reminder: Kiwi ships TWO jQuery instances — `$` (3.6.1, has Bootstrap
 * plugins) and `jQuery` (3.6.0, no plugins). Use `$` and close IIFEs with
 * `})($)` so modal / dropdown events fire correctly.
 */
(function ($) {
    "use strict";

    // Bail early if jQuery isn't available (shouldn't happen on Kiwi pages
    // but makes the script resilient if loaded elsewhere).
    if (typeof $ === "undefined") {
        return;
    }

    const SCRIPT_TAG = document.querySelector('script[data-source="tcms_requirements"]');
    if (SCRIPT_TAG && SCRIPT_TAG.dataset.injected === "true") {
        return;
    }
    if (SCRIPT_TAG) {
        SCRIPT_TAG.dataset.injected = "true";
    }

    $(function () {
        const $body = $("body");
        const bodyId = $body.attr("id") || "";

        if (bodyId === "testcases-get") {
            injectTestCaseRequirementsCard();
        }
    });

    function currentCaseId() {
        // Kiwi embeds the case id in several places; the cheapest read is
        // the URL — /case/<pk>/
        const match = window.location.pathname.match(/\/case\/(\d+)/);
        return match ? parseInt(match[1], 10) : null;
    }

    function injectTestCaseRequirementsCard() {
        const caseId = currentCaseId();
        if (!caseId) {
            return;
        }

        const $target = $("#info_box, .case-info, .container-fluid").first();
        if (!$target.length) {
            return;
        }

        const $card = $(
            '<div class="tcmsreq-injected-card">' +
            '  <h3>Requirements</h3>' +
            '  <div class="tcmsreq-link-body"><em>Loading…</em></div>' +
            '</div>'
        );
        $target.after($card);

        fetchLinks(caseId).then(function (links) {
            renderLinks($card.find(".tcmsreq-link-body"), links);
        }).catch(function () {
            $card.find(".tcmsreq-link-body").html(
                '<small class="text-muted">Failed to load requirements.</small>'
            );
        });
    }

    function fetchLinks(caseId) {
        // We call the same JSON-RPC the rest of Kiwi uses. For v0.1 we expose
        // a lightweight `Requirement.filter({cases: caseId})` (see tcms_requirements/rpc.py).
        return new Promise(function (resolve, reject) {
            if (typeof jsonRPC !== "function") {
                // Kiwi's JSON-RPC helper isn't present on this page. Quietly
                // degrade — the card stays empty.
                resolve([]);
                return;
            }
            jsonRPC("Requirement.filter", { cases: caseId }, function (data) {
                resolve(data || []);
            }, function () {
                reject();
            });
        });
    }

    function renderLinks($body, links) {
        if (!links || !links.length) {
            $body.html(
                '<small class="text-muted">No linked requirements. ' +
                'Add one from the requirement detail page.</small>'
            );
            return;
        }
        const $list = $('<ul class="tcmsreq-link-list"></ul>');
        links.forEach(function (req) {
            const href = "/requirements/" + encodeURIComponent(req.id) + "/";
            const identifier = escapeHtml(req.identifier || "?");
            const title = escapeHtml(req.title || "");
            const linkType = escapeHtml(req.link_type || "");
            let html =
                '<li>' +
                '<a href="' + href + '"><code>' + identifier + '</code></a> ' +
                '<span class="text-muted">— ' + title + '</span> ' +
                '<small class="text-muted">[' + linkType + ']</small>';
            if (req.suspect) {
                html += ' <span class="tcmsreq-suspect">⚠ suspect</span>';
            }
            html += "</li>";
            $list.append(html);
        });
        $body.empty().append($list);
    }

    function escapeHtml(text) {
        return String(text || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }
})($);
