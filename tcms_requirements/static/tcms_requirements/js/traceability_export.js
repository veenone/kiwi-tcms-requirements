/* Captures a live-rendered Sankey SVG and POSTs it to a server export
 * endpoint (DOCX or PDF) on user click. Uses fetch + blob + download
 * anchor so the user gets an explicit save dialog and clear visual
 * feedback (spinner on the clicked button) rather than relying on the
 * browser's silent auto-download from a hidden-form POST.
 *
 * Public API:
 *   window.tcmsRequirements.wireSankeyExport({
 *     formId:      "requirements-traceability-export-form",  (optional, legacy)
 *     svgFieldId:  "requirements-export-svg",                (optional, legacy)
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
        var docxBtn = opts.docxBtnId ? document.getElementById(opts.docxBtnId) : null;
        var pdfBtn = opts.pdfBtnId ? document.getElementById(opts.pdfBtnId) : null;
        var svgEl = document.getElementById(opts.svgId);
        var urls = opts.urls || {};

        // No buttons + no URLs is the auto-bootstrap "this page has no
        // export wiring" case — bail silently. Only error when the
        // caller clearly intended to wire something (buttons found OR
        // urls supplied) but the other half is missing.
        if (!docxBtn && !pdfBtn && !urls.docx && !urls.pdf) {
            return false;
        }
        if (!docxBtn && !pdfBtn) {
            console.warn(TAG, "wireSankeyExport: URLs supplied but no buttons found —",
                opts.docxBtnId, opts.pdfBtnId);
            return false;
        }
        if (!urls.docx && !urls.pdf) {
            console.warn(TAG, "wireSankeyExport: buttons found but URLs missing —",
                "did you set data-export-docx-url / data-export-pdf-url on #requirements-project-detail?");
            return false;
        }

        console.log(TAG, "wired", {
            docx: urls.docx, pdf: urls.pdf, hasSvg: !!svgEl,
        });

        function captureSvg() {
            if (!svgEl) {
                console.warn(TAG, "no live SVG — POSTing empty (server falls back to table-only).");
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

        function getCsrfToken() {
            var anyField = document.querySelector("input[name=csrfmiddlewaretoken]");
            return (anyField || {}).value || "";
        }

        function downloadFromResponse(response, fallbackName) {
            var disposition = response.headers.get("Content-Disposition") || "";
            var match = disposition.match(/filename="?([^";]+)"?/i);
            var name = match ? match[1] : fallbackName;
            return response.blob().then(function (blob) {
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url;
                a.download = name;
                a.style.display = "none";
                document.body.appendChild(a);
                a.click();
                setTimeout(function () {
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                }, 100);
            });
        }

        function setBusy(btn, busy) {
            if (!btn) { return; }
            if (busy) {
                if (!btn.dataset.origText) {
                    btn.dataset.origText = btn.textContent;
                }
                while (btn.firstChild) { btn.removeChild(btn.firstChild); }
                var icon = document.createElement("i");
                icon.className = "fa fa-spinner fa-spin";
                btn.appendChild(icon);
                btn.appendChild(document.createTextNode(" Exporting…"));
                btn.style.pointerEvents = "none";
                btn.style.opacity = "0.6";
            } else if (btn.dataset.origText) {
                while (btn.firstChild) { btn.removeChild(btn.firstChild); }
                btn.appendChild(document.createTextNode(btn.dataset.origText));
                btn.style.pointerEvents = "";
                btn.style.opacity = "";
                delete btn.dataset.origText;
            }
        }

        function submitFetch(url, label, btn, fallbackName) {
            console.log(TAG, "POST →", label, url);
            setBusy(btn, true);
            var fd = new FormData();
            fd.append("csrfmiddlewaretoken", getCsrfToken());
            fd.append("svg", captureSvg());
            return fetch(url, {
                method: "POST",
                body: fd,
                credentials: "same-origin",
            }).then(function (response) {
                if (!response.ok) {
                    throw new Error(label + " export failed: HTTP " + response.status);
                }
                return downloadFromResponse(response, fallbackName);
            }).then(function () {
                console.log(TAG, label, "download complete");
            }).catch(function (err) {
                console.error(TAG, "submitFetch error:", err);
                alert("Export failed: " + err.message + "\nSee browser console for details.");
            }).then(function () {
                setBusy(btn, false);
            });
        }

        if (docxBtn && urls.docx) {
            docxBtn.addEventListener("click", function (ev) {
                ev.preventDefault();
                submitFetch(urls.docx, "DOCX", docxBtn, "export.docx");
            });
        }
        if (pdfBtn && urls.pdf) {
            pdfBtn.addEventListener("click", function (ev) {
                ev.preventDefault();
                submitFetch(urls.pdf, "PDF", pdfBtn, "export.pdf");
            });
        }
        return true;
    }

    // Public API.
    window.tcmsRequirements = window.tcmsRequirements || {};
    window.tcmsRequirements.wireSankeyExport = wireSankeyExport;

    // Auto-bootstrap for the traceability-page IDs. URLs come from data
    // attributes on #requirements-traceability (CSP-safe — no inline JS).
    // Falls back to window.REQ_TRACE_EXPORT_URLS for legacy templates that
    // still use the old inline-script pattern.
    function bootstrap() {
        var root = document.getElementById("requirements-traceability");
        var urls = window.REQ_TRACE_EXPORT_URLS || {};
        if (root) {
            urls = {
                docx: root.getAttribute("data-export-docx-url") || urls.docx,
                pdf: root.getAttribute("data-export-pdf-url") || urls.pdf,
            };
        }
        wireSankeyExport({
            docxBtnId: "requirements-export-docx",
            pdfBtnId: "requirements-export-pdf",
            svgId: "requirements-sankey",
            urls: urls,
        });
    }
    if (document.readyState !== "loading") { bootstrap(); }
    else { document.addEventListener("DOMContentLoaded", bootstrap); }
})();
