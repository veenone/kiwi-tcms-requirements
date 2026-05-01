/* Renders a Sankey traceability diagram into a target <svg>.
 *
 * Public API:
 *   window.tcmsRequirements.renderSankey({
 *     dataElementId:   "requirements-sankey-data",      // <script type="application/json">
 *     svgElementId:    "requirements-sankey",           // <svg>
 *     statusElementId: "requirements-sankey-status",    // optional <div> for empty/truncated msg
 *     legendElementId: "requirements-sankey-legend"     // optional <div> for the colour legend
 *   });
 *
 * Auto-bootstraps for the legacy traceability-page IDs at load time so
 * existing pages keep working with no template changes.
 */
(function () {
    "use strict";

    // Shared palette + labels — used by both the diagram fill and the legend.
    var KIND_COLOUR = {
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

    var KIND_LABEL = {
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

    function renderSankey(opts) {
        opts = opts || {};
        var dataNode = document.getElementById(opts.dataElementId);
        var svgNode = document.getElementById(opts.svgElementId);
        if (!dataNode || !svgNode) { return; }

        var statusNode = opts.statusElementId
            ? document.getElementById(opts.statusElementId) : null;
        var legendNode = opts.legendElementId
            ? document.getElementById(opts.legendElementId) : null;

        var payload;
        try {
            payload = JSON.parse(dataNode.textContent || "{}");
        } catch (err) {
            payload = { nodes: [], links: [] };
        }

        function setStatus(text) {
            if (!statusNode) { return; }
            while (statusNode.firstChild) { statusNode.removeChild(statusNode.firstChild); }
            var em = document.createElement("em");
            em.textContent = text;
            statusNode.appendChild(em);
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
        var height = Math.max(360, Math.min(payload.nodes.length * 18 + 60, 1600));

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

        function nodeFill(d) {
            if (d.kind === "bug" && d.is_open === false) {
                return "#888";
            }
            return KIND_COLOUR[d.kind] || "#888";
        }

        renderLegend(payload, legendNode);

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
    }

    function renderLegend(payload, host) {
        if (!host) { return; }
        host.innerHTML = "";

        var seen = {};
        var hasClosedBug = false;
        (payload.nodes || []).forEach(function (n) {
            if (n.kind === "bug" && n.is_open === false) {
                hasClosedBug = true;
                return;
            }
            seen[n.kind] = true;
        });

        Object.keys(seen).forEach(function (kind) {
            host.appendChild(makeLegendItem(KIND_COLOUR[kind] || "#888", KIND_LABEL[kind] || kind));
        });
        if (hasClosedBug) {
            host.appendChild(makeLegendItem("#888", "Bug (closed)"));
        }
        var suspect = (payload.links || []).some(function (l) { return l.suspect; });
        if (suspect) {
            host.appendChild(makeLegendItem("#cc0000", "Suspect link", true));
        }
    }

    function makeLegendItem(colour, label, isLine) {
        var item = document.createElement("span");
        item.className = "sankey-legend-item";
        var swatch = document.createElement("span");
        swatch.className = "sankey-legend-swatch" + (isLine ? " sankey-legend-swatch-line" : "");
        swatch.style.background = colour;
        var text = document.createElement("span");
        text.textContent = label;
        item.appendChild(swatch);
        item.appendChild(text);
        return item;
    }

    // Public API.
    window.tcmsRequirements = window.tcmsRequirements || {};
    window.tcmsRequirements.renderSankey = renderSankey;

    // Auto-bootstrap for the legacy traceability page IDs.
    document.addEventListener("DOMContentLoaded", function () {
        renderSankey({
            dataElementId: "requirements-sankey-data",
            svgElementId: "requirements-sankey",
            statusElementId: "requirements-sankey-status",
            legendElementId: "requirements-sankey-legend"
        });
    });

    // Also try to bootstrap immediately in case the script loads after
    // DOMContentLoaded (defer/end-of-body include).
    if (document.readyState !== "loading") {
        renderSankey({
            dataElementId: "requirements-sankey-data",
            svgElementId: "requirements-sankey",
            statusElementId: "requirements-sankey-status",
            legendElementId: "requirements-sankey-legend"
        });
    }
})();
