"""
Sends email notifications for expense reminders due today (or overdue,
and not yet sent). Run manually with:

    python manage.py send_reminder_emails

Like send_weekly_summaries, this needs an external trigger to run on a
schedule in production (cron / hosting platform's scheduled jobs) —
Django itself has no built-in scheduler.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from expenses.db import reminders_collection
from expenses.email_utils import send_email


class Command(BaseCommand):
    help = "Sends email notifications for due expense reminders."

    def handle(self, *args, **options):
        today_str = datetime.now().strftime("%Y-%m-%d")

        due_reminders = list(reminders_collection.find({
            "reminder_date": {"$lte": today_str},
            "sent": False,
        }))

        sent_count = 0

        for reminder in due_reminders:
            try:
                user = User.objects.get(id=int(reminder["user_id"]))
            except User.DoesNotExist:
                continue

            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
                <h2 style="color: #C9A15B;">⏰ Expense Reminder</h2>
                <p>Hi {user.username},</p>
                <p>This is a reminder for an upcoming expense:</p>
                <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                    <tr><td style="padding: 6px 0; color: #666;">Title:</td><td style="text-align: right;"><strong>{reminder['title']}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Amount:</td><td style="text-align: right;"><strong>₹{reminder['amount']:.2f}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Due:</td><td style="text-align: right;"><strong>{reminder['reminder_date']}</strong></td></tr>
                </table>
                {f"<p>{reminder['notes']}</p>" if reminder.get('notes') else ""}
                <p>Log in to Fintellect to log this expense once paid.</p>
            </div>
            """

            if send_email(user.email, f"⏰ Reminder: {reminder['title']}", html):
                reminders_collection.update_one(
                    {"_id": reminder["_id"]},
                    {"$set": {"sent": True}}
                )
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"Sent reminder to {user.username}: {reminder['title']}"))
            else:
                self.stdout.write(self.style.WARNING(f"Failed to send reminder to {user.username}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Sent {sent_count} reminder email(s)."))