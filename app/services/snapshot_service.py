"""Situation-report snapshots stored in MongoDB.

A snapshot freezes the consolidated situation report (``report_service.summary()``)
at a moment in time, so briefings can be compared later even though the live
figures keep changing. Each snapshot is one self-contained document.
"""
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from ..mongo import ServiceUnavailableError, get_db
from ..utils.errors import NotFoundError
from ..utils.time import isoformat, utcnow
from . import report_service
from .activity_service import log_activity
from .common import atomic

COLLECTION = "situation_reports"


def _collection():
    return get_db()[COLLECTION]


def _object_id(snapshot_id):
    try:
        return ObjectId(snapshot_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Situation report not found", {"id": f"No situation report with id {snapshot_id}"}) from None


def _mongo_call(fn):
    try:
        return fn()
    except PyMongoError:
        raise ServiceUnavailableError(
            "The document store (MongoDB) is not reachable",
            {"mongodb": "Check that the MongoDB server is running"},
        ) from None


def _highlights(summary):
    dash = summary["dashboard"]
    return {
        "total_incidents": dash["total_incidents"],
        "active_incidents": dash["active_incidents"],
        "critical_incidents": dash["critical_incidents"],
        "pending_requests": dash["pending_requests"],
        "available_teams": dash["available_teams"],
        "active_allocations": dash["active_allocations"],
        "available_shelter_beds": dash["available_shelter_beds"],
        "people_affected": summary["incidents"]["affected_people"],
    }


def serialize(doc, include_data=False):
    out = {
        "id": str(doc["_id"]),
        "title": doc["title"],
        "notes": doc.get("notes"),
        "created_at": isoformat(doc["created_at"]),
        "created_by": doc.get("created_by"),
        "generated_at": doc.get("generated_at"),
        "highlights": doc.get("highlights", {}),
    }
    if include_data:
        out["data"] = doc["data"]
    return out


def create_snapshot(data, actor):
    collection = _collection()
    summary = report_service.summary()
    doc = {
        "title": data["title"],
        "notes": data.get("notes"),
        "created_at": utcnow(),
        "created_by": {**actor.to_summary(), "role": actor.role},
        "generated_at": summary["generated_at"],
        "highlights": _highlights(summary),
        "data": summary,
    }
    inserted_id = _mongo_call(lambda: collection.insert_one(doc).inserted_id)
    try:
        with atomic():
            log_activity(
                actor, "SITUATION_REPORT_SAVED", "situation_report", None,
                f"Situation report saved: {doc['title']}", {"snapshot_id": str(inserted_id)},
            )
    except Exception:
        # Keep both stores consistent: no snapshot without its audit entry.
        _mongo_call(lambda: collection.delete_one({"_id": inserted_id}))
        raise
    return serialize(doc)


def list_snapshots(page, per_page):
    collection = _collection()

    def query():
        total = collection.count_documents({})
        cursor = (
            collection.find({}, {"data": 0})
            .sort("created_at", DESCENDING)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        return total, [serialize(d) for d in cursor]

    total, items = _mongo_call(query)
    return {
        "items": items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": -(-total // per_page)},
    }


def get_snapshot(snapshot_id):
    oid = _object_id(snapshot_id)
    doc = _mongo_call(lambda: _collection().find_one({"_id": oid}))
    if doc is None:
        raise NotFoundError("Situation report not found", {"id": f"No situation report with id {snapshot_id}"})
    return serialize(doc, include_data=True)


def delete_snapshot(snapshot_id, actor):
    snapshot = get_snapshot(snapshot_id)
    _mongo_call(lambda: _collection().delete_one({"_id": ObjectId(snapshot["id"])}))
    with atomic():
        log_activity(
            actor, "SITUATION_REPORT_DELETED", "situation_report", None,
            f"Situation report deleted: {snapshot['title']}", {"snapshot_id": snapshot["id"]},
        )
