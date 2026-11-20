# Disaster Response Resource Coordinator — Backend

A Flask REST API for coordinating emergency response. It covers incidents, emergency requests, response teams, shelters, relief supplies, resource allocation, dispatch operations and situation reports. Access is controlled by JWT authentication and four user roles.

The React frontend lives in its own project (`Disaster Response-frontend`) and talks to this API over REST. See [Running with the React frontend](#running-with-the-react-frontend).

Full endpoint reference: [docs/API.md](docs/API.md)

## Contents

- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Configuration (.env)](#configuration-env)
- [Setting up MongoDB](#setting-up-mongodb)
- [Demo accounts](#demo-accounts)
- [CLI commands](#cli-commands)
- [API overview](#api-overview)
- [Roles](#roles)
- [Key business rules](#key-business-rules)
- [Project structure](#project-structure)
- [Database](#database)
- [Simulated emergency scenarios](#simulated-emergency-scenarios)
- [Testing](#testing)
- [Running with the React frontend](#running-with-the-react-frontend)
- [Docker](#docker)
- [Backups](#backups)
- [Jenkins CI/CD](#jenkins-cicd)
- [Troubleshooting](#troubleshooting)

## Tech stack

| Area | Tools |
|---|---|
| Language and framework | Python 3.12, Flask 3 (application factory and blueprints) |
| Database | SQLite with SQLAlchemy 2; migrations with Flask-Migrate (Alembic) |
| Document store | MongoDB via PyMongo, for saved situation-report snapshots (optional) |
| Security | Flask-JWT-Extended (access and refresh tokens, revocation on logout); Werkzeug password hashing (scrypt) |
| API support | Flask-CORS; python-dotenv for configuration |
| Testing | Pytest, pytest-cov, mongomock |
| Delivery | Docker with Gunicorn, docker-compose, Jenkins |

## Quick start

Requires **Python 3.12+**. MongoDB is optional (see [Setting up MongoDB](#setting-up-mongodb)).

**1. Create a virtual environment and install dependencies.**

```bash
python -m venv .venv

# Activate it
.venv\Scripts\Activate.ps1          # Windows PowerShell
source .venv/bin/activate           # macOS / Linux

pip install -r requirements-dev.txt
```

**2. Create the `.env` file** next to `run.py`, then edit it as described in [Configuration (.env)](#configuration-env).

```bash
cp .env.example .env                # Windows PowerShell: Copy-Item .env.example .env
```

**3. Create the database schema and load demo data** (first run only).

```bash
flask --app run.py db upgrade
flask --app run.py seed             # demo users, teams, shelters, supplies + 5 scenarios
```

**4. Start the API.**

```bash
python run.py                       # http://127.0.0.1:5000
```

**5. Check that it's running.**

```bash
curl http://127.0.0.1:5000/api/health
# {"success": true, "message": "Service is healthy", "data": {"status": "ok", "mongodb": "ok"}}
```

## Configuration (.env)

All settings are read from environment variables, normally through a `.env` file in this folder. Use [.env.example](.env.example) as the template.

- `.env` is git-ignored. **Never commit it**, and never put real values in `.env.example`.
- It is read only at start-up, so **restart the API after changing it**.
- Without a `.env`, development still runs on built-in defaults; production refuses to start.

Generate a strong secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `development`, `testing` or `production` |
| `SECRET_KEY`, `JWT_SECRET_KEY` | development placeholders | Signing keys. **Required** in production: 32+ random characters each |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Access-token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | `7` | Refresh-token lifetime |
| `DATABASE_URL` | `sqlite:///disaster_response.db` | SQLite database. Relative paths resolve to the `instance/` folder |
| `MONGO_URI` | development: `mongodb://localhost:27017/disaster_response`; otherwise empty (disabled) | MongoDB for saved situation reports |
| `MONGO_DB_NAME` | the database name in `MONGO_URI`, else `disaster_response` | Overrides the MongoDB database name |
| `MONGO_TIMEOUT_MS` | `3000` | How long to wait for MongoDB before answering `503` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000` | Comma-separated frontend origins allowed to call the API |
| `SEED_DEFAULT_PASSWORD` | `Password@123` | Password given to the demo accounts by `flask seed` |
| `SEED_DEMO_DATA` | `false` | Docker only: load demo data when the container starts |
| `API_PORT` | `5000` | Docker only: host port published by docker-compose |
| `HOST`, `PORT` | `127.0.0.1`, `5000` | Address used by `python run.py`. `HOST=0.0.0.0` allows other devices on your network |

## Setting up MongoDB

MongoDB is only needed for **saved situation reports**; everything else runs on SQLite. Put the connection URL in **`MONGO_URI` in `.env`**. The database name is the last part of the URL.

| Where MongoDB runs | `MONGO_URI` value |
|---|---|
| On this computer (the development default) | `mongodb://localhost:27017/disaster_response` |
| MongoDB Atlas (cloud) | `mongodb+srv://<user>:<password>@<cluster>.mongodb.net/disaster_response?retryWrites=true&w=majority` |
| Docker Compose | Set automatically to `mongodb://mongo:27017/disaster_response` by `docker-compose.yml`; the `.env` value is ignored |
| Turned off | `MONGO_URI=` (empty). Snapshot endpoints then return `503`; the rest of the API is unaffected |

- **Local server:** install MongoDB Community Server and make sure the MongoDB service is running.
- **Atlas:** add your IP address to the cluster's network access list, and URL-encode special characters in the password (for example `@` becomes `%40`).

After restarting the API, `GET /api/health` shows the connection state:

| `mongodb` value | Meaning |
|---|---|
| `ok` | Connected |
| `unavailable` | `MONGO_URI` is set but the server can't be reached |
| `disabled` | `MONGO_URI` is empty |

## Demo accounts

`flask seed` creates these accounts. They all use the password from `SEED_DEFAULT_PASSWORD` (default `Password@123`). You can sign in with either the username or the email.

| Username | Email | Role |
|---|---|---|
| `admin` | `admin@drrc.local` | Administrator |
| `operator` | `operator@drrc.local` | Control Room Operator |
| `teamlead`, `teamlead2` | `teamlead@drrc.local`, `teamlead2@drrc.local` | Response Team Lead |
| `coordinator` | `coordinator@drrc.local` | Relief Coordinator |

**For a real deployment**, skip seeding and create the administrator with `flask --app run.py create-admin`, or at least set your own `SEED_DEFAULT_PASSWORD` before seeding.

## CLI commands

| Command | Purpose |
|---|---|
| `flask --app run.py db upgrade` | Create or update the database schema |
| `flask --app run.py db migrate -m "message"` | Generate a migration after changing a model |
| `flask --app run.py seed [--no-scenarios]` | Load demo data, with or without the simulated scenarios |
| `flask --app run.py simulate [all\|flood\|earthquake\|fire\|cyclone\|building_collapse]` | Run simulated emergency scenarios |
| `flask --app run.py create-admin` | Create an administrator account (prompts for details) |

## API overview

Base URL: `http://127.0.0.1:5000/api`. Every endpoint except login, register, refresh and health needs the header `Authorization: Bearer <access_token>`. Full request and response details are in [docs/API.md](docs/API.md).

| Module | Endpoints |
|---|---|
| Health | `GET /health` |
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET` and `PUT /auth/profile` |
| Users (admin) | `GET`/`POST /users`, `GET`/`PUT`/`DELETE /users/{id}` (delete deactivates), `GET /activity-logs` |
| Incidents | `GET`/`POST /incidents`, `GET`/`PUT`/`DELETE /incidents/{id}` |
| Emergency requests | `GET`/`POST /requests`, `GET`/`PUT`/`DELETE /requests/{id}` |
| Response teams | `GET`/`POST /teams`, `GET /teams/available`, `GET`/`PUT`/`DELETE /teams/{id}`, `GET`/`POST /teams/{id}/activities` |
| Shelters | `GET`/`POST /shelters`, `GET /shelters/available`, `GET`/`PUT`/`DELETE /shelters/{id}` |
| Relief supplies | `GET`/`POST /supplies`, `GET /supplies/low-stock`, `GET`/`PUT`/`DELETE /supplies/{id}`, `GET /supplies/{id}/history` |
| Allocations | `GET`/`POST /allocations`, `GET`/`PUT /allocations/{id}` (cancelled, never deleted) |
| Dispatch | `GET`/`POST /dispatch`, `GET`/`PUT`/`DELETE /dispatch/{id}` (delete only while `Prepared`) |
| Reports | `GET /reports/dashboard`, `/summary`, `/incidents`, `/resources`, `/shelters`, `/teams` |
| Saved reports (MongoDB) | `GET`/`POST /reports/snapshots`, `GET`/`DELETE /reports/snapshots/{id}` |

List endpoints are paginated with `?page=` and `?per_page=` (max 100) and accept filters such as `?status=` and `?search=`.

**Response format.** Every response uses the same envelope:

```json
{ "success": true,  "message": "Incident created successfully", "data": { } }
{ "success": false, "message": "Invalid incident information", "errors": { "title": "This field is required." } }
```

Status codes: `200`/`201` success, `400` validation error, `401` missing or invalid token, `403` not allowed for your role, `404` not found, `409` business-rule conflict (for example not enough stock or an invalid status change), `503` MongoDB unavailable.

**Example:**

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login -H "Content-Type: application/json" \
     -d '{"username":"coordinator","password":"Password@123"}'

curl http://127.0.0.1:5000/api/reports/dashboard -H "Authorization: Bearer <access_token>"
```

## Roles

| Role (`role` value) | Can do |
|---|---|
| Control Room Operator (`control_room_operator`) | Register and update incidents; create and manage emergency requests; assign response teams; view dashboards; save situation reports |
| Response Team Lead (`response_team_lead`) | Register and manage their own teams and availability; record team activities and progress; view incidents, requests and dispatches **assigned to their teams**; update dispatch delivery status; mark their assignments and requests complete |
| Relief Coordinator (`relief_coordinator`) | Manage shelters and supplies; view inventory history; allocate teams, supplies and shelter space; approve and complete allocations; manage dispatches; save situation reports |
| Administrator (`admin`) | Everything above, plus user and role management, the system activity log, and deleting incidents, teams and saved reports |

Permissions are enforced on the server. The role is reloaded from the database on every request, so a role change or deactivation applies immediately. Self-registration offers every role except Administrator.

## Key business rules

- Teams can only be assigned while `Available`. Assignment sets them to `Assigned`, dispatch to `Busy`, and completion or cancellation back to `Available`.
- An allocation reserves supply stock, which can never exceed what is available. Dispatching deducts the stock. Inventory can never go negative, and every movement is recorded in `inventory_transactions`.
- Shelter occupancy can never exceed capacity. Shelter status switches between `Open` and `Full` automatically.
- `Completed`/`Closed` incidents accept no new allocations or requests until they are reopened. An incident with active allocations cannot be closed.
- A dispatch must belong to an `Approved`/`Allocated` allocation, and dispatched quantities can never exceed the allocated quantity.
- Status changes follow strict state machines:
  - Allocation: `Pending → Approved → Allocated → Completed`, or `Cancelled`.
  - Dispatch: `Prepared → Dispatched → In Transit → Delivered → Completed`.
- Duplicate active allocations are rejected with `409`.
- Every multi-step operation runs as one database transaction. Stock, capacity and availability changes use conditional `UPDATE … WHERE` statements, so concurrent requests cannot oversell stock or overfill a shelter.
- Every important operation is written to `activity_logs`.

## Project structure

```
Disaster Response-backend/
├── app/
│   ├── __init__.py          # application factory, health endpoint, SQLite FK enforcement
│   ├── config.py            # Development / Testing / Production config (env-driven)
│   ├── constants.py         # roles, statuses, categories, status transition maps
│   ├── extensions.py        # db, migrate, jwt, cors
│   ├── mongo.py             # optional MongoDB connection
│   ├── cli.py               # flask seed | simulate | create-admin
│   ├── seed.py              # demo users, teams, shelters, supplies
│   ├── scenarios.py         # 5 simulated emergency scenarios
│   ├── models/              # SQLAlchemy models (one per table)
│   ├── routes/              # blueprints: input validation + RBAC, delegate to services
│   ├── services/            # business rules and transactions
│   ├── middleware/          # role_required decorator, JWT callbacks, global error handlers
│   └── utils/               # response envelopes, validators, pagination, errors, time helpers
├── migrations/              # Alembic migration scripts
├── tests/                   # Pytest suite (separate SQLite database per test)
├── docs/API.md              # full API documentation
├── instance/                # SQLite database (created at runtime, git-ignored)
├── .env.example             # configuration template
├── requirements.txt         # runtime dependencies
├── requirements-dev.txt     # + test dependencies
├── Dockerfile, docker-entrypoint.sh, docker-compose.yml
├── Jenkinsfile
└── run.py                   # entry point (python run.py / gunicorn run:app)
```

Requests flow **route → service → model**: routes validate input and check roles, services apply the business rules inside a transaction, and models define the tables.

## Database

### SQLite tables

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

SQLite is the system of record. MongoDB runs alongside it and stores one thing: **saved situation-report snapshots**, in the `situation_reports` collection.

- **What a snapshot is.** It freezes the full consolidated report (`GET /api/reports/summary`) at a moment in time, with a title and notes, so briefings can be compared later even though the live figures keep changing.
- **Why MongoDB.** Each snapshot is one large, read-only, nested document with no relational constraints. Keeping it out of SQLite leaves the transactional data model unchanged.
- **It's optional.** If MongoDB is off or unreachable, only the snapshot endpoints return `503`.
- **Auditing.** Saving and deleting a snapshot are still recorded in the SQL `activity_logs` table.

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
pytest                                   # 188 tests
pytest --cov=app --cov-report=term       # with coverage (about 94%)
pytest --junitxml=reports/junit.xml      # JUnit report (used by Jenkins)
```

Each test gets a fresh SQLite database in a temporary directory, and MongoDB is faked in memory with mongomock, so your development data is never touched and no MongoDB server is needed.

The suite covers:

- Registration, login (valid and invalid), JWT handling (missing, invalid, expired and revoked tokens, refresh) and role-based authorization for every module.
- CRUD and validation for each module.
- Team assignment and availability changes.
- Shelter capacity limits and supply inventory limits.
- Allocation workflow and transaction rollback.
- Dispatch lifecycle and inventory deduction.
- Reports, saved situation reports, error format, and the five end-to-end scenarios.
- The contract the React frontend relies on: CORS for the Vite origin, dashboard and report payloads, and the fields the UI collects (`tests/test_frontend_contract.py`).

## Running with the React frontend

The two projects stay in separate folders and run independently. **Start the backend first.**

| | Backend (this folder) | Frontend (`Disaster Response-frontend`) |
|---|---|---|
| Install | `pip install -r requirements.txt` | `npm install` |
| Configure | `.env` (see [Configuration](#configuration-env)) | `.env` with `VITE_API_BASE_URL=http://127.0.0.1:5000/api` |
| First run | `flask --app run.py db upgrade` and `flask --app run.py seed` | — |
| Start | `python run.py` → http://127.0.0.1:5000 | `npm run dev` → http://localhost:5173 |

Open http://localhost:5173 and sign in with a demo account, for example `coordinator@drrc.local` / `Password@123`.

How the two sides fit together:

- **CORS.** The defaults already allow `http://localhost:5173` and `http://127.0.0.1:5173`. Set `CORS_ORIGINS` if the frontend is served from anywhere else.
- **Authentication.** The frontend stores the access and refresh tokens and sends `Authorization: Bearer <token>`. On a `401` it refreshes once through `POST /api/auth/refresh`; if that fails it sends the user back to the login page. Logout revokes both tokens.
- **Data shapes.** The frontend translates this API's snake_case fields and integer ids into its own shapes in a single module (`src/services/adapters.js`). The API contract is unchanged.
- **Data access.** The browser never touches SQLite or MongoDB; everything goes through this API.

## Docker

```bash
cp .env.example .env
# In .env: set APP_ENV=production and strong SECRET_KEY / JWT_SECRET_KEY values (32+ random characters).
# Optional: SEED_DEMO_DATA=true to load demo data on first start.
docker compose up --build -d
curl http://localhost:5000/api/health
```

- docker-compose needs the `.env` file to exist.
- The container runs as a non-root user and applies migrations at start-up (`flask db upgrade`).
- It serves the API with Gunicorn and includes a health check.
- The SQLite database lives in the named volume `drrc_data`, mounted at `/app/instance`, so data survives restarts and rebuilds.
- Compose also starts a `mongo` (MongoDB 8.0) container with its data in the `drrc_mongo` volume. It isn't published to the host; only the API container can reach it.
- In production the app refuses to start with missing or placeholder secrets.

Useful commands: `docker compose logs -f api`, `docker compose down` (keeps data), `docker compose down -v` (**deletes** both volumes).

## Backups

All data lives in two places: the SQLite file and the MongoDB snapshots.

**Local development**

```bash
# Stop the API first, then:
copy instance\disaster_response.db backup\disaster_response.db                      # Windows (cp on macOS/Linux)
mongodump --uri "mongodb://localhost:27017/disaster_response" --out backup/
```

**Docker**

```bash
docker compose cp api:/app/instance/disaster_response.db ./backup/disaster_response.db
docker compose exec -T mongo mongodump --db disaster_response --archive > ./backup/mongo.archive
```

**Restore:** put the `.db` file back while the API is stopped, then restore MongoDB with `mongorestore --uri "mongodb://localhost:27017" backup/` (local) or `docker compose exec -T mongo mongorestore --archive < ./backup/mongo.archive` (Docker).

## Jenkins CI/CD

The [Jenkinsfile](Jenkinsfile) is a declarative pipeline. It needs a Linux agent with Python 3.12, Docker (with the compose plugin) and the JUnit plugin.

| Stage | What it does |
|---|---|
| Checkout | `checkout scm` |
| Install Dependencies | Creates a virtualenv and installs `requirements-dev.txt` |
| Run Tests | Runs Pytest with JUnit XML and coverage (XML and HTML). Results are published even when tests fail. |
| Generate Test Reports | Writes a summary of test counts and coverage, and archives `reports/**` |
| Build Docker Image | Builds `disaster-response-backend:<build>` and `:latest` |
| Deployment Preparation | Validates `docker-compose.yml`, smoke-tests the image (migrations and the health endpoint), records the image tag, and pushes to `$DOCKER_REGISTRY` if that variable is set |

## Troubleshooting

| Problem | Fix |
|---|---|
| `RuntimeError: Production requires strong secrets` | Set `SECRET_KEY` and `JWT_SECRET_KEY` to 32+ random characters, or use `APP_ENV=development` locally |
| `no such table: users` | Run `flask --app run.py db upgrade` |
| Login fails for the demo accounts | Run `flask --app run.py seed`, or check `SEED_DEFAULT_PASSWORD` |
| Saved reports return `503` | MongoDB isn't running or `MONGO_URI` is wrong; check `GET /api/health` |
| Browser shows a CORS error | Add the frontend's exact origin (scheme, host and port) to `CORS_ORIGINS` and restart |
| Everyone was logged out | `JWT_SECRET_KEY` changed, so old tokens are no longer valid; sign in again |
| Port 5000 is already in use | Stop the other process, or start with `PORT=5001` and update the frontend's `VITE_API_BASE_URL` |
| `Activate.ps1 cannot be loaded` (PowerShell) | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again |
