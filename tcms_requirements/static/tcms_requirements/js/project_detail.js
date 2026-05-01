/* Bootstraps the project detail page:
 *   1. Renders the project-scoped Sankey using the shared renderer.
 *   2. Wires the "Export with Sankey" DOCX/PDF dropdown items.
 *
 * Config is read from data-* attributes on `#requirements-project-detail`
 * because Kiwi's CSP forbids inline <script>. Required attributes:
 *   data-export-docx-url  — URL for the DOCX export endpoint
 *   data-export-pdf-url   — URL for the PDF export endpoint
 */
(function () {
    "use strict";

    function bootstrap() {
        var root = document.getElementById("requirements-project-detail");
        if (!root || !window.tcmsRequirements) { return; }

        window.tcmsRequirements.renderSankey({
            dataElementId: "project-sankey-payload",
            svgElementId: "project-sankey",
            statusElementId: "project-sankey-status",
            legendElementId: "project-sankey-legend"
        });

        var docxUrl = root.getAttribute("data-export-docx-url");
        var pdfUrl = root.getAttribute("data-export-pdf-url");
        if (!docxUrl && !pdfUrl) { return; }

        window.tcmsRequirements.wireSankeyExport({
            formId: "project-export-form",
            svgFieldId: "project-export-svg",
            docxBtnId: "project-export-docx-with-sankey",
            pdfBtnId: "project-export-pdf-with-sankey",
            svgId: "project-sankey",
            urls: { docx: docxUrl, pdf: pdfUrl }
        });
    }

    if (document.readyState !== "loading") { bootstrap(); }
    else { document.addEventListener("DOMContentLoaded", bootstrap); }
})();
