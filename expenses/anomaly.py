"""
Statistical anomaly detection for expenses — uses mean and standard
deviation (classical statistics, not machine learning or an LLM) to
flag expenses that are unusually large compared to a user's typical
spending in that category.
"""
import statistics
from .db import expenses_collection


def check_anomaly(user_id, category, amount):
    """
    Compares a given amount against the user's historical spending in
    that category. Returns a dict with anomaly info, or None if there
    isn't enough history yet to judge (need at least 3 past expenses
    in that category for a meaningful comparison).
    """
    past_expenses = list(expenses_collection.find({
        "user_id": user_id,
        "category": category,
    }))

    past_amounts = [e["amount"] for e in past_expenses]

    if len(past_amounts) < 3:
        return None  # not enough history for a meaningful comparison

    avg = statistics.mean(past_amounts)

    # Guard against zero variance (e.g., every past expense was exactly the same amount)
    try:
        std_dev = statistics.stdev(past_amounts)
    except statistics.StatisticsError:
        std_dev = 0

    threshold = avg + (2 * std_dev)

    is_anomaly = amount > threshold and amount > avg  # extra safety check

    return {
        "is_anomaly": is_anomaly,
        "average": round(avg, 2),
        "threshold": round(threshold, 2),
    }