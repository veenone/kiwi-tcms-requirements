from django.urls import reverse_lazy


# Appended to Kiwi's MORE menu by the plugin loader.
# Divider convention: ("-", "-") renders as <li class="divider">.
MENU_ITEMS = [
    ("Requirements", [
        # Registry group — CRUD entry points.
        ("All requirements", reverse_lazy("requirement-list")),
        ("New requirement", reverse_lazy("requirement-new")),
        ("Projects", reverse_lazy("requirement-project-list")),
        ("-", "-"),
        # Analytics group — dashboard + Sankey traceability views.
        ("Requirements dashboard", reverse_lazy("requirement-dashboard")),
        ("Traceability — full chain", reverse_lazy("requirement-traceability")),
        ("Traceability — by feature",
         reverse_lazy("requirement-traceability-feature")),
        ("Traceability — verification status",
         reverse_lazy("requirement-traceability-verification")),
        ("-", "-"),
        # Data-exchange group — bulk import / export.
        ("Import (CSV / XLSX)", reverse_lazy("requirement-import")),
        ("Export for JIRA", reverse_lazy("requirement-export-hub")),
    ]),
]
