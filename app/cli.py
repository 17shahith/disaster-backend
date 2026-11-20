"""Flask CLI commands: ``flask seed``, ``flask simulate``, ``flask create-admin``."""
import click
from flask import current_app

from .constants import Role
from .scenarios import SCENARIOS, run_scenarios
from .seed import seed_base_data


def register_cli(app):
    @app.cli.command("seed")
    @click.option("--no-scenarios", is_flag=True, help="Only create base data, skip simulated emergencies.")
    def seed(no_scenarios):
        """Load demo users, teams, shelters, supplies and simulated scenarios."""
        click.echo("Seeding base data...")
        seed_base_data(log=click.echo)
        if not no_scenarios:
            click.echo("Running simulated emergency scenarios...")
            run_scenarios(log=click.echo)
        click.echo(
            "Done. Demo accounts: admin / operator / teamlead / teamlead2 / coordinator "
            f"(password: {current_app.config['SEED_DEFAULT_PASSWORD']})"
        )

    @app.cli.command("simulate")
    @click.argument("scenario", type=click.Choice(["all", *SCENARIOS]), default="all")
    def simulate(scenario):
        """Run one or all simulated emergency scenarios."""
        run_scenarios(None if scenario == "all" else [scenario], log=click.echo)

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--full-name", prompt=True, default="System Administrator")
    @click.password_option()
    def create_admin(username, email, full_name, password):
        """Create an administrator account."""
        from .services.user_service import SYSTEM, create_user
        from .utils.errors import APIError

        try:
            user = create_user(
                {"username": username, "email": email, "full_name": full_name, "password": password,
                 "role": Role.ADMIN},
                actor=SYSTEM,
            )
        except APIError as exc:
            raise click.ClickException(f"{exc.message}: {exc.errors}") from None
        click.echo(f"Administrator '{user.username}' created (id={user.id}).")
