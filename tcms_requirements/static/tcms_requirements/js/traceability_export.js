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
 *
 * Diagnostics: every step logs to the browser console with the
 * `[tcms-req-export]` prefix so silent failures are easy to spot in
 * DevTools. If the click doesn't even produce a log line, the script
 * isn't being served — run `./manage.py collectstatic` or check the
 * Network tab for a 404 on this file.
 */
(function () {
    "use strict";

    var TAG = "[tcms-req-export]";
    console.log(TAG, "script loaded");

    var form = document.getElementById("requirements-traceability-export-form");
    var svgField = document.getElementById("requirements-export-svg");
    var docxBtn = document.getElementById("requirements-export-docx");
    var pdfBtn = document.getElementById("requirements-export-pdf");
    var svgEl = document.getElementById("requirements-sankey");
    var urls = window.REQ_TRACE_EXPORT_URLS || {};

    var missing = [];
    if (!form) { missing.push("form#requirements-traceability-export-form"); }
    if (!svgField) { missing.push("input#requirements-export-svg"); }
    if (!docxBtn) { missing.push("button#requirements-export-docx"); }
    if (!pdfBtn) { missing.push("button#requirements-export-pdf"); }
    if (!urls.docx || !urls.pdf) { missing.push("window.REQ_TRACE_EXPORT_URLS"); }

    if (missing.length) {
        console.error(TAG, "missing required elements:", missing);
        if (docxBtn) {
            docxBtn.title = "Export wiring incomplete — see browser console.";
        }
        if (pdfBtn) {
            pdfBtn.title = "Export wiring incomplete — see browser console.";
        }
        return;
    }
    console.log(TAG, "wired", { docx: urls.docx, pdf: urls.pdf, hasSvg: !!svgEl });

    function captureSvg() {
        if (!svgEl) {
            console.warn(TAG, "no live SVG — submitting empty (server falls back to table-only).");
            return "";
        }
        try {
            var clone = svgEl.cloneNode(true);
            clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
            clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
            // Make sure width/height are set so svglib has dimensions.
            if (!clone.getAttribute("width")) {
                clone.setAttribute("width", svgEl.clientWidth || 1200);
            }
            if (!clone.getAttribute("height")) {
                clone.setAttribute("height", svgEl.clientHeight || 600);
            }
            var serializer = new XMLSerializer();
            var serialized = '<?xml version="1.0" encoding="UTF-8"?>\n' +
                             serializer.serializeToString(clone);
            console.log(TAG, "captured SVG: " + serialized.length + " bytes");
            return serialized;
        } catch (err) {
            console.error(TAG, "SVG capture failed:", err);
            return "";
        }
    }

    function submit(url, label) {
        if (!url) {
            console.error(TAG, "no URL configured for", label);
            return;
        }
        console.log(TAG, "submitting", label, "to", url);
        svgField.value = captureSvg();
        form.action = url;
        try {
            form.submit();
        } catch (err) {
            console.error(TAG, "form.submit() raised:", err);
            alert(
                "Export request couldn't be sent. Open the browser console for details."
            );
        }
    }

    docxBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        submit(urls.docx, "DOCX");
    });
    pdfBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        submit(urls.pdf, "PDF");
    });
})();
