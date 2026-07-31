"""
Makes the pending split-request count available in every template
automatically, without needing to pass it manually in every view.
"""
from .db import split_requests_collection


def pending_splits(request):
    if not request.user.is_authenticated:
        return {"pending_split_count": 0}

    count = split_requests_collection.count_documents({
        "to_user_id": str(request.user.id),
        "status": "pending",
    })
    return {"pending_split_count": count}