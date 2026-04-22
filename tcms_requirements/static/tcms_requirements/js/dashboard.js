/* Renders dashboard charts from the embedded JSON snapshot.
 * C3.js donut + bar charts keyed off dashboard_snapshot() from metrics.py.
 */
(function () {
    "use strict";

    var dataNode = document.getElementById("requirements-dashboard-data");
    if (!dataNode || typeof c3 === "undefined") { return; }

    var snapshot;
    try {
        snapshot = JSON.parse(dataNode.textContent || "{}");
    } catch (err) {
        return;
    }

    function titleCase(s) {
        if (!s) { return "—"; }
        return String(s).replace(/_/g, " ").replace(/\b\w/g, function (ch) { return ch.toUpperCase(); });
    }

    function donut(elementId, rows, labelKey) {
        if (!rows || !rows.length) {
            placeholder(elementId);
            return;
        }
        var columns = rows.map(function (r) {
            return [titleCase(r[labelKey]), r.count];
        });
        c3.generate({
            bindto: elementId,
            data: {
                columns: columns,
                type: "donut"
            },
            donut: {
                title: "",
                label: { format: function (value) { return value; } }
            },
            legend: { position: "right" }
        });
    }

    function bar(elementId, rows, labelKey) {
        if (!rows || !rows.length) {
            placeholder(elementId);
            return;
        }
        var categories = rows.map(function (r) { return titleCase(r[labelKey]); });
        var values = rows.map(function (r) { return r.count; });
        c3.generate({
            bindto: elementId,
            data: {
                columns: [["Requirements"].concat(values)],
                type: "bar"
            },
            axis: {
                x: { type: "category", categories: categories }
            },
            legend: { show: false },
            color: { pattern: ["#39a5dc"] }
        });
    }

    function placeholder(elementId) {
        var el = document.querySelector(elementId);
        if (!el) { return; }
        while (el.firstChild) { el.removeChild(el.firstChild); }
        var small = document.createElement("small");
        small.className = "text-muted";
        small.textContent = "No data";
        el.appendChild(small);
    }

    donut("#chart-by-status", snapshot.by_status, "status");
    donut("#chart-by-priority", snapshot.by_priority, "priority");
    bar("#chart-by-level", snapshot.by_level, "name");
    bar("#chart-by-category", snapshot.by_category, "category");

    // Safety chart: combine ASIL/DAL/IEC62304 into a grouped bar if any present.
    var safety = snapshot.safety || {};
    var safetyRows = [];
    ["asil", "dal", "iec62304_class"].forEach(function (key) {
        var bucket = safety[key] || {};
        Object.keys(bucket).sort().forEach(function (code) {
            safetyRows.push({
                label: key.toUpperCase().replace("_CLASS", "") + " " + code,
                count: bucket[code]
            });
        });
    });
    if (safetyRows.length) {
        bar("#chart-safety", safetyRows, "label");
    }
})();
