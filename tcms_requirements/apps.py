"""AppConfig for tcms_requirements.

Mirrors the pattern from the sibling kiwitcms-review plugin: in ready() we
wire signals, install the response-rewriting middleware, and register any
JSON-RPC methods straight into modernrpc's registry (because modernrpc has
already finished scanning MODERNRPC_METHODS_MODULES by the time plugin
apps run their ready()).
"""
from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate, post_save, pre_save


def _grant_permissions_post_migrate(sender, **kwargs):
    """Assign the plugin's permissions to the Tester / Administrator groups.

    Runs late so `Permission` rows exist — a migration-time attempt can race
    against the contenttypes framework on some installs.
    """
    from tcms_requirements.permissions import grant_permissions_to_groups  # noqa: WPS433

    grant_permissions_to_groups()


class RequirementsConfig(AppConfig):
    name = "tcms_requirements"
    verbose_name = "Requirements Management"

    def ready(self):
        # Register Django system checks — importing executes the @register
        # decorators.
        from tcms_requirements import checks  # noqa: F401,WPS433

        self._register_rpc_methods()
        self._install_middleware()

        from tcms_requirements import signals as req_signals  # noqa: WPS433
        from tcms_requirements.models import Requirement, RequirementTestCaseLink

        pre_save.connect(
            req_signals.cache_previous_requirement_status,
            sender=Requirement,
            dispatch_uid="tcms_requirements.cache_previous_status",
        )
        post_save.connect(
            req_signals.flag_suspect_links_on_requirement_change,
            sender=Requirement,
            dispatch_uid="tcms_requirements.flag_suspect_links",
        )
        post_save.connect(
            req_signals.clear_suspect_on_link_update,
            sender=RequirementTestCaseLink,
            dispatch_uid="tcms_requirements.clear_suspect_on_link_update",
        )
        post_migrate.connect(
            _grant_permissions_post_migrate,
            sender=self,
            dispatch_uid="tcms_requirements.grant_permissions_post_migrate",
        )

    @staticmethod
    def _install_middleware():
        middleware_path = "tcms_requirements.middleware.InjectRequirementsBundleMiddleware"
        if middleware_path not in settings.MIDDLEWARE:
            settings.MIDDLEWARE = list(settings.MIDDLEWARE) + [middleware_path]

    @staticmethod
    def _register_rpc_methods():
        """Register tcms_requirements.rpc methods into modernrpc's registry."""
        import inspect  # noqa: WPS433

        try:
            from modernrpc.core import registry  # noqa: WPS433
        except ImportError:
            return

        try:
            import tcms_requirements.rpc as rpc_module  # noqa: WPS433
        except ImportError:
            return

        for _, func in inspect.getmembers(rpc_module, inspect.isfunction):
            if getattr(func, "modernrpc_enabled", False):
                registry.register_method(func)
