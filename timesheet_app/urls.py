from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    home_view,
    signup_view,
    CustomLoginView,
    post_login_redirect,
    employee_dashboard,
    manager_dashboard,
    approvals_list,
    week_detail,
    manager_reports,
    projects_list,
    project_create,
    project_edit,
    project_delete,
    add_edit_entry,
    my_timesheet,
    my_reports,
    submit_week,
    start_time_entry,
    stop_time_entry,
    delete_entry,
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
    path("manager/approvals/", approvals_list, name="approvals_list"),
    path("manager/approvals/<int:week_id>/", week_detail, name="week_detail"),
    path("manager/reports/", manager_reports, name="manager_reports"),
    path("manager/projects/", projects_list, name="projects_list"),
    path("manager/projects/new/", project_create, name="project_create"),
    path("manager/projects/<int:project_id>/edit/", project_edit, name="project_edit"),
    path("manager/projects/<int:project_id>/delete/", project_delete, name="project_delete"),

    # ------------------- Add / Edit Time Entry -------------------
    path("employee/add-entry/", add_edit_entry, name="add_time_entry"),
    path("employee/edit-entry/<int:entry_id>/", add_edit_entry, name="edit_time_entry"),

    # ------------------- Timesheet & Reports -------------------
    path("employee/timesheet/", my_timesheet, name="my_timesheet"),
    path("employee/submit-week/", submit_week, name="submit_week"),
    path("employee/reports/", my_reports, name="my_reports"),

    # ------------------- Start / Stop Timer -------------------
    # urls.py
    path("employee/start-timer/", start_time_entry, name="start_time_entry"),
    path("employee/stop-timer/<int:entry_id>/", stop_time_entry, name="stop_time_entry"),
    path("employee/delete-entry/<int:entry_id>/", delete_entry, name="delete_time_entry"),

]
