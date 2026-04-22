"""Response-rewriting middleware that injects the plugin's JS bundle on
Kiwi core pages (TestCase detail, etc.) so the "Requirements" card can
render without editing any core template.

Identical shape to tcms_review.middleware — the injected script is
self-contained, inspects `body[id]`, and no-ops on pages it doesn't know
about.
"""


class InjectRequirementsBundleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        from django.templatetags.static import static  # noqa: WPS433

        from tcms_requirements import __version__  # noqa: WPS433

        url = static("tcms_requirements/js/inject.js")
        self._versioned_src = f"{url}?v={__version__}"

    def _script_tag(self, request):
        user = getattr(request, "user", None)
        user_id = ""
        if user is not None and user.is_authenticated:
            user_id = str(user.pk)
        tag = (
            f'<script src="{self._versioned_src}" defer '
            f'data-source="tcms_requirements" '
            f'data-current-user-id="{user_id}"></script>'
        )
        return tag.encode("utf-8")

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(response, "streaming", False):
            return response

        content_type = response.get("Content-Type", "")
        if not content_type.startswith("text/html"):
            return response

        content = getattr(response, "content", None)
        if not content or b"</body>" not in content:
            return response

        if b'data-source="tcms_requirements"' in content:
            return response

        response.content = content.replace(
            b"</body>",
            self._script_tag(request) + b"</body>",
            1,
        )
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
