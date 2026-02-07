from flask import request, url_for


def toggle_url(key, value):
    """
    Generates a URL that toggles a specific query parameter
    (adds it if missing, removes it if present).
    Used for the multi-select checkboxes.
    """
    args = request.args.to_dict(flat=False)  # Get mutable dict of lists

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

    return url_for(request.endpoint, **args)
