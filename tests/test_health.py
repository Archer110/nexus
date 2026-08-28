from pymongo.errors import PyMongoError
from redis.exceptions import ConnectionError


def test_liveness_does_not_require_datastore_queries(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_readiness_reports_all_datastores_available(client, mocker):
    mongo_database = mocker.patch("app.routes.health.get_mongo_db").return_value

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json == {
        "status": "ok",
        "checks": {"mongo": True, "postgres": True, "redis": True},
    }
    mongo_database.command.assert_called_once_with("ping")


def test_readiness_returns_503_without_exposing_failure_details(client, app, mocker):
    mocker.patch(
        "app.routes.health.get_mongo_db"
    ).return_value.command.side_effect = PyMongoError("internal connection detail")
    mocker.patch.object(
        app.config["SESSION_REDIS"],
        "ping",
        side_effect=ConnectionError("internal redis detail"),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json == {
        "status": "unavailable",
        "checks": {"mongo": False, "postgres": True, "redis": False},
    }
    assert b"internal connection detail" not in response.data
