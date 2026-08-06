from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from bson.objectid import ObjectId
from datetime import datetime
import os
import csv
from .email_utils import send_email
from django.contrib import messages
from .anomaly import check_anomaly
from .db import expenses_collection, profiles_collection, users_collection, monthly_summaries_collection, split_requests_collection
from .forms import RegisterForm, ExpenseForm, EditProfileForm, ReceiptUploadForm, BudgetForm, SplitExpenseForm
from django.contrib.auth.models import User


from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .ai_assistant import (
    ask_ai_about_expenses,
    generate_spending_insight,
    recommend_budget,
    parse_expense_from_text,
    generate_month_summary,
)
from .forms import RegisterForm, ExpenseForm, EditProfileForm, ReceiptUploadForm, BudgetForm
from .ocr import extract_text_from_image, guess_amount
from .ml_classifier import predict_category, evaluate_model_accuracy
from .db import expenses_collection, profiles_collection, users_collection, monthly_summaries_collection
from .forms import RegisterForm, ExpenseForm, EditProfileForm, ReceiptUploadForm, BudgetForm, SplitExpenseForm, ReminderForm
from .db import expenses_collection, profiles_collection, users_collection, monthly_summaries_collection, split_requests_collection, reminders_collection

def home_view(request):
    return render(request, "home.html")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()

            try:
                users_collection.insert_one({
                    "user_id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "date_joined": str(user.date_joined),
                })
            except Exception as e:
                print("Warning: could not mirror user to MongoDB:", e)

            # ---- Send welcome email ----
            welcome_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
                <h2 style="color: #059669;">Welcome to Fintellect, {user.username}! 🎉</h2>
                <p>Your account has been created successfully.</p>
                <p>Fintellect helps you track expenses, scan receipts with OCR,
                get AI-powered spending insights, and stay on top of your budget —
                all in one place.</p>
                <p>Log in anytime to get started:</p>
                <p><strong>Username:</strong> {user.username}</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #888; font-size: 0.85rem;">
                    You're receiving this because you just created a Fintellect account.
                </p>
            </div>
            """
            send_email(user.email, "Welcome to Fintellect! 🎉", welcome_html)

            login(request, user)
            return redirect("home")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})


@login_required
def add_expense_view(request):
    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            user_id = str(request.user.id)
            amount = float(form.cleaned_data["amount"])
            category = form.cleaned_data["category"]

            # ---- Check for anomaly BEFORE saving, using existing history ----
            anomaly_result = check_anomaly(user_id, category, amount)

            expenses_collection.insert_one({
                "user_id": user_id,
                "title": form.cleaned_data["title"],
                "amount": amount,
                "category": category,
                "date": str(form.cleaned_data["date"]),
                "is_recurring": form.cleaned_data["is_recurring"],
            })

            if anomaly_result and anomaly_result["is_anomaly"]:
                messages.warning(
                    request,
                    f"⚠ This expense (₹{amount:.0f}) is unusually high for {category} — "
                    f"your average is ₹{anomaly_result['average']:.0f}."
                )
            else:
                messages.success(request, "Expense added!")

            # ---- Check if this expense pushed the user over their budget ----
            check_and_send_budget_alert(user_id, request.user)

            return redirect("home")
    else:
        form = ExpenseForm()

    return render(request, "add_expense.html", {"form": form})


@login_required
def expense_list_view(request):
    user_id = str(request.user.id)
    selected_category = request.GET.get("category", "")
    search_query = request.GET.get("q", "").strip()
    sort_by = request.GET.get("sort", "date_desc")

    query = {"user_id": user_id}
    if selected_category:
        query["category"] = selected_category
    if search_query:
        query["title"] = {"$regex": search_query, "$options": "i"}

    sort_options = {
        "date_desc": ("date", -1),
        "date_asc": ("date", 1),
        "amount_desc": ("amount", -1),
        "amount_asc": ("amount", 1),
    }
    sort_field, sort_direction = sort_options.get(sort_by, ("date", -1))

    all_expenses = list(expenses_collection.find(query).sort(sort_field, sort_direction))
    for expense in all_expenses:
        expense["id"] = str(expense["_id"])

    categories = ["Food", "Transport", "Shopping", "Bills", "Other"]

    return render(request, "expense_list.html", {
        "expenses": all_expenses,
        "categories": categories,
        "selected_category": selected_category,
        "search_query": search_query,
        "sort_by": sort_by,
    })


@login_required
def edit_expense_view(request, expense_id):
    expense = expenses_collection.find_one({"_id": ObjectId(expense_id)})

    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expenses_collection.update_one(
                {"_id": ObjectId(expense_id)},
                {"$set": {
                    "title": form.cleaned_data["title"],
                    "amount": float(form.cleaned_data["amount"]),
                    "category": form.cleaned_data["category"],
                    "date": str(form.cleaned_data["date"]),
                    "is_recurring": form.cleaned_data["is_recurring"],
                }}
            )
            return redirect("expense_list")
    else:
        form = ExpenseForm(initial={
            "title": expense["title"],
            "amount": expense["amount"],
            "category": expense["category"],
            "date": expense["date"],
            "is_recurring": expense.get("is_recurring", False),
        })

    return render(request, "edit_expense.html", {"form": form, "expense_id": expense_id})


@login_required
def delete_expense_view(request, expense_id):
    if request.method == "POST":
        expenses_collection.delete_one({"_id": ObjectId(expense_id)})
        return redirect("expense_list")

    expense = expenses_collection.find_one({"_id": ObjectId(expense_id)})
    return render(request, "delete_expense.html", {"expense": expense})


@login_required
def dashboard_view(request):
    user_id = str(request.user.id)

    total_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    total_result = list(expenses_collection.aggregate(total_pipeline))
    total_spent = total_result[0]["total"] if total_result else 0

    category_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
    ]
    category_totals = list(expenses_collection.aggregate(category_pipeline))

    month_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$date", "total": {"$sum": "$amount"}}},
        {"$sort": {"_id": 1}},
    ]
    monthly_totals = list(expenses_collection.aggregate(month_pipeline))

    profile_doc = profiles_collection.find_one({"user_id": user_id})
    monthly_budget = profile_doc.get("monthly_budget") if profile_doc else None

    budget_percent = 0
    budget_status = "safe"
    if monthly_budget and monthly_budget > 0:
        budget_percent = min(round((total_spent / monthly_budget) * 100), 100)
        if budget_percent >= 100:
            budget_status = "danger"
        elif budget_percent >= 75:
            budget_status = "warning"

    ai_insight = generate_spending_insight(user_id)
    # ---- ML model accuracy (for demonstration/report purposes) ----
    model_accuracy = evaluate_model_accuracy(user_id)

    context = {
        "total_spent": total_spent,
        "ai_insight": ai_insight,
        "model_accuracy": model_accuracy,
        "monthly_budget": monthly_budget,
        "budget_percent": budget_percent,
        "budget_status": budget_status,
        "category_labels": [c["_id"] for c in category_totals],
        "category_values": [c["total"] for c in category_totals],
        "month_labels": [m["_id"] for m in monthly_totals],
        "month_values": [m["total"] for m in monthly_totals],
    }

    return render(request, "dashboard.html", context)


@login_required
def profile_view(request):
    user_id = str(request.user.id)

    total_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    total_result = list(expenses_collection.aggregate(total_pipeline))
    total_spent = total_result[0]["total"] if total_result else 0

    expense_count = expenses_collection.count_documents({"user_id": user_id})

    profile_doc = profiles_collection.find_one({"user_id": user_id})

    # ---- Login activity ----
    user_doc = users_collection.find_one({"user_id": user_id})
    last_login_time = user_doc.get("last_login_time") if user_doc else None
    last_login_ip = user_doc.get("last_login_ip") if user_doc else None
    login_history = list(reversed(user_doc.get("login_history", []))) if user_doc else []

    context = {
        "total_spent": total_spent,
        "expense_count": expense_count,
        "profile_photo": profile_doc["photo"] if profile_doc else None,
        "last_login_time": last_login_time,
        "last_login_ip": last_login_ip,
        "login_history": login_history,
    }
    return render(request, "profile.html", context)



@login_required
def edit_profile_view(request):
    profile_doc = profiles_collection.find_one({"user_id": str(request.user.id)})

    if request.method == "POST":
        form = EditProfileForm(request.POST, request.FILES)
        if form.is_valid():
            request.user.username = form.cleaned_data["username"]
            request.user.email = form.cleaned_data["email"]
            request.user.save()

            users_collection.update_one(
                {"user_id": str(request.user.id)},
                {"$set": {
                    "username": form.cleaned_data["username"],
                    "email": form.cleaned_data["email"],
                }}
            )

            uploaded_photo = form.cleaned_data.get("photo")
            if uploaded_photo:
                filename = f"{request.user.id}_{uploaded_photo.name}"
                save_path = os.path.join(settings.MEDIA_ROOT, "profile_photos", filename)

                with open(save_path, "wb+") as destination:
                    for chunk in uploaded_photo.chunks():
                        destination.write(chunk)

                photo_url = f"profile_photos/{filename}"

                profiles_collection.update_one(
                    {"user_id": str(request.user.id)},
                    {"$set": {"photo": photo_url}},
                    upsert=True,
                )

            return redirect("profile")
    else:
        form = EditProfileForm(initial={
            "username": request.user.username,
            "email": request.user.email,
        })

    return render(request, "edit_profile.html", {
        "form": form,
        "profile_photo": profile_doc["photo"] if profile_doc else None,
    })


@login_required
def scan_receipt_view(request):
    guessed_amount = None
    extracted_text = None

    if request.method == "POST":
        form = ReceiptUploadForm(request.POST, request.FILES)
        if form.is_valid():
            receipt_image = form.cleaned_data["receipt"]

            extracted_text = extract_text_from_image(receipt_image)
            guessed_amount = guess_amount(extracted_text)

            expense_form = ExpenseForm(initial={
                "amount": guessed_amount,
                "date": datetime.now().date(),
            })

            return render(request, "scan_receipt.html", {
                "form": form,
                "expense_form": expense_form,
                "guessed_amount": guessed_amount,
                "extracted_text": extracted_text,
                "scanned": True,
            })
    else:
        form = ReceiptUploadForm()

    return render(request, "scan_receipt.html", {"form": form, "scanned": False})


@login_required
def search_expenses_api(request):
    user_id = str(request.user.id)
    selected_category = request.GET.get("category", "")
    search_query = request.GET.get("q", "").strip()
    sort_by = request.GET.get("sort", "date_desc")

    query = {"user_id": user_id}
    if selected_category:
        query["category"] = selected_category
    if search_query:
        query["title"] = {"$regex": search_query, "$options": "i"}

    sort_options = {
        "date_desc": ("date", -1),
        "date_asc": ("date", 1),
        "amount_desc": ("amount", -1),
        "amount_asc": ("amount", 1),
    }
    sort_field, sort_direction = sort_options.get(sort_by, ("date", -1))

    results = list(expenses_collection.find(query).sort(sort_field, sort_direction))

    data = []
    for e in results:
        data.append({
            "id": str(e["_id"]),
            "title": e["title"],
            "amount": e["amount"],
            "category": e["category"],
            "date": e["date"],
        })

    return JsonResponse({"expenses": data})


@login_required
def set_budget_view(request):
    user_id = str(request.user.id)
    current_budget = None

    if request.method == "POST":
        form = BudgetForm(request.POST)
        if form.is_valid():
            profiles_collection.update_one(
                {"user_id": user_id},
                {"$set": {"monthly_budget": float(form.cleaned_data["monthly_budget"])}},
                upsert=True,
            )
            return redirect("dashboard")
    else:
        profile_doc = profiles_collection.find_one({"user_id": user_id})
        current_budget = profile_doc.get("monthly_budget") if profile_doc else None
        form = BudgetForm(initial={"monthly_budget": current_budget})

    ai_suggested_budget = recommend_budget(user_id) if not current_budget else None

    return render(request, "set_budget.html", {
        "form": form,
        "ai_suggested_budget": ai_suggested_budget,
    })


@login_required
def ai_chat_view(request):
    return render(request, "ai_chat.html")


@login_required
def ai_chat_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    question = request.POST.get("question", "").strip()
    if not question:
        return JsonResponse({"error": "Please enter a question."}, status=400)

    user_id = str(request.user.id)

    try:
        answer = ask_ai_about_expenses(user_id, question)
        return JsonResponse({"answer": answer})
    except Exception as e:
        return JsonResponse({"error": f"Something went wrong: {str(e)}"}, status=500)


@login_required
def export_csv_view(request):
    user_id = str(request.user.id)
    all_expenses = list(expenses_collection.find({"user_id": user_id}).sort("date", -1))

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="my_expenses.csv"'

    writer = csv.writer(response)
    writer.writerow(["Date", "Title", "Category", "Amount"])

    for e in all_expenses:
        writer.writerow([e["date"], e["title"], e["category"], e["amount"]])

    return response


@login_required
def export_pdf_view(request):
    user_id = str(request.user.id)
    all_expenses = list(expenses_collection.find({"user_id": user_id}).sort("date", -1))

    total = sum(e["amount"] for e in all_expenses)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="expense_report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Title"], fontSize=20, spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle", parent=styles["Normal"], fontSize=10, textColor=colors.grey
    )

    elements = []

    elements.append(Paragraph("Expense Report", title_style))
    elements.append(Paragraph(f"Generated for: {request.user.username}", subtitle_style))
    elements.append(Paragraph(f"Total expenses: {len(all_expenses)} | Total spent: ₹{total:.2f}", subtitle_style))
    elements.append(Spacer(1, 16))

    table_data = [["Date", "Title", "Category", "Amount (₹)"]]
    for e in all_expenses:
        table_data.append([e["date"], e["title"], e["category"], f"{e['amount']:.2f}"])

    table = Table(table_data, colWidths=[80, 180, 100, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#171a21")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
    ]))

    elements.append(table)

    doc.build(elements)
    return response


@login_required
def recurring_expenses_view(request):
    user_id = str(request.user.id)
    recurring = list(expenses_collection.find({
        "user_id": user_id,
        "is_recurring": True
    }))

    for expense in recurring:
        expense["id"] = str(expense["_id"])

    return render(request, "recurring_expenses.html", {"recurring_expenses": recurring})


@login_required
def log_recurring_view(request, expense_id):
    original = expenses_collection.find_one({"_id": ObjectId(expense_id)})

    if not original or original["user_id"] != str(request.user.id):
        return redirect("recurring_expenses")

    if request.method == "POST":
        expenses_collection.insert_one({
            "user_id": str(request.user.id),
            "title": original["title"],
            "amount": original["amount"],
            "category": original["category"],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "is_recurring": False,
        })
        return redirect("expense_list")

    return render(request, "log_recurring_confirm.html", {"expense": original})


@login_required
def parse_expense_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    text = request.POST.get("text", "").strip()
    if not text:
        return JsonResponse({"error": "Please enter a description."}, status=400)

    parsed = parse_expense_from_text(text)

    if not parsed:
        return JsonResponse({"error": "Couldn't understand that. Try rephrasing, e.g. 'Spent 200 on lunch today'."}, status=400)

    return JsonResponse(parsed)


@login_required
def predict_category_api(request):
    title = request.GET.get("title", "").strip()
    if not title:
        return JsonResponse({"category": None})

    predicted = predict_category(str(request.user.id), title)
    return JsonResponse({"category": predicted})

@login_required
def monthly_history_view(request):
    user_id = str(request.user.id)

    month_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": {"$substr": ["$date", 0, 7]},
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}},
    ]
    months = list(expenses_collection.aggregate(month_pipeline))

    return render(request, "monthly_history.html", {"months": months})


@login_required
def monthly_history_view(request):
    user_id = str(request.user.id)

    month_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": {"$substr": ["$date", 0, 7]},
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}},
    ]
    raw_months = list(expenses_collection.aggregate(month_pipeline))

    # Rename '_id' to 'month' since Django templates block underscore-prefixed keys
    months = [
        {"month": m["_id"], "total": m["total"], "count": m["count"]}
        for m in raw_months
    ]

    return render(request, "monthly_history.html", {"months": months})


@login_required
def month_detail_view(request, month_str):
    user_id = str(request.user.id)

    # ---- Expenses for this specific month ----
    month_expenses = list(expenses_collection.find({
        "user_id": user_id,
        "date": {"$regex": f"^{month_str}"},
    }).sort("date", -1))
    for e in month_expenses:
        e["id"] = str(e["_id"])

    total = sum(e["amount"] for e in month_expenses)

    # ---- Category breakdown for this month ----
    category_pipeline = [
        {"$match": {"user_id": user_id, "date": {"$regex": f"^{month_str}"}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
    ]
    raw_category_totals = list(expenses_collection.aggregate(category_pipeline))

    # Rename '_id' to 'category' since Django templates block underscore-prefixed keys
    category_totals = [
        {"category": c["_id"], "total": c["total"]}
        for c in raw_category_totals
    ]


    # ---- AI summary: check cache first, but regenerate if the month's
    # total has changed since the summary was cached (new expense added) ----
    cached = monthly_summaries_collection.find_one({"user_id": user_id, "month": month_str})

    cache_is_stale = (not cached) or (cached.get("total") != total)

    if not cache_is_stale:
        ai_summary = cached["ai_summary"]
    else:
        ai_summary = generate_month_summary(user_id, month_str, month_expenses, category_totals, total)
        if ai_summary:
            monthly_summaries_collection.update_one(
                {"user_id": user_id, "month": month_str},
                {"$set": {
                    "user_id": user_id,
                    "month": month_str,
                    "total": total,
                    "ai_summary": ai_summary,
                }},
                upsert=True,
            )

    context = {
        "month_str": month_str,
        "expenses": month_expenses,
        "total": total,
        "category_totals": category_totals,
        "ai_summary": ai_summary,
    }
    return render(request, "month_detail.html", context)


def check_and_send_budget_alert(user_id, user):
    """
    Sends a budget-exceeded email, but only once per calendar month,
    to avoid spamming the user every time they add an expense while
    already over budget.
    """
    profile_doc = profiles_collection.find_one({"user_id": user_id})
    monthly_budget = profile_doc.get("monthly_budget") if profile_doc else None

    if not monthly_budget or monthly_budget <= 0:
        return  # no budget set, nothing to check

    current_month = datetime.now().strftime("%Y-%m")

    total_pipeline = [
        {"$match": {"user_id": user_id, "date": {"$regex": f"^{current_month}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    total_result = list(expenses_collection.aggregate(total_pipeline))
    total_this_month = total_result[0]["total"] if total_result else 0

    if total_this_month <= monthly_budget:
        return  # under budget, nothing to send

    # ---- Check if we already sent this alert for this month ----
    last_alert_month = profile_doc.get("last_budget_alert_month") if profile_doc else None
    if last_alert_month == current_month:
        return  # already alerted this month, don't spam

    # ---- Send the alert ----
    overspend = total_this_month - monthly_budget
    alert_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
        <h2 style="color: #f2545b;">⚠ Budget Exceeded</h2>
        <p>Hi {user.username},</p>
        <p>You've gone over your monthly budget for <strong>{current_month}</strong>.</p>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
            <tr><td style="padding: 6px 0; color: #666;">Budget:</td><td style="text-align: right;"><strong>₹{monthly_budget:.2f}</strong></td></tr>
            <tr><td style="padding: 6px 0; color: #666;">Spent so far:</td><td style="text-align: right;"><strong>₹{total_this_month:.2f}</strong></td></tr>
            <tr><td style="padding: 6px 0; color: #f2545b;">Over by:</td><td style="text-align: right; color: #f2545b;"><strong>₹{overspend:.2f}</strong></td></tr>
        </table>
        <p>Log in to Fintellect to review your spending and adjust your budget if needed.</p>
    </div>
    """
    sent = send_email(user.email, f"⚠ Budget Exceeded — {current_month}", alert_html)

    if sent:
        profiles_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_budget_alert_month": current_month}},
            upsert=True,
        )


@login_required
def create_split_view(request):
    if request.method == "POST":
        form = SplitExpenseForm(request.POST)
        if form.is_valid():
            friend_username = form.cleaned_data["friend_username"].strip()

            # ---- Look up the friend by username ----
            try:
                friend = User.objects.get(username=friend_username)
            except User.DoesNotExist:
                messages.error(request, f"No user found with username '{friend_username}'.")
                return render(request, "create_split.html", {"form": form})

            if friend.id == request.user.id:
                messages.error(request, "You can't split an expense with yourself.")
                return render(request, "create_split.html", {"form": form})

            total_amount = float(form.cleaned_data["total_amount"])
            split_amount = round(total_amount / 2, 2)

            split_requests_collection.insert_one({
                "from_user_id": str(request.user.id),
                "from_username": request.user.username,
                "to_user_id": str(friend.id),
                "to_username": friend.username,
                "title": form.cleaned_data["title"],
                "total_amount": total_amount,
                "category": form.cleaned_data["category"],
                "date": str(form.cleaned_data["date"]),
                "split_amount": split_amount,
                "status": "pending",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            # ---- Notify the friend by email ----
            split_email_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto;">
                <h2 style="color: #059669;">🤝 New Split Request</h2>
                <p>Hi {friend.username},</p>
                <p><strong>{request.user.username}</strong> wants to split an expense with you on Fintellect.</p>
                <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                    <tr><td style="padding: 6px 0; color: #666;">Title:</td><td style="text-align: right;"><strong>{form.cleaned_data['title']}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Total amount:</td><td style="text-align: right;"><strong>₹{total_amount:.2f}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Your share:</td><td style="text-align: right;"><strong>₹{split_amount:.2f}</strong></td></tr>
                    <tr><td style="padding: 6px 0; color: #666;">Category:</td><td style="text-align: right;">{form.cleaned_data['category']}</td></tr>
                </table>
                <p>Log in to Fintellect to accept or decline this request.</p>
            </div>
            """
            send_email(friend.email, f"{request.user.username} wants to split an expense with you", split_email_html)

            messages.success(request, f"Split request sent to {friend.username}!")
            return redirect("split_requests")
    else:
        form = SplitExpenseForm()

    return render(request, "create_split.html", {"form": form})


@login_required
def split_requests_view(request):
    user_id = str(request.user.id)

    incoming = list(split_requests_collection.find({
        "to_user_id": user_id,
        "status": "pending",
    }).sort("created_at", -1))
    for r in incoming:
        r["id"] = str(r["_id"])

    outgoing = list(split_requests_collection.find({
        "from_user_id": user_id,
    }).sort("created_at", -1))
    for r in outgoing:
        r["id"] = str(r["_id"])

    return render(request, "split_requests.html", {
        "incoming": incoming,
        "outgoing": outgoing,
    })


@login_required
def respond_split_view(request, request_id, action):
    split_req = split_requests_collection.find_one({"_id": ObjectId(request_id)})

    if not split_req or split_req["to_user_id"] != str(request.user.id):
        messages.error(request, "This split request doesn't belong to you.")
        return redirect("split_requests")

    if split_req["status"] != "pending":
        messages.error(request, "This request has already been responded to.")
        return redirect("split_requests")

    if request.method != "POST":
        messages.error(request, "Invalid request.")
        return redirect("split_requests")

    if action == "accept":
        # ---- Create the expense for BOTH users, using their own share ----
        expenses_collection.insert_one({
            "user_id": split_req["from_user_id"],
            "title": f"{split_req['title']} (split with {split_req['to_username']})",
            "amount": split_req["split_amount"],
            "category": split_req["category"],
            "date": split_req["date"],
            "is_recurring": False,
        })
        expenses_collection.insert_one({
            "user_id": split_req["to_user_id"],
            "title": f"{split_req['title']} (split with {split_req['from_username']})",
            "amount": split_req["split_amount"],
            "category": split_req["category"],
            "date": split_req["date"],
            "is_recurring": False,
        })

        split_requests_collection.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "accepted"}},
        )
        messages.success(request, "Split accepted! The expense has been added to both accounts.")

    elif action == "decline":
        split_requests_collection.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "declined"}},
        )
        messages.info(request, "Split request declined.")

    return redirect("split_requests")


@login_required
def search_users_api(request):
    """Used for autocomplete when typing a friend's username."""
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"users": []})

    matches = User.objects.filter(username__icontains=query).exclude(id=request.user.id)[:5]
    usernames = [u.username for u in matches]

    return JsonResponse({"users": usernames})


def get_pending_split_count(user_id):
    """Returns how many pending incoming split requests this user has."""
    return split_requests_collection.count_documents({
        "to_user_id": user_id,
        "status": "pending",
    })



@login_required
def create_reminder_view(request):
    if request.method == "POST":
        form = ReminderForm(request.POST)
        if form.is_valid():
            reminders_collection.insert_one({
                "user_id": str(request.user.id),
                "title": form.cleaned_data["title"],
                "amount": float(form.cleaned_data["amount"]),
                "reminder_date": str(form.cleaned_data["reminder_date"]),
                "notes": form.cleaned_data["notes"],
                "sent": False,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            messages.success(request, "Reminder created!")
            return redirect("reminders_list")
    else:
        form = ReminderForm()

    return render(request, "create_reminder.html", {"form": form})


@login_required
def reminders_list_view(request):
    user_id = str(request.user.id)
    reminders = list(reminders_collection.find({"user_id": user_id}).sort("reminder_date", 1))
    for r in reminders:
        r["id"] = str(r["_id"])

    return render(request, "reminders_list.html", {"reminders": reminders})


@login_required
def delete_reminder_view(request, reminder_id):
    reminder = reminders_collection.find_one({"_id": ObjectId(reminder_id)})
    if not reminder or reminder["user_id"] != str(request.user.id):
        messages.error(request, "This reminder doesn't belong to you.")
        return redirect("reminders_list")

    if request.method == "POST":
        reminders_collection.delete_one({"_id": ObjectId(reminder_id)})
        messages.success(request, "Reminder deleted.")

    return redirect("reminders_list")