import re

from flask.testing import FlaskClient

CSRF_TOKEN_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')


def get_csrf_token(client: FlaskClient) -> str:
    response = client.get("/admin/login")
    match = CSRF_TOKEN_PATTERN.search(response.data)
    if match is None:
        raise AssertionError("The login page did not render a CSRF token.")
    return match.group(1).decode()
