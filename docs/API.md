# API Reference — Disaster Response Resource Coordinator

Base URL: `http://localhost:5000/api`

All requests and responses are JSON. Protected endpoints need an access token in the header:

```
Authorization: Bearer <access_token>
```

## Response format

Success:

```json
{ "success": true, "message": "Incident created successfully", "data": { } }
```

Error:

```json
{ "success": false, "message": "Invalid incident information", "errors": { "severity": "Must be one of: Low, Medium, High, Critical." } }
```

| Status | Meaning |
|---|---|
| 200 | Success |
| 201 | Created |
| 400 | Validation error (field-level details in `errors`) |
| 401 | Missing, invalid, expired or revoked token |
| 403 | Authenticated, but the role is not allowed to do this |
| 404 | Resource not found |
| 409 | Business-rule conflict (insufficient stock, team unavailable, invalid status change, duplicate…) |
| 500 | Internal error (details are logged on the server, never returned) |

### Lists and pagination

Every list endpoint returns:

```json
{ "items": [ ], "pagination": { "page": 1, "per_page": 20, "total": 42, "pages": 3 } }
```

Query parameters: `page` (default 1) and `per_page` (default 20, max 100), plus the filters listed for each endpoint. Filter values are validated, so an unknown status returns 400.

## Roles

| Key | Role |
|---|---|
| `admin` | Administrator: can use every endpoint |
| `control_room_operator` | Control Room Operator |
| `response_team_lead` | Response Team Lead |
| `relief_coordinator` | Relief Coordinator |

The server reads the role from the database on every request. A role change or deactivation therefore takes effect immediately, even for tokens that were already issued. **Admin** passes every role check below.

Abbreviations in the tables: **OP** operator, **TL** team lead, **RC** relief coordinator, **ALL** any authenticated user.

---

## Authentication — `/api/auth`

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/auth/register` | public | Register an account. `admin` cannot self-register. |
| POST | `/auth/login` | public | Returns `access_token`, `refresh_token` and `user` |
| POST | `/auth/refresh` | refresh token | Issues a new access token |
| GET | `/auth/profile` | ALL | Current user's profile |
| PUT | `/auth/profile` | ALL | Update `full_name`, `email`, `phone`; to change `password`, also send `current_password` |
| POST | `/auth/logout` | ALL | Revokes the token that was sent |

**Register**

```json
POST /api/auth/register
{
  "username": "ravi",                 // 3-80 chars: letters, digits, . _ -
  "email": "ravi@example.org",
  "full_name": "Ravi Kumar",
  "password": "Secure123",            // min 8 chars, at least one letter and one digit
  "phone": "+91 98400 12345",         // optional
  "role": "relief_coordinator"        // optional, default control_room_operator
}
```

**Login.** Send `username` (or `email`) and `password`. Bad credentials return 401. A deactivated account returns 403.

## User management — `/api/users` (admin only)

| Method | Path | Description |
|---|---|---|
| GET | `/users` | Filters: `role`, `is_active=true/false`, `search` |
| POST | `/users` | Create a user with any role. Same fields as register, plus `is_active` |
| GET | `/users/<id>` | User details |
| PUT | `/users/<id>` | Update `username`, `email`, `full_name`, `phone`, `role`, `is_active`, `password` (reset) |
| DELETE | `/users/<id>` | Deactivate the account (soft delete, so history stays intact) |
| GET | `/activity-logs` | System audit trail. Filters: `entity_type`, `action`, `user_id`, `entity_id` |

Admins cannot demote or deactivate their own account (409).

---

## Incidents — `/api/incidents`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/incidents` | OP | Register an incident |
| GET | `/incidents` | ALL | Filters: `status`, `severity`, `incident_type`, `active=true`, `search`, `assigned=true`. **TL only sees incidents assigned to their teams.** |
| GET | `/incidents/<id>` | ALL (TL: assigned only) | Includes the incident's `requests` and `allocations` |
| PUT | `/incidents/<id>` | OP | Partial update |
| DELETE | `/incidents/<id>` | admin | Not allowed once resources have been allocated (409). Close the incident instead. |

Fields:

| Field | Type | Rules |
|---|---|---|
| `title` | string | required, 3-200 |
| `incident_type` | enum | required: `Flood`, `Earthquake`, `Fire`, `Cyclone`, `Building Collapse`, `Other` |
| `description` | string | required |
| `location` | string | required |
| `latitude` / `longitude` | number | optional, valid coordinates |
| `severity` | enum | `Low`, `Medium` (default), `High`, `Critical` |
| `status` | enum | `Reported` (default), `Active`, `In Progress`, `Completed`, `Closed` |
| `affected_people` | int | ≥ 0 |

Read-only fields: `id`, `reported_by`, `reporter`, `resolved_at`, `created_at`, `updated_at`.

Rules:

- New incidents cannot start as `Completed`/`Closed`.
- An incident cannot be marked `Completed`/`Closed` while it has active allocations (409).
- Setting a completed incident back to an active status reopens it: `resolved_at` is cleared and the change is logged as `INCIDENT_REOPENED`.

## Emergency requests — `/api/requests`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/requests` | OP | Must reference an open incident |
| GET | `/requests` | ALL (TL: assigned incidents only) | Filters: `status`, `priority`, `category`, `incident_id` |
| GET | `/requests/<id>` | ALL (TL: assigned only) | |
| PUT | `/requests/<id>` | OP, RC, TL | TL may only change `status` and `completion_notes`, and only on assigned incidents |
| DELETE | `/requests/<id>` | OP | Not allowed while active allocations reference the request (409) |

Fields:

| Field | Type | Rules |
|---|---|---|
| `incident_id` | int | required |
| `category` | enum | required: `Medical Assistance`, `Food`, `Drinking Water`, `Rescue`, `Shelter`, `Transportation`, `Other` |
| `description` | string | required |
| `priority` | enum | `Low`, `Medium` (default), `High`, `Critical` |
| `people_affected` | int | ≥ 0 |
| `quantity_requested` | int | optional, > 0 |
| `location` | string | optional; defaults to the incident's location |
| `contact_name`, `contact_phone` | string | optional |

Update-only fields: `status` (`Pending`, `In Progress`, `Completed`, `Cancelled`) and `completion_notes`.

- Setting `Completed` records `completed_at`.
- Allocating resources against a `Pending` request moves it to `In Progress` automatically.

## Response teams — `/api/teams`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/teams` | TL | A TL is set as the lead of the team they create. Admins may set `lead_id`. |
| GET | `/teams` | ALL | Filters: `availability`, `team_type`, `mine=true` |
| GET | `/teams/available` | ALL | Teams with `Available` status |
| GET | `/teams/<id>` | ALL | Includes `active_allocation` and `assignment_history` |
| PUT | `/teams/<id>` | TL (own teams only) | Only an admin can change `lead_id` |
| DELETE | `/teams/<id>` | admin | Not allowed once the team has allocation or dispatch history (409) |
| GET | `/teams/<id>/activities` | ALL | Activity log for the team |
| POST | `/teams/<id>/activities` | TL (own) | Record progress. Body: `{ "activity": "...", "incident_id": 1, "notes": "..." }` |

Fields:

| Field | Type | Rules |
|---|---|---|
| `name` | string | required, unique |
| `team_type` | enum | required: `Rescue`, `Medical`, `Fire`, `Search and Rescue`, `Logistics`, `Other` |
| `member_count` | int | required, ≥ 1 |
| `contact_phone`, `base_location`, `equipment` | string | optional |
| `lead_id` | int | optional; must be an active team-lead account |
| `availability` | enum | `Available`, `Assigned`, `Busy`, `Unavailable` |

How availability changes:

- **Allocation created:** `Available` → `Assigned`. A team that is not `Available` cannot be assigned (409).
- **Team dispatched:** becomes `Busy`.
- **Allocation completed or cancelled:** back to `Available`.
- **Manual changes:** `Assigned` cannot be set by hand. A team with an active assignment cannot be set to `Available` or `Unavailable`.

## Shelters — `/api/shelters`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/shelters` | RC | |
| GET | `/shelters` | ALL | Filters: `status`, `min_available_beds` |
| GET | `/shelters/available` | ALL | `Open` shelters with free beds |
| GET | `/shelters/<id>` | ALL | |
| PUT | `/shelters/<id>` | RC | Partial update |
| DELETE | `/shelters/<id>` | RC | Not allowed while occupied or once allocations exist (409) |

Fields:

| Field | Type | Rules |
|---|---|---|
| `name` | string | required, unique |
| `location` | string | required |
| `capacity` | int | required, > 0 |
| `current_occupancy` | int | 0 ≤ occupancy ≤ capacity |
| `status` | enum | `Open`, `Full`, `Closed`, `Under Maintenance` |
| `contact_person`, `contact_phone`, `facilities` | string | optional |

Computed fields: `available_beds`, `occupancy_rate` (%).

- Occupancy above capacity is rejected (400). This applies to direct edits and to shrinking `capacity`. The database enforces the same rule with a CHECK constraint.
- `Open` and `Full` switch automatically as occupancy changes.

## Relief supplies — `/api/supplies`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/supplies` | RC | |
| GET | `/supplies` | ALL | Filter: `category` |
| GET | `/supplies/low-stock` | ALL | Items where available ≤ `low_stock_threshold` |
| GET | `/supplies/<id>` | ALL | |
| GET | `/supplies/<id>/history` | RC | Inventory transaction history |
| PUT | `/supplies/<id>` | RC | Details. Change stock with `quantity` (absolute) **or** `restock_quantity` (amount to add). Optional `adjustment_note`. |
| DELETE | `/supplies/<id>` | RC | Not allowed once allocations exist (409) |

Fields:

| Field | Type | Rules |
|---|---|---|
| `name` | string | required, unique |
| `category` | enum | required: `Food`, `Drinking Water`, `Medicine`, `Clothing`, `Rescue Equipment`, `Other` |
| `unit` | string | default `units` |
| `quantity` | int | required, ≥ 0 |
| `low_stock_threshold` | int | ≥ 0, default 10 |
| `warehouse_location`, `description` | string | optional |

Computed fields:

| Field | Meaning |
|---|---|
| `reserved_quantity` | Held by active allocations |
| `available_quantity` | `quantity − reserved` |
| `dispatched_quantity` | Total that has left the warehouse so far |
| `is_low_stock` | `true` when available ≤ threshold |
| `low_stock_warning` | Warning text when stock is low |

History transaction types: `Initial Stock`, `Restock`, `Adjustment`, `Reserved`, `Released`, `Dispatched`.

Stock can never become negative. It also cannot be reduced below the reserved quantity (409).

## Resource allocations — `/api/allocations`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/allocations` | RC (all types), OP (`Team` only) | |
| GET | `/allocations` | ALL (TL: own teams only) | Filters: `status`, `resource_type`, `incident_id`, `team_id`, `supply_id`, `shelter_id`, `request_id` |
| GET | `/allocations/<id>` | ALL | Includes `dispatches` |
| PUT | `/allocations/<id>` | RC, OP (team allocations), TL (own team: only `progress_notes` and `status: Completed`) | |

Create:

```json
POST /api/allocations
{ "incident_id": 1, "resource_type": "Supply", "supply_id": 3, "quantity": 500, "request_id": 4, "notes": "..." }
{ "incident_id": 1, "resource_type": "Team",   "team_id": 2 }
{ "incident_id": 1, "resource_type": "Shelter","shelter_id": 1, "quantity": 120 }
```

- `resource_type` is `Team`, `Supply` or `Shelter`.
- Set exactly the matching id field.
- `quantity` is required for Supply (units) and Shelter (people). For a Team it is set to the team's size.

Update fields: `status`, `quantity` (only while `Pending`/`Approved`), `request_id`, `notes`, `progress_notes`, `cancellation_reason`.

Status workflow:

```
Pending ──► Approved ──► Allocated ──► Completed
   │           │            │
   └───────────┴────────────┴──► Cancelled
```

What creating an allocation does (all in one transaction, so it fully succeeds or fully fails):

| Resource | Validation | Effect |
|---|---|---|
| Team | Team must be `Available` and not already assigned | Team becomes `Assigned` |
| Supply | `quantity` ≤ available stock | Reserves the stock |
| Shelter | Shelter must be `Open` with enough free beds | Adds to occupancy |

Rejected with 409:

- An allocation for an incident that is `Completed`/`Closed`. Reopen the incident first.
- A duplicate: an active allocation of the same resource to the same incident already exists. Update that allocation instead.
- An invalid status transition.

Completing an allocation:

- Not allowed while any dispatch is still `Prepared`, `Dispatched` or `In Transit`.
- Releases the team and returns any reserved stock that was never dispatched.

Cancelling an allocation:

- Releases the team, the reserved stock or the shelter beds.
- Not allowed once dispatch records exist. Delete `Prepared` dispatches first.

## Dispatch — `/api/dispatch`

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/dispatch` | RC | Create a dispatch record (status `Prepared`) |
| GET | `/dispatch` | ALL (TL: their teams only) | Filters: `status`, `allocation_id`, `team_id`, `incident_id` |
| GET | `/dispatch/<id>` | ALL (TL: their teams only) | |
| PUT | `/dispatch/<id>` | RC; TL for their teams (only `In Transit`/`Delivered`/`Completed` and notes) | |
| DELETE | `/dispatch/<id>` | RC | Only while `Prepared` |

Create:

```json
POST /api/dispatch
{
  "allocation_id": 5,          // required; the allocation must be Approved or Allocated
  "quantity": 200,             // optional; defaults to the remaining undispatched quantity
  "team_id": 3,                // optional delivery team (not Unavailable); for team allocations, the allocated team
  "origin": "Central Warehouse",
  "destination": "Ward 4",     // defaults to the incident (or shelter) location
  "vehicle_details": "Truck TN-01-4521",
  "notes": "..."
}
```

Status workflow (forward only):

```
Prepared ──► Dispatched ──► In Transit ──► Delivered ──► Completed
                  └──────────────────────────►┘
```

Each step records a timestamp: `dispatched_at`, `in_transit_at`, `delivered_at`, `completed_at`. `completion_notes` holds the completion details.

- **Inventory is deducted on `Dispatched`.** At that point the stock moves from reserved to dispatched, an inventory transaction is written, and a low-stock warning is logged when the item runs low.
- The first dispatch moves an `Approved` allocation to `Allocated`.
- Dispatching a team allocation sets that team to `Busy`.
- The total dispatched quantity can never exceed the allocated quantity.
- `quantity` and `team_id` can only be edited while the dispatch is `Prepared`.
- When every unit of a Supply or Shelter allocation has been dispatched and those dispatches are `Completed`, the allocation becomes `Completed` automatically.

---

## Reports — `/api/reports`

| Method | Path | Access | Contents |
|---|---|---|---|
| GET | `/reports/dashboard` | ALL | Live counts (see below) |
| GET | `/reports/incidents` | ALL | Counts by type, severity and status; affected people; request counts by category, status and priority; active critical incidents; 10 most recent incidents |
| GET | `/reports/resources` | ALL | Per-supply stock and `utilization_rate`; totals by category; low-stock items; allocations by status and type; dispatches by status |
| GET | `/reports/shelters` | ALL | Capacity, occupancy, free beds and occupancy rate per shelter and in total |
| GET | `/reports/teams` | ALL | Teams by availability and type; availability rate; personnel; completed assignments per team |

`/reports/dashboard` returns:

- **Incidents:** `total_incidents`, `active_incidents`, `critical_incidents`
- **Requests:** `pending_requests`, `open_requests`
- **Teams:** `available_teams`, `total_teams`
- **Shelters:** `active_shelters`, `available_shelter_beds`
- **Supplies:** `total_available_supplies`, `supply_items`, `low_stock_items`
- **Operations:** `active_allocations`, `dispatched_resources`, `dispatched_quantity_total`
- **Completed work:** `completed_operations` (completed allocations, dispatches, requests and incidents)

## Health

`GET /api/health` is public and returns `{"success": true, "data": {"status": "ok"}}`.

## Activity log actions

Each important operation writes an activity log entry with the user, entity, IP address and details of the change:

- **Users:** `USER_REGISTERED`, `USER_CREATED`, `USER_LOGIN`, `USER_LOGOUT`, `USER_UPDATED`, `USER_ROLE_CHANGED`, `USER_DEACTIVATED`, `PROFILE_UPDATED`
- **Incidents:** `INCIDENT_CREATED`, `INCIDENT_UPDATED`, `INCIDENT_STATUS_CHANGED`, `INCIDENT_SEVERITY_CHANGED`, `INCIDENT_REOPENED`, `INCIDENT_DELETED`
- **Requests:** `REQUEST_CREATED`, `REQUEST_UPDATED`, `REQUEST_COMPLETED`, `REQUEST_DELETED`
- **Teams:** `TEAM_CREATED`, `TEAM_UPDATED`, `TEAM_AVAILABILITY_CHANGED`, `TEAM_ACTIVITY`, `TEAM_DELETED`
- **Shelters:** `SHELTER_CREATED`, `SHELTER_UPDATED`, `SHELTER_OCCUPANCY_UPDATED`, `SHELTER_DELETED`
- **Supplies:** `SUPPLY_CREATED`, `SUPPLY_UPDATED`, `SUPPLY_INVENTORY_UPDATED`, `LOW_STOCK_WARNING`, `SUPPLY_DELETED`
- **Allocations:** `ALLOCATION_CREATED`, `ALLOCATION_UPDATED`, `ALLOCATION_STATUS_CHANGED`, `ALLOCATION_PROGRESS_RECORDED`, `ALLOCATION_COMPLETED`
- **Dispatches:** `DISPATCH_CREATED`, `DISPATCH_UPDATED`, `DISPATCH_STATUS_CHANGED`, `DISPATCH_DELETED`
