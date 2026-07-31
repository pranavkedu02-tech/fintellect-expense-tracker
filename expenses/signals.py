"""
Listens for Django's built-in user_logged_in signal and records login
activity (timestamp + IP address) into MongoDB, so we can display it
on the user's profile page.
"""
from datetime import datetime
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .db import users_collection


def get_client_ip(request):
    """Extracts the real client IP, accounting for proxies/load balancers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "Unknown")


@receiver(user_logged_in)
def record_login_activity(sender, request, user, **kwargs):
    ip_address = get_client_ip(request)
    login_time = datetime.now()

    try:
        users_collection.update_one(
            {"user_id": str(user.id)},
            {
                "$set": {
                    "last_login_time": login_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_login_ip": ip_address,
                },
                "$push": {
                    "login_history": {
                        "$each": [{
                            "time": login_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "ip": ip_address,
                        }],
                        "$slice": -10,  # keep only the 10 most recent logins
                    }
                },
            },
            upsert=True,
        )
    except Exception as e:
        print("Warning: could not record login activity:", e)