from django.urls import path
from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views
from .views import (
    home_view,
    signup_view,
    CustomLoginView,
    post_login_redirect,
    employee_dashboard,
    upload_profile_picture,
    weekly_summary_fragment,
    logout_view,
    manager_dashboard,
    manager_employee_detail,
    manager_employee_reports,
    manager_add_edit_entry,
    manager_my_timesheet,
    manager_my_reports,
    manager_start_time_entry,
    manager_stop_time_entry,
    manager_delete_entry,
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
    manager_add_edit_entry,
    manager_my_timesheet,
    manager_my_reports,
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
    path("accounts/logout/", logout_view, name="logout"),
    # Password reset flow (using built-in views)
    path('accounts/password_reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('accounts/password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
    path("accounts/redirect/", post_login_redirect, name="post_login_redirect"),

    # ------------------- Dashboards -------------------
    path("dashboard/employee/", employee_dashboard, name="employee_dashboard"),
    path('employee/upload-avatar/', upload_profile_picture, name='upload_profile_picture'),
    path('employee/weekly-summary/', weekly_summary_fragment, name='weekly_summary_fragment'),
    path("dashboard/manager/", manager_dashboard, name="manager_dashboard"),
    path("manager/approvals/", approvals_list, name="approvals_list"),
    path("manager/employee/<int:user_id>/", manager_employee_detail, name="manager_employee_detail"),
    path("manager/employee-reports/", manager_employee_reports, name="manager_employee_reports"),
    # Manager personal pages (manager acts like an employee for own entries)
    path("manager/add-entry/", manager_add_edit_entry, name="manager_add_time_entry"),
    path("manager/my-timesheet/", manager_my_timesheet, name="manager_my_timesheet"),
    path("manager/my-reports/", manager_my_reports, name="manager_my_reports"),
    path("manager/start-timer/", manager_start_time_entry, name="manager_start_time_entry"),
    path("manager/stop-timer/<int:entry_id>/", manager_stop_time_entry, name="manager_stop_time_entry"),
    path("manager/approvals/<int:week_id>/", week_detail, name="week_detail"),
    path("manager/reports/", manager_reports, name="manager_reports"),
    path("manager/projects/", projects_list, name="projects_list"),
    path("manager/projects/new/", project_create, name="project_create"),
    path("manager/projects/<int:project_id>/edit/", project_edit, name="project_edit"),
    path("manager/projects/<int:project_id>/delete/", project_delete, name="project_delete"),

    # ------------------- Add / Edit Time Entry -------------------
    path("employee/add-entry/", add_edit_entry, name="add_time_entry"),
    path("employee/edit-entry/<int:entry_id>/", add_edit_entry, name="edit_time_entry"),
    # manager-scoped add/edit/delete
    path("manager/add-entry/", manager_add_edit_entry, name="manager_add_time_entry"),
    path("manager/edit-entry/<int:entry_id>/", manager_add_edit_entry, name="manager_edit_time_entry"),
    path("manager/delete-entry/<int:entry_id>/", manager_delete_entry, name="manager_delete_time_entry"),

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
