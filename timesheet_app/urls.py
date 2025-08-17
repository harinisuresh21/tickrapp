from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    home_view,
    signup_view,
    CustomLoginView,
    post_login_redirect,
    employee_dashboard,
    manager_dashboard,
    add_edit_entry,
    my_timesheet,
    my_reports,
)

urlpatterns = [
    # ------------------- Public / Auth -------------------
    path("", home_view, name="home"),
    path("accounts/signup/", signup_view, name="signup"),
    path("accounts/login/", CustomLoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(next_page="home"), name="logout"),
    path("accounts/redirect/", post_login_redirect, name="post_login_redirect"),

    # ------------------- Dashboards -------------------
    path("dashboard/employee/", employee_dashboard, name="employee_dashboard"),
    path("dashboard/manager/", manager_dashboard, name="manager_dashboard"),

    # ------------------- Add / Edit Time Entry -------------------
    path("employee/add-entry/", add_edit_entry, name="add_time_entry"),
    path("employee/edit-entry/<int:entry_id>/", add_edit_entry, name="edit_time_entry"),

    # ------------------- Timesheet & Reports -------------------
    path("employee/timesheet/", my_timesheet, name="my_timesheet"),
    path("employee/reports/", my_reports, name="my_reports"),
]
