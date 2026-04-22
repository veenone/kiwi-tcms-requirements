/* Captures the live-rendered Sankey SVG and POSTs it to the server
 * export endpoint when the user clicks DOCX / PDF.
 *
 * Submission flow:
 *   1. Serialise <svg id="requirements-sankey"> via XMLSerializer
 *   2. Stuff it into the hidden form's `svg` field
 *   3. Point the form's action at the right URL (docx or pdf)
 *   4. Submit — browser follows to a download response
 *
 * On failure (no SVG rendered yet), we still submit with an empty svg —
 * the server falls back to the table-only report.
 */
(function () {
    "use strict";

    var form = document.getElementById("requirements-traceability-export-form");
    var svgField = document.getElementById("requirements-export-svg");
    var docxBtn = document.getElementById("requirements-export-docx");
    var pdfBtn = document.getElementById("requirements-export-pdf");
    var svgEl = document.getElementById("requirements-sankey");
    var urls = window.REQ_TRACE_EXPORT_URLS || {};

    if (!form || !svgField || !docxBtn || !pdfBtn) { return; }

    function captureSvg() {
        if (!svgEl) { return ""; }
        try {
            // Clone so we don't mutate the live DOM.
            var clone = svgEl.cloneNode(true);
            // svglib requires an explicit namespace on the root.
            clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
            clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
            var serializer = new XMLSerializer();
            return '<?xml version="1.0" encoding="UTF-8"?>\n' +
                   serializer.serializeToString(clone);
        } catch (err) {
            return "";
        }
    }

    function submit(url) {
        if (!url) { return; }
        svgField.value = captureSvg();
        form.action = url;
        form.submit();
    }

    docxBtn.addEventListener("click", function () { submit(urls.docx); });
    pdfBtn.addEventListener("click", function () { submit(urls.pdf); });
})();
