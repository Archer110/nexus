from typing import Any

from flask import request, url_for


def toggle_url(key: str, value: str) -> str:
    """
    Generates a URL that toggles a specific query parameter
    (adds it if missing, removes it if present).
    Used for the multi-select checkboxes.
    """
    args: dict[str, Any] = request.args.to_dict(flat=False)

    # Always reset to page 1 when filtering
    if "page" in args:
        del args["page"]

    current_vals = args.get(key, [])
    str_val = str(value)

    if str_val in current_vals:
        current_vals.remove(str_val)  # Uncheck
        if not current_vals:
            del args[key]
    else:
        current_vals.append(str_val)  # Check
        args[key] = current_vals

    endpoint = request.endpoint
    if endpoint is None:
        raise RuntimeError("Cannot build a filter URL without an endpoint.")

    return url_for(endpoint, **args)
