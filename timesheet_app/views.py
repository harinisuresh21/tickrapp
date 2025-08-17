from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.http import HttpResponse
import csv

from .models import TimesheetEntry, Project, WeekSummary, STATUS_DRAFT, STATUS_SUBMITTED, STATUS_APPROVED
from .forms import SignUpForm, TimesheetEntryForm
from .decorators import role_required
from .utils import get_current_week_bounds

User = get_user_model()

# ------------------- Public Views -------------------
def home_view(request):
    return render(request, "home.html")


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data["role"]
            group_name = "Manager" if role == "manager" else "Employee"
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
            login(request, user)
            messages.success(request, "Account created successfully.")
            return redirect("post_login_redirect")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


class CustomLoginView(LoginView):
    template_name = "registration/login.html"


# ------------------- After Login -------------------
@login_required
def post_login_redirect(request):
    role = getattr(request.user, "role", "employee")
    if role == "manager":
        return redirect("manager_dashboard")
    return redirect("employee_dashboard")


# ------------------- Employee Dashboard -------------------
@role_required("employee")
@login_required
def employee_dashboard(request):
    week_start, week_end = get_current_week_bounds()
    entries = TimesheetEntry.objects.select_related("project")\
        .filter(user=request.user, work_date__range=(week_start, week_end))\
        .order_by("work_date", "start_time")

    total_minutes = entries.aggregate(total_minutes=Sum("duration_minutes"))["total_minutes"] or 0
    total_hours = round(total_minutes / 60.0, 2)

    week_summary, _ = WeekSummary.objects.get_or_create(
        user=request.user,
        week_start=week_start,
        defaults={"status": STATUS_DRAFT},
    )

    context = {
        "week_start": week_start,
        "week_end": week_end,
        "entries": entries,
        "total_hours": total_hours,
        "week_status": week_summary.status,
    }
    return render(request, "dashboard/employee.html", context)


# ------------------- Manager Dashboard -------------------
@role_required("manager")
@login_required
def manager_dashboard(request):
    pending_weeks = WeekSummary.objects.select_related("user")\
        .filter(status=STATUS_SUBMITTED)\
        .order_by("week_start")

    today = timezone.localdate()
    month_start = today.replace(day=1)
    approved_this_month = WeekSummary.objects.filter(
        status=STATUS_APPROVED,
        approved_at__date__gte=month_start
    ).count()

    context = {
        "pending_weeks": pending_weeks,
        "approved_this_month": approved_this_month,
        "today": today,
    }
    return render(request, "dashboard/manager.html", context)


# ------------------- Add/Edit Time Entry -------------------
@role_required("employee")
@login_required
def add_edit_entry(request, entry_id=None):
    entry = None
    if entry_id:
        entry = get_object_or_404(TimesheetEntry, pk=entry_id, user=request.user)

    if request.method == "POST":
        form = TimesheetEntryForm(request.POST, instance=entry, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, "✅ Time entry saved successfully.")
            return redirect("employee_dashboard")
        else:
            messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = TimesheetEntryForm(instance=entry, user=request.user)

    projects = Project.objects.filter(active=True)
    return render(request, "dashboard/employee_timeentry.html", {
        "form": form,
        "projects": projects,
        "entry": entry,
    })


# ------------------- My Timesheet (Weekly) -------------------
@role_required("employee")
@login_required
def my_timesheet(request):
    week_start, week_end = get_current_week_bounds()
    entries = TimesheetEntry.objects.filter(
        user=request.user,
        work_date__range=(week_start, week_end)
    ).order_by("work_date", "start_time")

    week_summary, _ = WeekSummary.objects.get_or_create(
        user=request.user,
        week_start=week_start,
        defaults={"status": STATUS_DRAFT},
    )

    total_minutes = entries.aggregate(total_minutes=Sum("duration_minutes"))["total_minutes"] or 0
    total_hours = round(total_minutes / 60.0, 2)

    context = {
        "entries": entries,
        "week_start": week_start,
        "week_end": week_end,
        "total_hours": total_hours,
        "week_status": week_summary.status,
    }
    return render(request, "dashboard/employee_mytimesheet.html", context)


# ------------------- My Reports -------------------
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Sum
import csv
from .models import TimesheetEntry
from .decorators import role_required

@role_required("employee")
@login_required
def my_reports(request):
    """View latest timesheet entries with optional date filter, CSV download, and dynamic chart data"""
    entries = TimesheetEntry.objects.filter(user=request.user).order_by("-work_date")

    # ---------------- Date filter ----------------
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    if start_date and end_date:
        entries = entries.filter(work_date__range=[start_date, end_date])

    entries = entries[:20]  # limit to latest 20 by default

    # ---------------- Calculate total hours ----------------
    total_minutes = entries.aggregate(total_minutes=Sum("duration_minutes"))["total_minutes"] or 0
    total_hours = round(total_minutes / 60.0, 2)

    # ---------------- CSV Export ----------------
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="timesheet_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Project', 'Start Time', 'End Time', 'Break (min)', 'Duration (hrs)', 'Notes'])
        for entry in entries:
            duration_hours = round(entry.duration_minutes / 60.0, 2)
            writer.writerow([entry.work_date, entry.project.name, entry.start_time, entry.end_time,
                             entry.break_minutes, duration_hours, entry.notes])
        return response

    # ---------------- Prepare chart data ----------------
    # Hours per project from filtered entries
    project_data = entries.values('project__name').annotate(hours=Sum('duration_minutes'))
    chart_labels = [item['project__name'] for item in project_data]
    chart_data = [round(item['hours'] / 60.0, 2) for item in project_data]

    # Add computed hours field for template
    for entry in entries:
        entry.hours = round(entry.duration_minutes / 60.0, 2)

    context = {
        "entries": entries,
        "total_hours": total_hours,
        "start_date": start_date,
        "end_date": end_date,
        "chart_labels": chart_labels,
        "chart_data": chart_data,
    }
    return render(request, "dashboard/employee_myreport.html", context)
