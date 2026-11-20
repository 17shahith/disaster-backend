from . import allocations, auth, dispatch, incidents, reports, requests, shelters, supplies, teams, users

BLUEPRINTS = (
    auth.bp,
    users.bp,
    incidents.bp,
    requests.bp,
    teams.bp,
    shelters.bp,
    supplies.bp,
    allocations.bp,
    dispatch.bp,
    reports.bp,
)


def register_blueprints(app):
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
