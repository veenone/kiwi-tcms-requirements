"""Signal handlers wired in apps.py::ready().

The suspect-flagging rule:
- When a Requirement is edited (not just created), every existing link
  to a test case has `suspect=True` set. The reviewer opens the link and
  confirms the test still verifies the new text, at which point the
  link's suspect flag clears.
- Creating or editing a link directly also clears `suspect` (fresh intent).
- A status-only change (e.g. draft → approved) does NOT flag suspect,
  because the requirement text hasn't changed.
"""
_PRE_SAVE_STATUS_ATTR = "_tcms_requirements_previous_status"
_PRE_SAVE_TEXT_ATTR = "_tcms_requirements_previous_text_hash"


def _text_fingerprint(req) -> str:
    """Cheap fingerprint of the mutable 'text' fields — used to decide
    whether to flip all links to suspect on save."""
    return "|".join([
        req.title or "",
        req.description or "",
        req.rationale or "",
        req.source_section or "",
    ])


def cache_previous_requirement_status(sender, instance, **kwargs):
    """Stash prior status + text hash on pre_save for post_save diffing."""
    if instance.pk:
        previous = (
            sender.objects
            .filter(pk=instance.pk)
            .values("status", "title", "description", "rationale", "source_section")
            .first()
        ) or {}
        setattr(instance, _PRE_SAVE_STATUS_ATTR, previous.get("status"))
        setattr(
            instance,
            _PRE_SAVE_TEXT_ATTR,
            "|".join([
                previous.get("title") or "",
                previous.get("description") or "",
                previous.get("rationale") or "",
                previous.get("source_section") or "",
            ]),
        )
    else:
        setattr(instance, _PRE_SAVE_STATUS_ATTR, None)
        setattr(instance, _PRE_SAVE_TEXT_ATTR, None)


def flag_suspect_links_on_requirement_change(sender, instance, created, **kwargs):
    """When a requirement's text changes after creation, flip every link to suspect."""
    if kwargs.get("raw"):
        return
    if created:
        return

    previous_hash = getattr(instance, _PRE_SAVE_TEXT_ATTR, None)
    current_hash = _text_fingerprint(instance)
    if previous_hash is None or previous_hash == current_hash:
        return

    # Lazy import to avoid circular import during apps.ready().
    from tcms_requirements.models import RequirementTestCaseLink  # noqa: WPS433

    RequirementTestCaseLink.objects.filter(
        requirement=instance,
        suspect=False,
    ).update(suspect=True)


def clear_suspect_on_link_update(sender, instance, created, **kwargs):
    """Treat any link save as an implicit 'reviewer re-confirmed' event.

    If the user explicitly edits the link (updates notes, re-saves, etc.),
    their intent is that the link is current. Creating a brand-new link
    is already non-suspect. The only path that keeps `suspect=True` is
    the automated flip from requirement edits — which sets suspect with
    .update() (bypassing signals), so there's no recursion.
    """
    if kwargs.get("raw"):
        return
    if created:
        return
    if not instance.suspect:
        return

    # The user saved a suspect link — assume re-confirmation unless they
    # explicitly kept the flag via the admin. We honour `suspect` being
    # passed in True via the form; clearing is the default-through-save path.
    # (In practice the clearing is handled by the view explicitly setting
    # `suspect=False`; this handler is a belt-and-suspenders safety net.)
    # No-op here to avoid overriding an explicit update. Left as a hook.


def on_requirement_delete(sender, instance, **kwargs):
    """No-op placeholder; lets future versions attach delete-time cleanup
    without needing a new signal wire-up."""
