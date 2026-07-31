from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("register/", views.register_view, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="home"), name="logout"),
    path("add-expense/", views.add_expense_view, name="add_expense"),
    path("expenses/", views.expense_list_view, name="expense_list"),
    path("expenses/<str:expense_id>/edit/", views.edit_expense_view, name="edit_expense"),
    path("expenses/<str:expense_id>/delete/", views.delete_expense_view, name="delete_expense"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.edit_profile_view, name="edit_profile"),
    path(
        "profile/change-password/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/change_password.html",
            success_url="/profile/",
        ),
        name="change_password",
    ),
    path("scan-receipt/", views.scan_receipt_view, name="scan_receipt"),
    path("api/search-expenses/", views.search_expenses_api, name="search_expenses_api"),
    path("set-budget/", views.set_budget_view, name="set_budget"),
    path("ai-chat/", views.ai_chat_view, name="ai_chat"),
    path("api/ai-chat/", views.ai_chat_api, name="ai_chat_api"),
    path("export-csv/", views.export_csv_view, name="export_csv"),
    path("export-pdf/", views.export_pdf_view, name="export_pdf"),
    path("recurring/", views.recurring_expenses_view, name="recurring_expenses"),
    path("recurring/<str:expense_id>/log/", views.log_recurring_view, name="log_recurring"),
    path("api/parse-expense/", views.parse_expense_api, name="parse_expense_api"),
    path("api/predict-category/", views.predict_category_api, name="predict_category_api"),
    path("monthly-history/", views.monthly_history_view, name="monthly_history"),
    path("monthly-history/<str:month_str>/", views.month_detail_view, name="month_detail"),
    path("create-split/", views.create_split_view, name="create_split"),
    path("split-requests/", views.split_requests_view, name="split_requests"),
    path("split-requests/<str:request_id>/<str:action>/", views.respond_split_view, name="respond_split"),
    path("api/search-users/", views.search_users_api, name="search_users_api"),
]