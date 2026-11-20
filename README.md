# Disaster Response Resource Coordinator — Backend

A Flask REST API for coordinating emergency response. It covers incidents, emergency requests, response teams, shelters, relief supplies, resource allocation, dispatch operations and situation reports. Access is controlled by JWT authentication and four user roles.

The React frontend lives in its own project (`Disaster Response-frontend`) and talks to this API over REST. See [Running with the React frontend](#running-with-the-react-frontend).

- Full endpoint reference: [docs/API.md](docs/API.md)

## Tech stack

| Area | Tools |
|---|---|
| Language and framework | Python 3.12, Flask 3 (application factory and blueprints) |
| Database | SQLite with SQLAlchemy 2; migrations with Flask-Migrate (Alembic) |
| Document store | MongoDB via PyMongo, for saved situation-report snapshots (optional) |
| Security | Flask-JWT-Extended (access and refresh tokens, revocation on logout); Werkzeug password hashing (scrypt) |
| API support | Flask-CORS; python-dotenv for configuration |
| Testing | Pytest, pytest-cov |
| Delivery | Docker with Gunicorn, docker-compose, Jenkins |

## Project structure

```
app/
├── __init__.py          # application factory, health endpoint, SQLite FK enforcement
├── config.py            # Development / Testing / Production config (env-driven)
├── constants.py         # roles, statuses, categories, status transition maps
├── extensions.py        # db, migrate, jwt, cors
├── cli.py               # flask seed | simulate | create-admin
├── seed.py              # demo users, teams, shelters, supplies
├── scenarios.py         # 5 simulated emergency scenarios
├── models/              # SQLAlchemy models (one per table)
├── routes/              # Blueprints: input validation + RBAC, delegate to services
├── services/            # business rules and transactions
├── middleware/          # role_required decorator, JWT callbacks, global error handlers
└── utils/               # response envelopes, validators, pagination, errors, time helpers
migrations/              # Alembic migration scripts
tests/                   # Pytest suite (separate SQLite database per test)
docs/API.md              # API documentation
Dockerfile, docker-compose.yml, docker-entrypoint.sh, Jenkinsfile
```

### Database tables

| Table | Purpose |
|---|---|
| `users` | Accounts and roles |
| `incidents` | Registered emergencies |
| `emergency_requests` | Requests for help, linked to incidents |
| `response_teams` | Teams, leads and availability |
| `shelters` | Capacity and occupancy |
| `relief_supplies` | Stock, reserved and dispatched quantities |
| `resource_allocations` | Teams, supplies or shelter space allocated to incidents |
| `dispatch_records` | Movement of allocated resources to the field |
| `activity_logs` | Audit trail |
| `inventory_transactions` | Supply history (supporting table) |
| `token_blocklist` | Revoked JWTs (supporting table) |

The database protects its own integrity:

- Foreign keys are enforced.
- CHECK constraints cover every enumerated value, non-negative quantities, `reserved ≤ stock` and `occupancy ≤ capacity`.
- An allocation must name exactly one resource that matches its type.
- A partial unique index stops a team from holding two active assignments.

### MongoDB (saved situation reports)

SQLite is the system of record for everything above. MongoDB runs alongside it and stores one thing: **saved situation-report snapshots**, in the `situation_reports` collection of the `disaster_response` database.

- **What a snapshot is.** It freezes the full consolidated report (`GET /api/reports/summary`) at a moment in time, so briefings can be compared later even though the live figures keep changing.
- **Why MongoDB.** Each snapshot is one large, read-only, nested document with no relational constraints. Keeping it out of SQLite leaves the transactional data model unchanged.
- **It's optional.** Without `MONGO_URI`, or if the server is down, only the snapshot endpoints return `503`. `GET /api/health` reports `mongodb: ok | unavailable | disabled`.
- **Auditing.** Saving and deleting a snapshot are still recorded in the SQL `activity_logs` table.

## Roles

| Role (`role` value) | Can do |
|---|---|
| Control Room Operator (`control_room_operator`) | Register and update incidents; create and manage emergency requests; assign response teams; view dashboards |
| Response Team Lead (`response_team_lead`) | Register and manage their own teams and availability; record team activities and progress; view incidents, requests and dispatches **assigned to their teams**; update dispatch delivery status; mark their assignments and requests complete |
| Relief Coordinator (`relief_coordinator`) | Manage shelters and supplies; view inventory history; allocate teams, supplies and shelter space; approve and complete allocations; manage dispatches |
| Administrator (`admin`) | Everything above, plus user and role management, the system activity log, and deleting incidents and teams |

Permissions are enforced on the server. The role is reloaded from the database on every request, so a role change or deactivation applies immediately.

## Key business rules

- Teams can only be assigned while `Available`. Assignment sets them to `Assigned`, dispatch to `Busy`, and completion or cancellation back to `Available`.
- An allocation reserves supply stock, which can never exceed what is available. Dispatching deducts the stock. Inventory can never go negative, and every movement is recorded in `inventory_transactions`.
- Shelter occupancy can never exceed capacity. Shelter status switches between `Open` and `Full` automatically.
- `Completed`/`Closed` incidents accept no new allocations or requests until they are reopened. An incident with active allocations cannot be closed.
- A dispatch must belong to an `Approved`/`Allocated` allocation, and dispatched quantities can never exceed the allocated quantity.
- Status changes follow strict state machines for allocations and dispatches. Duplicate active allocations are rejected with 409.
- Every multi-step operation runs as one database transaction. Stock, capacity and availability changes use conditional `UPDATE … WHERE` statements, so concurrent requests cannot oversell stock or overfill a shelter.
- Every important operation is written to `activity_logs`.

## Getting started (local)

Requires Python 3.12+.

**1. Create a virtual environment and install dependencies.**

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
```

**2. Create your configuration file.**

Copy the example into a file named `.env` in this folder (next to `run.py`):

```bash
cp .env.example .env                 # Windows PowerShell: Copy-Item .env.example .env
```

Then edit `.env`:

- Replace the two `change-me` values for `SECRET_KEY` and `JWT_SECRET_KEY` with random strings. To generate one:
  `python -c "import secrets; print(secrets.token_hex(32))"`
- Set `MONGO_URI` to your MongoDB server (see [Setting up MongoDB](#setting-up-mongodb)). Leave it as it is to use a local MongoDB.

`.env` is git-ignored; never commit it. It is read only at start-up, so restart the API after changing it.

**3. Create the database schema and load demo data.**

```bash
flask --app run.py db upgrade
flask --app run.py seed     # demo users, teams, shelters, supplies + 5 scenarios
```

**4. Start the API.**

```bash
python run.py               # http://127.0.0.1:5000
```

### Demo accounts (created by `flask seed`)

All demo accounts use the password from `SEED_DEFAULT_PASSWORD` (default `Password@123`). You can sign in with either the username or the email.

| Username | Email | Role |
|---|---|---|
| `admin` | `admin@drrc.local` | Administrator |
| `operator` | `operator@drrc.local` | Control Room Operator |
| `teamlead`, `teamlead2` | `teamlead@drrc.local`, `teamlead2@drrc.local` | Response Team Lead |
| `coordinator` | `coordinator@drrc.local` | Relief Coordinator |

Change these passwords, or skip seeding, for any real deployment.

### CLI commands

| Command | Purpose |
|---|---|
| `flask --app run.py seed [--no-scenarios]` | Load base demo data, with or without the simulated scenarios |
| `flask --app run.py simulate [all\|flood\|earthquake\|fire\|cyclone\|building_collapse]` | Run simulated emergency scenarios |
| `flask --app run.py create-admin` | Create an administrator account (prompts for details) |
| `flask --app run.py db migrate -m "msg"` | Generate a migration after changing a model |
| `flask --app run.py db upgrade` | Apply migrations |

### Quick API check

```bash
curl -X POST http://localhost:5000/api/auth/login -H "Content-Type: application/json" \
     -d '{"username":"coordinator","password":"Password@123"}'
curl http://localhost:5000/api/reports/dashboard -H "Authorization: Bearer <access_token>"
```

## Setting up MongoDB

MongoDB is only needed for saved situation reports; everything else runs on SQLite. The connection is set with **`MONGO_URI` in `.env`**. The database name is the last part of the URL.

| Where MongoDB runs | `MONGO_URI` value |
|---|---|
| On this computer (the default in development) | `mongodb://localhost:27017/disaster_response` |
| MongoDB Atlas (cloud) | `mongodb+srv://<user>:<password>@<cluster>.mongodb.net/disaster_response?retryWrites=true&w=majority` |
| Docker Compose | Set automatically to `mongodb://mongo:27017/disaster_response` by `docker-compose.yml`; the `.env` value is ignored |
| Turned off | `MONGO_URI=` (empty); snapshot endpoints then return `503` |

To use a local server, install MongoDB Community Server and make sure the MongoDB service is running. For Atlas, add your IP address to the cluster's network access list, and URL-encode any special characters in the password (for example `@` becomes `%40`).

Check the connection after restarting the API:

```bash
curl http://127.0.0.1:5000/api/health
# "mongodb": "ok"           connected
# "mongodb": "unavailable"  MONGO_URI is set but the server can't be reached
# "mongodb": "disabled"     MONGO_URI is empty
```

## Simulated emergency scenarios

`flask seed` and `flask simulate` run five scenarios. They call the same service layer as the API, so every validation, transaction and audit-log rule applies. No external alert systems are involved.

| Scenario | What it does |
|---|---|
| Flood | Rescue, food, water and shelter requests. Assigns a rescue team, which is dispatched. Water is allocated and fully delivered. Rice is allocated, with part of it in transit. 120 evacuees are placed in a shelter. |
| Earthquake | Medical and rescue requests. Assigns search-and-rescue and medical teams. First-aid kits are delivered and antibiotics are partly dispatched. Incident set to In Progress. |
| Fire | Rescue request. A fire brigade is dispatched. The team lead completes the assignment, the request is completed and the incident is marked Completed. |
| Cyclone | Shelter, food and water requests. 850 evacuees are spread over two shelters. Meal packs are delivered and water tablets and blankets are allocated. |
| Building collapse | Rescue and medical requests. A rescue team and hydraulic cutters are dispatched and the rescue is completed. A medical team stays assigned. |

## Testing

```bash
pytest                                   # 188 tests (MongoDB is faked in memory with mongomock)
pytest --cov=app --cov-report=term       # with coverage
pytest --junitxml=reports/junit.xml      # JUnit report (used by Jenkins)
```

Each test gets a fresh SQLite database file in a temporary directory, so the development database is never touched.

The suite covers:

- Registration, login (valid and invalid), JWT handling (missing, invalid, expired and revoked tokens, refresh) and role-based authorization for every module.
- CRUD and validation for each module.
- Team assignment and availability changes.
- Shelter capacity limits and supply inventory limits.
- Allocation workflow and transaction rollback.
- Dispatch lifecycle and inventory deduction.
- Reports, error format, and the five end-to-end scenarios.
- The contract the React frontend relies on: CORS for the Vite origin, dashboard and report payloads, and the incident and dispatch fields the UI collects (`tests/test_frontend_contract.py`).

## Running with the React frontend

The two projects stay in separate folders and run independently. The frontend only talks to SQLite through this API.

| | Backend (this folder) | Frontend (`Disaster Response-frontend`) |
|---|---|---|
| Install | `pip install -r requirements.txt` | `npm install` |
| Configure | `.env` (optional for local development) | `.env` with `VITE_API_BASE_URL=http://127.0.0.1:5000/api` |
| First run | `flask --app run.py db upgrade` and `flask --app run.py seed` | — |
| Start | `python run.py` → http://127.0.0.1:5000 | `npm run dev` → http://localhost:5173 |

Open http://localhost:5173 and sign in with a seeded account, for example `coordinator@drrc.local` / `Password@123`.

How the two sides fit together:

- **CORS.** The defaults already allow `http://localhost:5173` and `http://127.0.0.1:5173`. Set `CORS_ORIGINS` if the frontend is served from anywhere else.
- **Authentication.** The frontend stores the access and refresh tokens and sends `Authorization: Bearer <token>`. On a 401 it refreshes once through `POST /api/auth/refresh`; if that fails it sends the user back to the login page. Logout revokes both tokens.
- **Data shapes.** The frontend translates this API's snake_case fields and integer ids into its own shapes in a single module (`src/services/adapters.js`). The API contract is unchanged.

## Docker

```bash
cp .env.example .env
# Set APP_ENV=production and strong SECRET_KEY / JWT_SECRET_KEY values (32+ random chars).
# Set SEED_DEMO_DATA=true to load demo data on first start.
docker compose up --build -d
curl http://localhost:5000/api/health
```

- The container runs as a non-root user and applies migrations at startup (`flask db upgrade`).
- It serves the API with Gunicorn and includes a health check.
- The SQLite database lives in the named volume `drrc_data`, mounted at `/app/instance`, so data survives restarts and rebuilds.
- Compose also starts a `mongo` (MongoDB 8.0) container with its data in the `drrc_mongo` volume. It isn't published to the host; only the API container can reach it.
- In production the app refuses to start with missing or placeholder secrets.

### Backups

All data lives in two places: the SQLite file and the MongoDB snapshots.

- **Local development:** stop the API, then copy `instance/disaster_response.db`. Back up MongoDB with `mongodump --uri "mongodb://localhost:27017/disaster_response" --out backup/`.
- **Docker:** copy the database out of the running container, and dump MongoDB from its container:

```bash
docker compose cp api:/app/instance/disaster_response.db ./backup/disaster_response.db
docker compose exec mongo mongodump --db disaster_response --archive > ./backup/mongo.archive
```

To restore, put the `.db` file back while the API is stopped, and run `mongorestore --archive < mongo.archive` (in the container: `docker compose exec -T mongo mongorestore --archive < ./backup/mongo.archive`).

## Jenkins CI/CD

The [Jenkinsfile](Jenkinsfile) is a declarative pipeline. It needs a Linux agent with Python 3.12, Docker and the JUnit plugin.

| Stage | What it does |
|---|---|
| Checkout | `checkout scm` |
| Install Dependencies | Creates a virtualenv and installs `requirements-dev.txt` |
| Run Tests | Runs Pytest with JUnit XML and coverage (XML and HTML). Results are published even when tests fail. |
| Generate Test Reports | Writes a summary of test counts and coverage, and archives `reports/**` |
| Build Docker Image | Builds `disaster-response-backend:<build>` and `:latest` |
| Deployment Preparation | Validates `docker-compose.yml`, smoke-tests the image (migrations and the health endpoint), records the image tag, and pushes to `$DOCKER_REGISTRY` if that variable is set |

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `development` / `testing` / `production` |
| `SECRET_KEY`, `JWT_SECRET_KEY` | dev placeholders | **Required** in production (32+ chars) |
| `DATABASE_URL` | `sqlite:///disaster_response.db` | Relative paths resolve to `instance/` |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Access-token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | `7` | Refresh-token lifetime |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000` | Allowed frontend origins (the Vite dev server can be opened as either host) |
| `SEED_DEFAULT_PASSWORD` | `Password@123` | Password for seeded demo users |
| `SEED_DEMO_DATA` | `false` | Docker: seed data on container start |
| `MONGO_URI` | development: `mongodb://localhost:27017/disaster_response`; otherwise empty (disabled) | MongoDB for saved situation reports. Docker Compose sets it to its `mongo` service |
| `MONGO_DB_NAME` | the database name in the URI, else `disaster_response` | Overrides the MongoDB database name |
| `MONGO_TIMEOUT_MS` | `3000` | How long to wait for MongoDB before answering `503` |
| `HOST`, `PORT` | `127.0.0.1`, `5000` | Address used by `python run.py` (use `HOST=0.0.0.0` to allow other devices on your network) |

## Troubleshooting

| Problem | Fix |
|---|---|
| `RuntimeError: Production requires strong secrets` | Set `SECRET_KEY` and `JWT_SECRET_KEY` to 32+ random characters, or use `APP_ENV=development` locally |
| `no such table: users` | Run `flask --app run.py db upgrade` |
| Login fails for the demo accounts | Run `flask --app run.py seed`, or check `SEED_DEFAULT_PASSWORD` |
| Snapshots return `503` | MongoDB isn't running or `MONGO_URI` is wrong; check `GET /api/health` |
| Browser shows a CORS error | Add the frontend's exact origin (scheme, host and port) to `CORS_ORIGINS` and restart |
| Everyone was logged out | `JWT_SECRET_KEY` changed, so old tokens are no longer valid; sign in again |
| Port 5000 is already in use | Stop the other process, or start with `PORT=5001` and update the frontend's `VITE_API_BASE_URL` |
