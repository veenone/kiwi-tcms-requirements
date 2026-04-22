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

    var kindColour = {
        requirement: "#39a5dc",
        case: "#ec7a08",
        plan: "#3f9c35"
    };

    svg.append("g")
        .attr("fill", "none")
        .attr("stroke-opacity", 0.35)
        .selectAll("path")
        .data(graph.links)
        .join("path")
        .attr("d", d3.sankeyLinkHorizontal())
        .attr("stroke", function (d) {
            if (d.suspect) { return "#cc0000"; }
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
        .attr("fill", function (d) { return kindColour[d.kind] || "#888"; })
        .append("title")
        .text(function (d) { return d.name + " (" + d.value + ")"; });

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
