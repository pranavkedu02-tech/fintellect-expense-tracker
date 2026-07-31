from groq import Groq
from django.conf import settings
from .db import expenses_collection
from datetime import datetime


def build_spending_summary(user_id):
    """
    Runs the same kind of aggregation pipelines used in the dashboard,
    and packages the results into a compact text summary. This summary
    is what gets sent to the AI — the AI never touches MongoDB directly.
    """
    # Total spent
    total_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    total_result = list(expenses_collection.aggregate(total_pipeline))
    total_spent = total_result[0]["total"] if total_result else 0

    # Spending by category
    category_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    category_totals = list(expenses_collection.aggregate(category_pipeline))

    # Spending by date
    date_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$date", "total": {"$sum": "$amount"}}},
        {"$sort": {"_id": 1}},
    ]
    date_totals = list(expenses_collection.aggregate(date_pipeline))

    # Most recent expenses (for specific questions like "what did I last buy")
    recent = list(expenses_collection.find({"user_id": user_id}).sort("date", -1).limit(10))

    # ---- Build a plain-text summary ----
    if total_spent == 0 and not category_totals:
        return "This user has no expenses recorded yet."

    lines = [f"Total spent overall: ₹{total_spent:.2f}", ""]

    lines.append("Spending by category:")
    for c in category_totals:
        lines.append(f"- {c['_id']}: ₹{c['total']:.2f} ({c['count']} expenses)")

    lines.append("")
    lines.append("Spending by date:")
    for d in date_totals:
        lines.append(f"- {d['_id']}: ₹{d['total']:.2f}")

    lines.append("")
    lines.append("10 most recent expenses:")
    for e in recent:
        lines.append(f"- {e['date']}: {e['title']} — ₹{e['amount']} ({e['category']})")

    return "\n".join(lines)


def ask_ai_about_expenses(user_id, question):
    """
    Sends the user's spending summary + their question to Groq's API
    (running Llama), and returns a natural-language answer based only
    on that data.
    """
    if not settings.GROQ_API_KEY:
        return "AI Assistant isn't configured yet — missing API key in .env."

    summary = build_spending_summary(user_id)

    client = Groq(api_key=settings.GROQ_API_KEY, timeout=60.0)

    system_prompt = (
        "You are a helpful financial assistant inside an expense tracker app. "
        "Answer the user's question using ONLY the spending data provided below. "
        "Be concise and friendly. If the data doesn't contain enough information "
        "to answer, say so honestly instead of guessing.\n\n"
        f"USER'S SPENDING DATA:\n{summary}"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=300,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )

    return response.choices[0].message.content


def generate_spending_insight(user_id):
    """
    Asks the AI to write a short, natural-language summary of the
    user's spending patterns, based on the same aggregated data used
    by the chat assistant.
    """
    if not settings.GROQ_API_KEY:
        return None

    summary = build_spending_summary(user_id)

    if "no expenses recorded yet" in summary.lower():
        return None

    client = Groq(api_key=settings.GROQ_API_KEY, timeout=30.0)

    prompt = (
        "Based on the spending data below, write a short 2-3 sentence "
        "insight for the user. Mention their biggest spending category, "
        "and one observation or friendly tip. Keep it conversational, "
        "not robotic. Do not use markdown formatting.\n\n"
        f"{summary}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception:
        return None
    
def recommend_budget(user_id):
    """
    Asks the AI to suggest a realistic monthly budget number based on
    the user's spending history. Returns just a number (float) so it
    can be dropped straight into the budget form, or None if it can't
    be determined.
    """
    if not settings.GROQ_API_KEY:
        return None

    summary = build_spending_summary(user_id)

    if "no expenses recorded yet" in summary.lower():
        return None

    client = Groq(api_key=settings.GROQ_API_KEY, timeout=30.0)

    prompt = (
        "Based on the spending data below, suggest a realistic monthly "
        "budget for this user. Respond with ONLY a number (no currency "
        "symbol, no words, no explanation) — for example: 8500\n\n"
        f"{summary}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()

        # Extract just the numeric part, in case the AI adds extra text anyway
        import re
        match = re.search(r"[\d,]+\.?\d*", raw)
        if match:
            return float(match.group().replace(",", ""))
        return None
    except Exception:
        return None
    

def parse_expense_from_text(text):
    """
    Sends a natural-language sentence to the AI and asks it to extract
    structured expense data as JSON. Returns a dict with title, amount,
    category, and date — or None if parsing fails.
    """
    if not settings.GROQ_API_KEY or not text.strip():
        return None

    client = Groq(api_key=settings.GROQ_API_KEY, timeout=30.0)

    today_str = datetime.now().strftime("%Y-%m-%d")

    prompt = (
        f"Today's date is {today_str}. Extract expense details from this sentence: "
        f'"{text}"\n\n'
        "Respond with ONLY valid JSON in this exact format, no other text:\n"
        '{"title": "short title", "amount": 000.00, "category": "one of: '
        'Food, Transport, Shopping, Bills, Other", "date": "YYYY-MM-DD"}\n\n'
        "If a relative date like 'yesterday' or 'today' is mentioned, convert it to "
        "an actual date based on today's date. If no date is mentioned, use today's date. "
        "If no amount is mentioned, use 0."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences, in case the model wraps the JSON in ```json ... ```
        raw = raw.replace("```json", "").replace("```", "").strip()

        import json
        parsed = json.loads(raw)

        # Basic validation — make sure all expected keys exist
        required_keys = {"title", "amount", "category", "date"}
        if not required_keys.issubset(parsed.keys()):
            return None

        valid_categories = ["Food", "Transport", "Shopping", "Bills", "Other"]
        if parsed["category"] not in valid_categories:
            parsed["category"] = "Other"

        return parsed
    except Exception:
        return None
    

def generate_month_summary(user_id, month_str, month_expenses, category_totals, total):
    """
    Generates an AI narrative summary for a specific month, based on
    that month's actual data. Used by the Monthly History feature.
    """
    if not settings.GROQ_API_KEY or not month_expenses:
        return None

    lines = [f"Month: {month_str}", f"Total spent: ₹{total:.2f}", ""]
    lines.append("Spending by category:")
    for c in category_totals:
        lines.append(f"- {c['category']}: ₹{c['total']:.2f}")
    lines.append("")
    lines.append("Expenses this month:")
    for e in month_expenses[:15]:
        lines.append(f"- {e['title']}: ₹{e['amount']} ({e['category']})")

    summary_text = "\n".join(lines)

    client = Groq(api_key=settings.GROQ_API_KEY, timeout=30.0)

    prompt = (
        "Write a short 2-3 sentence summary of this month's spending. "
        "Mention the total, the biggest category, and one friendly observation "
        "or tip. Keep it conversational. Do not use markdown formatting.\n\n"
        f"{summary_text}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception:
        return None
    