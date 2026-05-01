/* Renders the Sankey traceability diagram.
 * Reads the payload from the <script id="requirements-sankey-data"> tag,
 * sizes to the container width, and colours by node kind.
 */
(function () {
    "use strict";

    var dataNode = document.getElementById("requirements-sankey-data");
    if (!dataNode) { return; }

    var payload;
    try {
        payload = JSON.parse(dataNode.textContent || "{}");
    } catch (err) {
        payload = { nodes: [], links: [] };
    }

    var status = document.getElementById("requirements-sankey-status");
    var svgNode = document.getElementById("requirements-sankey");
    if (!svgNode) { return; }

    function setStatus(text) {
        if (!status) { return; }
        while (status.firstChild) { status.removeChild(status.firstChild); }
        var em = document.createElement("em");
        em.textContent = text;
        status.appendChild(em);
    }

    if (!payload.nodes || !payload.nodes.length) {
        setStatus(
            "No traceability links match the current filters. " +
            "Link at least one test case to a requirement to populate the diagram."
        );
        return;
    }

    if (payload.truncated) {
        setStatus(
            "Diagram truncated to the most-connected nodes. " +
            "Narrow filters to see the full graph."
        );
    }

    var width = Math.max(720, svgNode.parentNode.clientWidth || 960);
    var height = Math.max(480, Math.min(payload.nodes.length * 18 + 60, 1600));

    var svg = d3.select(svgNode)
        .attr("width", width)
        .attr("height", height)
        .attr("viewBox", "0 0 " + width + " " + height)
        .style("font", "11px sans-serif");

    svg.selectAll("*").remove();

    var sankeyLayout = d3.sankey()
        .nodeWidth(18)
        .nodePadding(12)
        .extent([[10, 10], [width - 10, height - 10]]);

    var graph = sankeyLayout({
        nodes: payload.nodes.map(function (d) { return Object.assign({}, d); }),
        links: payload.links.map(function (d) { return Object.assign({}, d); })
    });

    // Node palette. Extended across every Sankey view:
    //   blue = requirement, orange = case, green = plan,
    //   purple = bug (grey when closed), gold = feature,
    //   teal = source document,
    //   status_* = verification-status nodes (green / red / orange / grey).
    var kindColour = {
        requirement: "#39a5dc",
        case: "#ec7a08",
        plan: "#3f9c35",
        bug: "#9c27b0",
        feature: "#f0ad4e",
        document: "#008b8b",
        status_passed: "#3f9c35",
        status_failed: "#cc0000",
        status_blocked: "#ec7a08",
        status_untested: "#9c9c9c",
        status_idle: "#bcbcbc"
    };

    var kindLabel = {
        requirement: "Requirement",
        case: "Test case",
        plan: "Test plan",
        bug: "Bug (open)",
        feature: "Feature",
        document: "Source document",
        status_passed: "Passed",
        status_failed: "Failed",
        status_blocked: "Blocked",
        status_untested: "Untested",
        status_idle: "Idle"
    };

    function nodeFill(d) {
        if (d.kind === "bug" && d.is_open === false) {
            return "#888";
        }
        return kindColour[d.kind] || "#888";
    }

    renderLegend(payload.nodes);

    function renderLegend(nodes) {
        var host = document.getElementById("requirements-sankey-legend");
        if (!host) { return; }
        host.innerHTML = "";

        var seen = {};
        var hasClosedBug = false;
        nodes.forEach(function (n) {
            var key = n.kind;
            if (n.kind === "bug" && n.is_open === false) {
                hasClosedBug = true;
                return;
            }
            seen[key] = true;
        });

        Object.keys(seen).forEach(function (kind) {
            var item = document.createElement("span");
            item.className = "sankey-legend-item";
            var swatch = document.createElement("span");
            swatch.className = "sankey-legend-swatch";
            swatch.style.background = kindColour[kind] || "#888";
            var label = document.createElement("span");
            label.textContent = kindLabel[kind] || kind;
            item.appendChild(swatch);
            item.appendChild(label);
            host.appendChild(item);
        });

        if (hasClosedBug) {
            var closed = document.createElement("span");
            closed.className = "sankey-legend-item";
            var sw = document.createElement("span");
            sw.className = "sankey-legend-swatch";
            sw.style.background = "#888";
            var lbl = document.createElement("span");
            lbl.textContent = "Bug (closed)";
            closed.appendChild(sw);
            closed.appendChild(lbl);
            host.appendChild(closed);
        }

        // Suspect-link indicator is a stroke colour, not a node kind, so
        // only surface it when at least one suspect link is present.
        var suspect = (payload.links || []).some(function (l) { return l.suspect; });
        if (suspect) {
            var item = document.createElement("span");
            item.className = "sankey-legend-item";
            var sw2 = document.createElement("span");
            sw2.className = "sankey-legend-swatch sankey-legend-swatch-line";
            sw2.style.background = "#cc0000";
            var lbl2 = document.createElement("span");
            lbl2.textContent = "Suspect link";
            item.appendChild(sw2);
            item.appendChild(lbl2);
            host.appendChild(item);
        }
    }

    svg.append("g")
        .attr("fill", "none")
        .attr("stroke-opacity", 0.35)
        .selectAll("path")
        .data(graph.links)
        .join("path")
        .attr("d", d3.sankeyLinkHorizontal())
        .attr("stroke", function (d) {
            if (d.suspect) { return "#cc0000"; }
            if (d.link_type === "has_bug") {
                return d.bug_open === false ? "#b0b0b0" : "#c890d9";
            }
            return "#9cc2dc";
        })
        .attr("stroke-width", function (d) { return Math.max(1, d.width); });

    var node = svg.append("g")
        .selectAll("g")
        .data(graph.nodes)
        .join("g");

    node.append("rect")
        .attr("x", function (d) { return d.x0; })
        .attr("y", function (d) { return d.y0; })
        .attr("width", function (d) { return d.x1 - d.x0; })
        .attr("height", function (d) { return Math.max(1, d.y1 - d.y0); })
        .attr("fill", nodeFill)
        .append("title")
        .text(function (d) {
            var suffix = "";
            if (d.kind === "bug") {
                suffix = d.is_open === false ? " [closed]" : " [open]";
            }
            return d.name + suffix + " (" + d.value + ")";
        });

    node.append("text")
        .attr("x", function (d) { return d.x0 < width / 2 ? d.x1 + 6 : d.x0 - 6; })
        .attr("y", function (d) { return (d.y1 + d.y0) / 2; })
        .attr("dy", "0.35em")
        .attr("text-anchor", function (d) { return d.x0 < width / 2 ? "start" : "end"; })
        .text(function (d) {
            var label = d.name || "";
            return label.length > 60 ? label.slice(0, 57) + "…" : label;
        })
        .append("title")
        .text(function (d) { return d.name; });
})();
