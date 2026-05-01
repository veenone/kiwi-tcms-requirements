/* Captures a live-rendered Sankey SVG and POSTs it to a server export
 * endpoint (DOCX or PDF) on user click.
 *
 * Public API:
 *   window.tcmsRequirements.wireSankeyExport({
 *     formId:      "requirements-traceability-export-form",
 *     svgFieldId:  "requirements-export-svg",
 *     docxBtnId:   "requirements-export-docx",
 *     pdfBtnId:    "requirements-export-pdf",
 *     svgId:       "requirements-sankey",
 *     urls:        { docx: "...", pdf: "..." }
 *   });
 *
 * Auto-bootstraps for the legacy traceability-page IDs at load time using
 * window.REQ_TRACE_EXPORT_URLS so existing pages keep working.
 *
 * Diagnostics: every step logs to the browser console with the
 * `[tcms-req-export]` prefix.
 */
(function () {
    "use strict";

    var TAG = "[tcms-req-export]";

    function wireSankeyExport(opts) {
        opts = opts || {};
        var form = document.getElementById(opts.formId);
        var svgField = document.getElementById(opts.svgFieldId);
        var docxBtn = opts.docxBtnId ? document.getElementById(opts.docxBtnId) : null;
        var pdfBtn = opts.pdfBtnId ? document.getElementById(opts.pdfBtnId) : null;
        var svgEl = document.getElementById(opts.svgId);
        var urls = opts.urls || {};

        // Without the form scaffold, this page just doesn't have export
        // wiring. Don't error — the auto-bootstrap calls this on every
        // page that loads the script.
        if (!form || !svgField) { return false; }

        var missing = [];
        if (!docxBtn && !pdfBtn) { missing.push("at least one of docxBtnId / pdfBtnId"); }
        if (!urls.docx && !urls.pdf) { missing.push("urls.docx or urls.pdf"); }
        if (missing.length) {
            console.error(TAG, "wireSankeyExport missing:", missing);
            return false;
        }

        console.log(TAG, "wired", {
            form: opts.formId, docx: urls.docx, pdf: urls.pdf, hasSvg: !!svgEl,
        });

        function captureSvg() {
            if (!svgEl) {
                console.warn(TAG, "no live SVG — submitting empty (server falls back to table-only).");
                return "";
            }
            try {
                var clone = svgEl.cloneNode(true);
                clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
                clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
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

        if (docxBtn && urls.docx) {
            docxBtn.addEventListener("click", function (ev) {
                ev.preventDefault();
                submit(urls.docx, "DOCX");
            });
        }
        if (pdfBtn && urls.pdf) {
            pdfBtn.addEventListener("click", function (ev) {
                ev.preventDefault();
                submit(urls.pdf, "PDF");
            });
        }
        return true;
    }

    // Public API.
    window.tcmsRequirements = window.tcmsRequirements || {};
    window.tcmsRequirements.wireSankeyExport = wireSankeyExport;

    // Auto-bootstrap for the legacy traceability-page IDs, which set
    // window.REQ_TRACE_EXPORT_URLS via inline <script> in the template.
    function bootstrap() {
        var urls = window.REQ_TRACE_EXPORT_URLS || {};
        wireSankeyExport({
            formId: "requirements-traceability-export-form",
            svgFieldId: "requirements-export-svg",
            docxBtnId: "requirements-export-docx",
            pdfBtnId: "requirements-export-pdf",
            svgId: "requirements-sankey",
            urls: urls,
        });
    }
    if (document.readyState !== "loading") { bootstrap(); }
    else { document.addEventListener("DOMContentLoaded", bootstrap); }
})();
