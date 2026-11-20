"""Domain vocabularies shared by models, validation and business rules."""


class Role:
    ADMIN = "admin"
    OPERATOR = "control_room_operator"
    TEAM_LEAD = "response_team_lead"
    COORDINATOR = "relief_coordinator"

    ALL = (ADMIN, OPERATOR, TEAM_LEAD, COORDINATOR)
    SELF_REGISTERABLE = (OPERATOR, TEAM_LEAD, COORDINATOR)


INCIDENT_TYPES = ("Flood", "Earthquake", "Fire", "Cyclone", "Building Collapse", "Other")
SEVERITIES = ("Low", "Medium", "High", "Critical")

INCIDENT_STATUSES = ("Reported", "Active", "In Progress", "Completed", "Closed")
ACTIVE_INCIDENT_STATUSES = ("Reported", "Active", "In Progress")
CLOSED_INCIDENT_STATUSES = ("Completed", "Closed")

REQUEST_CATEGORIES = (
    "Medical Assistance",
    "Food",
    "Drinking Water",
    "Rescue",
    "Shelter",
    "Transportation",
    "Other",
)
PRIORITIES = SEVERITIES
REQUEST_STATUSES = ("Pending", "In Progress", "Completed", "Cancelled")
OPEN_REQUEST_STATUSES = ("Pending", "In Progress")

TEAM_TYPES = ("Rescue", "Medical", "Fire", "Search and Rescue", "Logistics", "Other")
TEAM_AVAILABILITY = ("Available", "Assigned", "Busy", "Unavailable")

SHELTER_STATUSES = ("Open", "Full", "Closed", "Under Maintenance")
ACTIVE_SHELTER_STATUSES = ("Open", "Full")

SUPPLY_CATEGORIES = (
    "Food",
    "Drinking Water",
    "Medicine",
    "Clothing",
    "Rescue Equipment",
    "Other",
)

INVENTORY_TX_TYPES = ("Initial Stock", "Restock", "Adjustment", "Reserved", "Released", "Dispatched")

RESOURCE_TYPES = ("Team", "Supply", "Shelter")
ALLOCATION_STATUSES = ("Pending", "Approved", "Allocated", "Completed", "Cancelled")
ACTIVE_ALLOCATION_STATUSES = ("Pending", "Approved", "Allocated")
ALLOCATION_TRANSITIONS = {
    "Pending": ("Approved", "Cancelled"),
    "Approved": ("Allocated", "Cancelled"),
    "Allocated": ("Completed", "Cancelled"),
    "Completed": (),
    "Cancelled": (),
}

DISPATCH_STATUSES = ("Prepared", "Dispatched", "In Transit", "Delivered", "Completed")
IN_FLIGHT_DISPATCH_STATUSES = ("Dispatched", "In Transit")
DISPATCH_TRANSITIONS = {
    "Prepared": ("Dispatched",),
    "Dispatched": ("In Transit", "Delivered"),
    "In Transit": ("Delivered",),
    "Delivered": ("Completed",),
    "Completed": (),
}
