from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import HttpResponse
from collections import defaultdict
import csv
import datetime as dt
import calendar

from .models import TimesheetEntry, Project, WeekSummary, STATUS_DRAFT, STATUS_SUBMITTED, STATUS_APPROVED, STATUS_REJECTED
from .forms import SignUpForm, TimesheetEntryForm, ProjectForm
from .decorators import role_required
from .utils import get_current_week_bounds
from django.template.loader import render_to_string
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth import logout as auth_logout

User = get_user_model()


@role_required('manager')
@login_required
def manager_employee_detail(request, user_id):
    # Show employee profile, projects and hours per project
    employee = get_object_or_404(User, pk=user_id)
    # projects this employee has entries for (last 90 days)
    start = timezone.localdate() - dt.timedelta(days=90)
    entries = TimesheetEntry.objects.filter(user=employee, work_date__gte=start).select_related('project')
    proj_map = {}
    for e in entries:
        name = e.project.name if e.project else 'Unassigned'
        proj_map.setdefault(name, 0.0)
        proj_map[name] += (e.duration_minutes or 0) / 60.0
    proj_rows = [{'project': k, 'hours': round(v, 2)} for k, v in proj_map.items()]
    return render(request, 'dashboard/manager_employee_detail.html', {'employee': employee, 'proj_rows': proj_rows})


@role_required('manager')
@login_required
def manager_employee_reports(request):
    # Similar to manager_reports but grouped by employee
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    today = dt.date.today()
    try:
        start = dt.date.fromisoformat(start_date) if start_date else today - dt.timedelta(days=30)
    except Exception:
        start = today - dt.timedelta(days=30)
    try:
        end = dt.date.fromisoformat(end_date) if end_date else today
    except Exception:
        end = today

    # Only include entries for users who are in the Employee group (exclude managers)
    qs = TimesheetEntry.objects.filter(work_date__range=(start, end), user__groups__name='Employee').select_related('project', 'user')
    # Optional project filter
    proj_id = request.GET.get('project')
    if proj_id:
        try:
            qs = qs.filter(project_id=int(proj_id))
        except ValueError:
            pass
    rows = []
    emp_proj = {}
    billable = {}
    for e in qs:
        key = (e.user.username, e.project.name if e.project else 'Unassigned')
        emp_proj.setdefault(key, 0.0)
        emp_proj[key] += (e.duration_minutes or 0) / 60.0
        if e.billable:
            billable.setdefault(key, 0.0)
            billable[key] += (e.duration_minutes or 0) / 60.0

    for (username, project), hrs in emp_proj.items():
        bill = billable.get((username, project), 0.0)
        pct = round((bill / hrs * 100) if hrs else 0, 2)
        rows.append({'employee': username, 'project': project, 'hours': round(hrs, 2), 'billable_hours': round(bill, 2), 'percent_billable': pct})

    projects = Project.objects.all().order_by('name')
    import json
    rows_json = json.dumps(rows)
    context = {'rows': rows, 'rows_json': rows_json, 'projects': projects, 'start': start, 'end': end}
    return render(request, 'dashboard/manager_employee_reports.html', context)


@role_required('manager')
@login_required
def manager_add_edit_entry(request, entry_id=None):
    # Manager-scoped add/edit entry: similar to employee add_edit_entry but renders manager template
    entry = get_object_or_404(TimesheetEntry, pk=entry_id, user=request.user) if entry_id else None
    if request.method == "POST":
        form = TimesheetEntryForm(request.POST, instance=entry, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            start_time_field = form.cleaned_data.get('start_time_time')
            end_time_field = form.cleaned_data.get('end_time_time')
            if start_time_field:
                obj.start_time = timezone.make_aware(dt.datetime.combine(obj.work_date, start_time_field))
            if end_time_field:
                obj.end_time = timezone.make_aware(dt.datetime.combine(obj.work_date, end_time_field))
            if obj.start_time and obj.end_time:
                delta = obj.end_time - obj.start_time
                obj.duration_minutes = int(delta.total_seconds() / 60)
            obj.save()
            messages.success(request, "✅ Time entry saved successfully.")
            # Redirect to manager timesheet and show the week containing the saved entry
            try:
                wd = obj.work_date.isoformat() if getattr(obj, 'work_date', None) else None
                if wd:
                    url = reverse('manager_my_timesheet')
                    return redirect(f"{url}?view_date={wd}")
            except Exception:
                pass
            return redirect('manager_my_timesheet')
        messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = TimesheetEntryForm(instance=entry, user=request.user)

    projects = Project.objects.filter(active=True)
    projects_available = projects.exists() or (entry and entry.project is not None)
    return render(request, "dashboard/manager_timeentry.html", {
        "form": form,
        "projects": projects,
        "projects_available": projects_available,
        "entry": entry,
    })


@role_required('manager')
@login_required
def manager_my_timesheet(request):
    # Manager-scoped timesheet (only manager's own entries)
    # Support optional view_date query param to show the week containing that date (useful after redirects)
    view_date_str = request.GET.get('view_date')
    if view_date_str:
        try:
            vd = dt.date.fromisoformat(view_date_str)
            week_start, week_end = get_current_week_bounds(vd)
        except Exception:
            week_start, week_end = get_current_week_bounds()
    else:
        week_start, week_end = get_current_week_bounds()
    # Show newest entries first so recently added items appear at top
    entries = TimesheetEntry.objects.filter(
        user=request.user,
        work_date__range=(week_start, week_end)
    ).order_by("-work_date", "-start_time")

    week_summary, _ = WeekSummary.objects.get_or_create(
        user=request.user, week_start=week_start, defaults={"status": STATUS_DRAFT}
    )

    for e in entries:
        if e.duration_minutes is not None:
            e.hours = round(e.duration_minutes / 60.0, 2)
        elif e.start_time and e.end_time:
            delta = e.end_time - e.start_time
            e.hours = round(delta.total_seconds() / 3600, 2)
        else:
            e.hours = 0

    total_minutes = entries.aggregate(total_minutes=Coalesce(Sum("duration_minutes"), 0))["total_minutes"]
    total_hours = round((total_minutes or 0) / 60.0, 2)

    context = {
        "entries": entries,
        "week_start": week_start,
        "week_end": week_end,
        "total_hours": total_hours,
        "week_status": week_summary.status,
    }
    return render(request, "dashboard/manager_mytimesheet.html", context)


@role_required('manager')
@login_required
def manager_my_reports(request):
    # Manager-scoped reports (only manager's own entries)
    user = request.user
    projects = Project.objects.all().order_by("name")

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    project_id = request.GET.get("project")

    today = dt.date.today()
    def _parse_query_date(s, default):
        if not s:
            return default
        s_clean = s.replace('.', '').strip()
        formats = [
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%m/%d/%Y",
            "%d-%m-%Y",
        ]
        for fmt in formats:
            try:
                return dt.datetime.strptime(s_clean, fmt).date()
            except Exception:
                continue
        try:
            return dt.date.fromisoformat(s_clean)
        except Exception:
            messages.warning(request, f"Could not parse date '{s}'; using default range.")
            return default

    start_date_obj = _parse_query_date(start_date, today - dt.timedelta(days=30))
    end_date_obj = _parse_query_date(end_date, today)

    entries_qs = TimesheetEntry.objects.filter(
        user=user,
        work_date__range=(start_date_obj, end_date_obj)
    ).order_by("work_date", "start_time")

    if project_id:
        try:
            entries_qs = entries_qs.filter(project_id=int(project_id))
        except ValueError:
            pass

    entries = []
    for e in entries_qs:
        if e.duration_minutes is not None:
            e.hours = round(e.duration_minutes / 60.0, 2)
        else:
            e.hours = 0
        entries.append(e)

    summary_dict = defaultdict(float)
    for e in entries:
        name = e.project.name if e.project else "Unassigned"
        summary_dict[name] += e.hours
    summary_rows = [{"name": k, "hours": round(v, 2)} for k, v in summary_dict.items()]

    chart_dict = defaultdict(float)
    for e in entries:
        chart_dict[e.work_date.strftime("%d-%m-%Y")] += e.hours
    chart_labels = list(chart_dict.keys())
    chart_data = [chart_dict[d] for d in chart_labels]

    export = request.GET.get("export", "").lower()
    if export in {"summary", "details"}:
        filename = f"timesheet_{export}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write('\ufeff')
        writer = csv.writer(response, lineterminator='\n')
        if export == "summary":
            writer.writerow(["Project", "Total Hours"])
            for row in summary_rows:
                writer.writerow([str(row.get('name','')), f"{float(row.get('hours',0)):.2f}"])
        else:
            writer.writerow(["Date", "Project", "Start", "End", "Break (min)", "Hours", "Notes"])
            for e in entries:
                date_str = e.work_date.strftime("%d-%m-%Y") if getattr(e, 'work_date', None) else ""
                project_name = e.project.name if getattr(e, 'project', None) else "Unassigned"
                start_str = e.start_time.strftime("%H:%M") if getattr(e, 'start_time', None) else ""
                end_str = e.end_time.strftime("%H:%M") if getattr(e, 'end_time', None) else ""
                break_min = getattr(e, 'break_minutes', 0) or 0
                hours_val = getattr(e, 'hours', 0) or 0
                notes = getattr(e, 'notes', '') or ''
                writer.writerow([date_str, project_name, start_str, end_str, str(break_min), f"{float(hours_val):.2f}", notes])
        return response

    context = {
        "entries": entries,
        "projects": projects,
        "summary_rows": summary_rows,
        "chart_labels": chart_labels,
        "chart_data": chart_data,
        "start_date": start_date_obj.isoformat(),
        "end_date": end_date_obj.isoformat(),
        "selected_project_id": int(project_id) if project_id else None,
    }
    return render(request, "dashboard/manager_myreport.html", context)


@role_required('manager')
@login_required
def manager_start_time_entry(request):
    # Similar to start_time_entry but for managers starting their own timer via manager UI
    user = request.user
    today = timezone.localdate()
    overlapping = TimesheetEntry.objects.filter(user=user, end_time__isnull=True).exists()
    if overlapping:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'running'}, status=400)
        messages.warning(request, 'You already have a running timer!')
        return redirect('manager_dashboard')

    if request.method == 'POST':
        project_id = request.POST.get('project')
        notes = request.POST.get('notes', '')
        project = Project.objects.filter(id=project_id).first() if project_id else None
        entry = TimesheetEntry.objects.create(user=user, project=project, start_time=timezone.now(), work_date=today, notes=notes, duration_minutes=0)
        # Return JSON fragment similar to employee handler
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            running_html = render_to_string('dashboard/_running_timer.html', {'running_timer': entry, 'projects': Project.objects.filter(active=True)}, request=request)
            return JsonResponse({'running_html': running_html, 'start_ms': int(entry.start_time.timestamp() * 1000)})
    return redirect('manager_dashboard')


@role_required('manager')
@login_required
def manager_stop_time_entry(request, entry_id):
    user = request.user
    entry = get_object_or_404(TimesheetEntry, id=entry_id, user=user)
    if entry.end_time:
        messages.warning(request, 'This timer is already stopped!')
        return redirect('manager_dashboard')
    entry.end_time = timezone.now()
    delta = entry.end_time - entry.start_time
    entry.duration_minutes = int(delta.total_seconds() / 60)
    entry.hours = round(delta.total_seconds() / 3600, 2)
    entry.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        recent_entries = TimesheetEntry.objects.filter(user=user).order_by('-work_date', '-start_time')[:5]
        recent_html = render_to_string('dashboard/_recent_entries.html', {'recent_entries': recent_entries}, request=request)
        running_timer = TimesheetEntry.objects.filter(user=user, end_time__isnull=True).order_by('-start_time').first()
        running_html = render_to_string('dashboard/_running_timer.html', {'running_timer': running_timer, 'projects': Project.objects.filter(active=True)}, request=request)
        return JsonResponse({'recent_html': recent_html, 'running_html': running_html})
    messages.success(request, f'Timer stopped! Total hours: {entry.hours}')
    return redirect('manager_dashboard')

@login_required
def upload_profile_picture(request):
    if request.method == 'POST':
        avatar = request.FILES.get('avatar')
        profile = getattr(request.user, 'profile', None)
        if not profile:
            from .models import Profile
            profile = Profile.objects.create(user=request.user)
        if avatar:
            profile.avatar = avatar
            profile.save()
            messages.success(request, 'Profile picture updated.')
        return redirect('employee_dashboard')
    return render(request, 'dashboard/profile_picture_form.html')


def logout_view(request):
    # Accept only POST for logout to avoid accidental GET logouts
    if request.method == 'POST':
        auth_logout(request)
        return redirect('home')
    # If GET, redirect to home (do not logout via GET)
    return redirect('home')


@login_required
def weekly_summary_fragment(request):
    # Returns JSON with this week's total hours and approved count for user
    week_start, week_end = get_current_week_bounds()
    entries = TimesheetEntry.objects.filter(user=request.user, work_date__range=(week_start, week_end))
    total_minutes = entries.aggregate(total_minutes=Coalesce(Sum('duration_minutes'), 0))['total_minutes'] or 0
    total_hours = round(total_minutes / 60.0, 2)
    approved = WeekSummary.objects.filter(user=request.user, week_start=week_start, status=STATUS_APPROVED).exists()
    return JsonResponse({'this_week_hours': total_hours, 'approved': int(bool(approved))})

# ------------------- Public Views -------------------
def home_view(request):
    return render(request, "home.html")


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data.get("role", "employee")
            group_name = "Manager" if role.lower() == "manager" else "Employee"
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
            login(request, user)
            messages.success(request, "Account created successfully.")
            return redirect("post_login_redirect")
        messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


class CustomLoginView(LoginView):
    template_name = "registration/login.html"


# ------------------- Post Login Redirect -------------------
@login_required
def post_login_redirect(request):
    if request.user.groups.filter(name="Manager").exists():
        return redirect("manager_dashboard")
    return redirect("employee_dashboard")


# ---------------- Employee Dashboard ----------------
@login_required
@role_required("employee")
def employee_dashboard(request):
    user = request.user
    today = dt.date.today()

    # Projects for timer
    projects = Project.objects.filter(active=True).order_by("name")

    # Active Timer (exposed to template as 'running_timer')
    running_timer = TimesheetEntry.objects.filter(user=user, end_time__isnull=True).order_by("-start_time").first()
    if running_timer and running_timer.start_time:
        delta = timezone.now() - running_timer.start_time
        running_timer.hours = round(delta.total_seconds() / 3600, 2)
    else:
        running_timer = None

    # Recent Entries (last 5)
    recent_entries = TimesheetEntry.objects.filter(user=user).order_by("-work_date", "-start_time")[:5]
    for e in recent_entries:
        if e.duration_minutes is not None:
            e.hours = round(e.duration_minutes / 60.0, 2)
        elif e.start_time:
            delta = timezone.now() - e.start_time
            e.hours = round(delta.total_seconds() / 3600, 2)
        else:
            e.hours = 0

    # Git-style Year Contribution
    year_start = dt.date(today.year, 1, 1)
    year_end = dt.date(today.year, 12, 31)
    entries_qs = TimesheetEntry.objects.filter(
        user=user, work_date__range=(year_start, year_end)
    ).values("work_date").annotate(total_minutes=Coalesce(Sum("duration_minutes"), 0))

    hours_map = {e["work_date"]: e["total_minutes"] / 60 for e in entries_qs}

    cal_data = []
    week = []
    current_date = year_start
    while current_date <= year_end:
        if current_date.weekday() == 6 and week:
            cal_data.append(week)
            week = []
        week.append({"date": current_date, "hours": hours_map.get(current_date, 0)})
        current_date += dt.timedelta(days=1)
    if week:
        cal_data.append(week)

    # Month labels with precomputed margin
    month_labels = []
    # Each week column consumes ~22px (16px block + gaps); calculate margins accordingly
    week_column_width = 22
    for month in range(1, 13):
        first_day = dt.date(today.year, month, 1)
        week_index = (first_day - year_start).days // 7
        margin_px = week_index * week_column_width
        month_labels.append({"name": calendar.month_abbr[month], "margin": margin_px})

    # Build week day pairs (label + date) for current week
    week_start, _ = get_current_week_bounds(today)
    week_days = [week_start + dt.timedelta(days=i) for i in range(7)]
    labels = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
    week_day_pairs = [{'date': d, 'label': labels[i]} for i, d in enumerate(week_days)]

    # compute total minutes for current week
    entries_week = TimesheetEntry.objects.filter(user=user, work_date__range=(week_start, week_start + dt.timedelta(days=6)))
    total_minutes = entries_week.aggregate(total_minutes=Coalesce(Sum('duration_minutes'), 0))['total_minutes'] or 0
    total_hours = round(total_minutes / 60.0, 2)

    context = {
        "projects": projects,
        "running_timer": running_timer,
        "recent_entries": recent_entries,
        "cal_data": cal_data,
        "month_labels": month_labels,
        # weekly UI data
        "week_start": week_start,
        "week_day_pairs": week_day_pairs,
        "today": today,
        "approved_this_week": int(WeekSummary.objects.filter(user=user, week_start=week_start, status=STATUS_APPROVED).exists()),
        "this_week_hours": total_hours,
    }

    return render(request, "dashboard/employee.html", context)


# ---------------- Start Timer ----------------
@login_required
def start_time_entry(request):
    user = request.user
    today = timezone.localdate()
    # Prevent overlapping timers
    overlapping = TimesheetEntry.objects.filter(
        user=user,
        end_time__isnull=True,
    ).exists()

    if overlapping:
        messages.warning(request, "You already have a running timer!", extra_tags='dashboard')
        # If XHR request, return JSON so front-end can update without redirect
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({"error": "running"}, status=400)
        return redirect("employee_dashboard")

    if request.method == "POST":
        project_id = request.POST.get("project")
        notes = request.POST.get("notes", "")
        project = Project.objects.filter(id=project_id).first() if project_id else None

        # Check if overlapping with today entries
        overlapping_today = TimesheetEntry.objects.filter(
            user=user,
            work_date=today,
            start_time__lte=timezone.now(),
            end_time__gte=timezone.now(),
        ).exists()

        if overlapping_today:
            messages.error(request, "Cannot start timer: overlapping entry exists today.", extra_tags='dashboard')
            return redirect("employee_dashboard")

        TimesheetEntry.objects.create(
            user=user,
            project=project,
            start_time=timezone.now(),
            work_date=today,
            notes=notes,
            duration_minutes=0,
        )

        messages.success(request, "Timer started successfully!", extra_tags='dashboard')

        # If AJAX request, return updated fragments
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            recent_entries = TimesheetEntry.objects.filter(user=user).order_by("-work_date", "-start_time")[:5]
            for e in recent_entries:
                if e.duration_minutes is not None:
                    e.hours = round(e.duration_minutes / 60.0, 2)
                elif e.start_time:
                    delta = timezone.now() - e.start_time
                    e.hours = round(delta.total_seconds() / 3600, 2)
                else:
                    e.hours = 0

            running_timer = TimesheetEntry.objects.filter(user=user, end_time__isnull=True).order_by("-start_time").first()
            if running_timer and running_timer.start_time:
                delta = timezone.now() - running_timer.start_time
                running_timer.hours = round(delta.total_seconds() / 3600, 2)

            recent_html = render_to_string("dashboard/_recent_entries.html", {"recent_entries": recent_entries}, request=request)
            running_html = render_to_string("dashboard/_running_timer.html", {"running_timer": running_timer, "projects": Project.objects.filter(active=True)}, request=request)
            # include start_ms for client initialization
            start_ms = int(running_timer.start_time.timestamp() * 1000) if running_timer and running_timer.start_time else None
            return JsonResponse({"recent_html": recent_html, "running_html": running_html, "start_ms": start_ms})

    return redirect("employee_dashboard")


# ---------------- Stop Timer ----------------
@login_required
def stop_time_entry(request, entry_id):
    user = request.user
    entry = get_object_or_404(TimesheetEntry, id=entry_id, user=user)
    if entry.end_time:
        messages.warning(request, "This timer is already stopped!", extra_tags='dashboard')
        return redirect("employee_dashboard")

    entry.end_time = timezone.now()
    delta = entry.end_time - entry.start_time
    entry.duration_minutes = int(delta.total_seconds() / 60)
    entry.hours = round(delta.total_seconds() / 3600, 2)
    entry.save()
    messages.success(request, f"Timer stopped! Total hours: {entry.hours}", extra_tags='dashboard')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Return updated fragments for AJAX clients
        recent_entries = TimesheetEntry.objects.filter(user=user).order_by("-work_date", "-start_time")[:5]
        for e in recent_entries:
            if e.duration_minutes is not None:
                e.hours = round(e.duration_minutes / 60.0, 2)
            elif e.start_time and e.end_time:
                delta = e.end_time - e.start_time
                e.hours = round(delta.total_seconds() / 3600, 2)
            else:
                e.hours = 0

        running_timer = TimesheetEntry.objects.filter(user=user, end_time__isnull=True).order_by("-start_time").first()
        if running_timer and running_timer.start_time:
            delta = timezone.now() - running_timer.start_time
            running_timer.hours = round(delta.total_seconds() / 3600, 2)

        recent_html = render_to_string("dashboard/_recent_entries.html", {"recent_entries": recent_entries}, request=request)
        running_html = render_to_string(
            "dashboard/_running_timer.html",
            {"running_timer": running_timer, "projects": Project.objects.filter(active=True), "start_name": 'start_time_entry', "stop_name": 'stop_time_entry'},
            request=request,
        )
        start_ms = int(running_timer.start_time.timestamp() * 1000) if running_timer and running_timer.start_time else None
        return JsonResponse({"recent_html": recent_html, "running_html": running_html, "start_ms": start_ms})

    # Non-AJAX: simple redirect back to dashboard
    return redirect("employee_dashboard")


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

    # Users to show in manager dashboard (exclude superusers if desired)
    employees = User.objects.filter(groups__name='Employee').order_by('username')
    projects = Project.objects.all().order_by('name')

    # Also include manager's personal dashboard widgets: calendar graph and weekly UI
    # Git-style Year Contribution for manager (their own entries)
    year_start = dt.date(today.year, 1, 1)
    year_end = dt.date(today.year, 12, 31)
    entries_qs = TimesheetEntry.objects.filter(user=request.user, work_date__range=(year_start, year_end)).values("work_date").annotate(total_minutes=Coalesce(Sum("duration_minutes"), 0))
    hours_map = {e["work_date"]: e["total_minutes"] / 60 for e in entries_qs}
    cal_data = []
    week = []
    current_date = year_start
    while current_date <= year_end:
        if current_date.weekday() == 6 and week:
            cal_data.append(week)
            week = []
        week.append({"date": current_date, "hours": hours_map.get(current_date, 0)})
        current_date += dt.timedelta(days=1)
    if week:
        cal_data.append(week)

    # Month labels
    month_labels = []
    week_column_width = 22
    for month in range(1,13):
        first_day = dt.date(today.year, month, 1)
        week_index = (first_day - year_start).days // 7
        margin_px = week_index * week_column_width
        month_labels.append({"name": calendar.month_abbr[month], "margin": margin_px})

    # week_day_pairs
    week_start, _ = get_current_week_bounds(today)
    week_days = [week_start + dt.timedelta(days=i) for i in range(7)]
    labels = ['M','T','W','T','F','S','S']
    week_day_pairs = [{'date': d, 'label': labels[i]} for i, d in enumerate(week_days)]
    entries_week = TimesheetEntry.objects.filter(user=request.user, work_date__range=(week_start, week_start + dt.timedelta(days=6)))
    total_minutes = entries_week.aggregate(total_minutes=Coalesce(Sum('duration_minutes'), 0))['total_minutes'] or 0
    total_hours = round(total_minutes / 60.0, 2)

    context = {
        "pending_weeks": pending_weeks,
        "approved_this_month": approved_this_month,
        "today": today,
        "employees": employees,
        "projects": projects,
        # manager personal widgets
        "cal_data": cal_data,
        "month_labels": month_labels,
        "week_day_pairs": week_day_pairs,
        "today": today,
        "this_week_hours": total_hours,
        "approved_this_week": int(WeekSummary.objects.filter(user=request.user, week_start=week_start, status=STATUS_APPROVED).exists()),
    }
    return render(request, "dashboard/manager.html", context)


# ------------------- Approvals -------------------
@role_required("manager")
@login_required
def approvals_list(request):
    pending = WeekSummary.objects.select_related('user').filter(status=STATUS_SUBMITTED).order_by('week_start')
    approved = WeekSummary.objects.select_related('user').filter(status=STATUS_APPROVED).order_by('-approved_at')[:50]
    rejected = WeekSummary.objects.select_related('user').filter(status=STATUS_REJECTED).order_by('-approved_at')[:50]
    return render(request, 'dashboard/approvals_list.html', {'pending': pending, 'approved': approved, 'rejected': rejected})


@role_required('manager')
@login_required
def week_detail(request, week_id):
    week = get_object_or_404(WeekSummary, pk=week_id)
    entries = TimesheetEntry.objects.filter(user=week.user, work_date__range=(week.week_start, week.week_start + dt.timedelta(days=6))).select_related('project')
    if request.method == 'POST':
        action = request.POST.get('action')
        note = request.POST.get('note', '')
        manager_comment = request.POST.get('manager_comment', '')
        if action == 'approve':
            week.status = STATUS_APPROVED
            week.approver = request.user
            week.approved_at = timezone.now()
            week.audit_note = note
            week.manager_comment = manager_comment
            week.save()
            messages.success(request, 'Week approved.')
        elif action == 'reject':
            week.status = STATUS_REJECTED
            week.approver = request.user
            week.approved_at = timezone.now()
            week.audit_note = note
            week.manager_comment = manager_comment
            week.save()
            messages.success(request, 'Week rejected.')
        return redirect('approvals_list')
    return render(request, 'dashboard/week_detail.html', {'week': week, 'entries': entries})


@role_required('employee')
@login_required
def submit_week(request):
    # Submits the current user's week summary for manager review
    week_start, week_end = get_current_week_bounds()
    week, created = WeekSummary.objects.get_or_create(user=request.user, week_start=week_start)
    week.status = STATUS_SUBMITTED
    week.submitted_at = timezone.now()
    week.save()
    messages.success(request, 'Week submitted for approval.')
    return redirect('my_timesheet')


# ------------------- Manager Reports -------------------
@role_required('manager')
@login_required
def manager_reports(request):
    # Hours by project within date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    try:
        start = dt.date.fromisoformat(start_date) if start_date else dt.date.today() - dt.timedelta(days=30)
    except Exception:
        start = dt.date.today() - dt.timedelta(days=30)
    try:
        end = dt.date.fromisoformat(end_date) if end_date else dt.date.today()
    except Exception:
        end = dt.date.today()

    qs = TimesheetEntry.objects.filter(work_date__range=(start, end)).select_related('project')
    project_map = defaultdict(float)
    billable_map = defaultdict(float)
    for e in qs:
        h = (e.duration_minutes or 0) / 60.0
        name = e.project.name if e.project else 'Unassigned'
        project_map[name] += h
        if e.billable:
            billable_map[name] += h

    rows = []
    total_hours = sum(project_map.values())
    for name, hrs in project_map.items():
        bill = billable_map.get(name, 0.0)
        pct_bill = round((bill / hrs * 100) if hrs else 0, 2)
        rows.append({'project': name, 'hours': round(hrs,2), 'billable_hours': round(bill,2), 'percent_billable': pct_bill})

    # CSV export option
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="hours_by_project.csv"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['Project','Hours','Billable Hours','% Billable'])
        for r in rows:
            writer.writerow([r['project'], f"{r['hours']:.2f}", f"{r['billable_hours']:.2f}", f"{r['percent_billable']:.2f}"])
        return response

    return render(request, 'dashboard/manager_reports.html', {'rows': rows, 'start': start, 'end': end, 'total_hours': total_hours})


# ------------------- Project CRUD (manager) -------------------
@role_required('manager')
@login_required
def projects_list(request):
    projects = Project.objects.all().order_by('name')
    return render(request, 'dashboard/projects_list.html', {'projects': projects})


@role_required('manager')
@login_required
def project_create(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project created.')
            return redirect('projects_list')
    else:
        form = ProjectForm()
    return render(request, 'dashboard/project_form.html', {'form': form})


@role_required('manager')
@login_required
def project_edit(request, project_id):
    proj = get_object_or_404(Project, pk=project_id)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=proj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated.')
            return redirect('projects_list')
    else:
        form = ProjectForm(instance=proj)
    return render(request, 'dashboard/project_form.html', {'form': form, 'project': proj})


@role_required('manager')
@login_required
def project_delete(request, project_id):
    proj = get_object_or_404(Project, pk=project_id)
    if TimesheetEntry.objects.filter(project=proj).exists():
        messages.error(request, 'Cannot delete project linked to timesheet entries.')
        return redirect('projects_list')
    if request.method == 'POST':
        proj.delete()
        messages.success(request, 'Project deleted.')
        return redirect('projects_list')
    return render(request, 'dashboard/project_confirm_delete.html', {'project': proj})


# ------------------- Add / Edit Time Entry -------------------
@role_required("employee")
@login_required
def add_edit_entry(request, entry_id=None):
    entry = get_object_or_404(TimesheetEntry, pk=entry_id, user=request.user) if entry_id else None
    if request.method == "POST":
        form = TimesheetEntryForm(request.POST, instance=entry, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            # Compose start_time and end_time from date + time fields if provided
            start_time_field = form.cleaned_data.get('start_time_time')
            end_time_field = form.cleaned_data.get('end_time_time')
            if start_time_field:
                obj.start_time = timezone.make_aware(dt.datetime.combine(obj.work_date, start_time_field))
            if end_time_field:
                obj.end_time = timezone.make_aware(dt.datetime.combine(obj.work_date, end_time_field))
            if obj.start_time and obj.end_time:
                delta = obj.end_time - obj.start_time
                obj.duration_minutes = int(delta.total_seconds() / 60)
            obj.save()
            messages.success(request, f"✅ Time entry saved successfully (id={obj.id}, date={obj.work_date}).")
            return redirect("employee_dashboard")
        messages.error(request, "⚠️ Please correct the errors below.")
    else:
        form = TimesheetEntryForm(instance=entry, user=request.user)

    projects = Project.objects.filter(active=True)
    projects_available = projects.exists() or (entry and entry.project is not None)
    return render(request, "dashboard/employee_timeentry.html", {
        "form": form,
        "projects": projects,
        "projects_available": projects_available,
        "entry": entry,
    })


@login_required
@role_required("employee")
def delete_entry(request, entry_id):
    entry = get_object_or_404(TimesheetEntry, pk=entry_id, user=request.user)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, "Entry deleted.")
        return redirect('employee_dashboard')
    return render(request, 'dashboard/confirm_delete.html', {'entry': entry})


@role_required('manager')
@login_required
def manager_delete_entry(request, entry_id):
    # Allow manager to delete their own entries (manager-scoped)
    entry = get_object_or_404(TimesheetEntry, pk=entry_id, user=request.user)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, "Entry deleted.")
        return redirect('manager_my_timesheet')
    return render(request, 'dashboard/confirm_delete.html', {'entry': entry})


# ------------------- My Timesheet -------------------
@role_required("employee")
@login_required
def my_timesheet(request):
    week_start, week_end = get_current_week_bounds()
    entries = TimesheetEntry.objects.filter(
        user=request.user,
        work_date__range=(week_start, week_end)
    ).order_by("work_date", "start_time")

    week_summary, _ = WeekSummary.objects.get_or_create(
        user=request.user, week_start=week_start, defaults={"status": STATUS_DRAFT}
    )

    # Compute per-entry hours for template display (hours as float)
    for e in entries:
        if e.duration_minutes is not None:
            e.hours = round(e.duration_minutes / 60.0, 2)
        elif e.start_time and e.end_time:
            delta = e.end_time - e.start_time
            e.hours = round(delta.total_seconds() / 3600, 2)
        else:
            e.hours = 0

    total_minutes = entries.aggregate(total_minutes=Coalesce(Sum("duration_minutes"), 0))["total_minutes"]
    total_hours = round(total_minutes / 60.0, 2)

    context = {
        "entries": entries,
        "week_start": week_start,
        "week_end": week_end,
        "total_hours": total_hours,
        "week_status": week_summary.status,
    }
    return render(request, "dashboard/employee_mytimesheet.html", context)


# ------------------- Reports -------------------
@role_required("employee")
@login_required
def my_reports(request):
    user = request.user
    projects = Project.objects.all().order_by("name")

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    project_id = request.GET.get("project")

    today = dt.date.today()
    def _parse_query_date(s, default):
        if not s:
            return default
        # Normalize common query formats (remove dots from abbreviated months like 'Aug.')
        s_clean = s.replace('.', '').strip()
        # Try a few common formats
        formats = [
            "%Y-%m-%d",
            "%B %d, %Y",  # July 20, 2025
            "%b %d, %Y",  # Jul 20, 2025 or Aug 19, 2025
            "%m/%d/%Y",   # 07/20/2025
            "%d-%m-%Y",
        ]
        for fmt in formats:
            try:
                return dt.datetime.strptime(s_clean, fmt).date()
            except Exception:
                continue
        # Try ISO parse as last resort
        try:
            return dt.date.fromisoformat(s_clean)
        except Exception:
            # Fall back to default and warn the user instead of raising an exception
            messages.warning(request, f"Could not parse date '{s}'; using default range.")
            return default

    start_date = _parse_query_date(start_date, today - dt.timedelta(days=30))
    end_date = _parse_query_date(end_date, today)

    entries_qs = TimesheetEntry.objects.filter(
        user=user,
        work_date__range=(start_date, end_date)
    ).order_by("work_date", "start_time")

    if project_id:
        try:
            entries_qs = entries_qs.filter(project_id=int(project_id))
        except ValueError:
            pass

    entries = []
    for e in entries_qs:
        if e.duration_minutes is not None:
            e.hours = round(e.duration_minutes / 60.0, 2)
        else:
            e.hours = 0
        entries.append(e)

    # Summary
    summary_dict = defaultdict(float)
    for e in entries:
        name = e.project.name if e.project else "Unassigned"
        summary_dict[name] += e.hours
    summary_rows = [{"name": k, "hours": round(v, 2)} for k, v in summary_dict.items()]

    # Chart data
    chart_dict = defaultdict(float)
    for e in entries:
        chart_dict[e.work_date.strftime("%d-%m-%Y")] += e.hours
    chart_labels = list(chart_dict.keys())
    chart_data = [chart_dict[d] for d in chart_labels]

    # CSV Export
    export = request.GET.get("export", "").lower()
    if export in {"summary", "details"}:
        # Use explicit UTF-8 charset and BOM so Excel opens files correctly on Windows.
        filename = f"timesheet_{export}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        # Write UTF-8 BOM
        response.write('\ufeff')
        # Use lineterminator to avoid extra blank lines on some platforms
        writer = csv.writer(response, lineterminator='\n')

        if export == "summary":
            writer.writerow(["Project", "Total Hours"])
            for row in summary_rows:
                name = row.get("name", "")
                hours = row.get("hours", 0)
                writer.writerow([str(name), f"{float(hours):.2f}"])
        else:
            writer.writerow(["Date", "Project", "Start", "End", "Break (min)", "Hours", "Notes"])
            for e in entries:
                date_str = e.work_date.strftime("%d-%m-%Y") if getattr(e, 'work_date', None) else ""
                project_name = e.project.name if getattr(e, 'project', None) else "Unassigned"
                start_str = e.start_time.strftime("%H:%M") if getattr(e, 'start_time', None) else ""
                end_str = e.end_time.strftime("%H:%M") if getattr(e, 'end_time', None) else ""
                break_min = getattr(e, 'break_minutes', 0) or 0
                hours_val = getattr(e, 'hours', 0) or 0
                notes = getattr(e, 'notes', '') or ''
                writer.writerow([date_str, project_name, start_str, end_str, str(break_min), f"{float(hours_val):.2f}", notes])
        return response

    context = {
        "entries": entries,
        "projects": projects,
        "summary_rows": summary_rows,
        "chart_labels": chart_labels,
        "chart_data": chart_data,
        "start_date": start_date,
        "end_date": end_date,
        "selected_project": int(project_id) if project_id else None,
    }
    return render(request, "dashboard/employee_myreport.html", context)
