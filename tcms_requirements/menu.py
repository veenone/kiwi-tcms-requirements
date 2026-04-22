from django.urls import reverse_lazy


# Appended to Kiwi's MORE menu by the plugin loader.
# Divider convention: ("-", "-") renders as <li class="divider">.
MENU_ITEMS = [
    ("Requirements", [
        ("All requirements", reverse_lazy("requirement-list")),
        ("New requirement", reverse_lazy("requirement-new")),
        ("Requirements dashboard", reverse_lazy("requirement-dashboard")),
        ("Traceability diagram", reverse_lazy("requirement-traceability")),
        ("-", "-"),
        ("Import (CSV / XLSX)", reverse_lazy("requirement-import")),
        ("Export for JIRA", reverse_lazy("requirement-export-hub")),
    ]),
]
