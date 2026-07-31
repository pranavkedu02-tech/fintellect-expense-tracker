"""
Sends a weekly spending summary email to every user who has expenses
in the last 7 days. Run manually with:

    python manage.py send_weekly_summaries

In a real deployment, this would be scheduled to run automatically
once a week (e.g., via Windows Task Scheduler, cron, or a hosting
platform's scheduled jobs feature) — Django itself has no built-in
scheduler, so an external trigger is the standard approach.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from expenses.db import expenses_collection
from expenses.email_utils import send_email


class Command(BaseCommand):
    help = "Sends weekly spending summary emails to all users with recent activity."

    def handle(self, *args, **options):
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        today_str = datetime.now().strftime("%Y-%m-%d")

        sent_count = 0

        for user in User.objects.all():
            user_id = str(user.id)

            pipeline = [
                {"$match": {
                    "user_id": user_id,
                    "date": {"$gte": seven_days_ago, "$lte": today_str},
                }},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            ]
            result = list(expenses_collection.aggregate(pipeline))

            if not result:
                continue  # no expenses this week, skip this user

            total = result[0]["total"]
            count = result[0]["count"]

            category_pipeline = [
                {"$match": {
                    "user_id": user_id,
                    "date": {"$gte": seven_days_ago, "$lte": today_str},
                }},
                {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
                {"$sort": {"total": -1}},
                {"$limit": 1},
            ]
            top_category_result = list(expenses_collection.aggregate(category_pipeline))
            top_category = top_category_result[0]["_id"] if top_category_result else "N/A"

            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
                <h2 style="color: #059669;">📊 Your Weekly Spending Summary</h2>
                <p>Hi {user.username}, here's what happened this past week:</p>
                <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                    <tr><td style="padding: 6px 0; color: #666;">Total spent:</td><td style="text-align: right;"><strong>₹{total:.2f}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Expenses logged:</td><td style="text-align: right;"><strong>{count}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Top category:</td><td style="text-align: right;"><strong>{top_category}</strong></td></tr>
                </table>
                <p>Log in to Fintellect to see the full breakdown and your AI-generated insights.</p>
            </div>
            """

            if send_email(user.email, "📊 Your Weekly Spending Summary", html):
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"Sent summary to {user.username}"))
            else:
                self.stdout.write(self.style.WARNING(f"Failed to send to {user.username}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Sent {sent_count} weekly summary email(s)."))