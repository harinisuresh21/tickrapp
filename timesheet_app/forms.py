from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import TimesheetEntry, Project
from django.utils import timezone
import datetime as _dt
from django.core.exceptions import ValidationError

User = get_user_model()

ROLE_CHOICES = (
    ("employee", "Employee"),
    ("manager", "Manager"),
)

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.RadioSelect)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "role")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user


class TimesheetEntryForm(forms.ModelForm):
    billable = forms.ChoiceField(
        choices=[(True, "Yes"), (False, "No")],
        widget=forms.RadioSelect,
        label="Billable",
    )
    # Separate time inputs (combined with work_date in view/validation)
    start_time_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}), label="Start Time")
    end_time_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}), label="End Time")

    class Meta:
        model = TimesheetEntry
        # ✅ Exclude start_time, end_time, and hours; set them in backend
        fields = [
            "project",
            "work_date",
            # times handled separately
            "break_minutes",
            "billable",
            "notes",
        ]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "break_minutes": forms.NumberInput(attrs={"min": 0}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Required fields
        for field in ["work_date", "break_minutes", "billable"]:
            self.fields[field].required = True
        self.fields["notes"].required = False

        # Project is optional
        self.fields["project"].required = False
        # Default queryset: active projects
        qs = Project.objects.filter(active=True)
        # If editing and the instance has a project that is inactive, include it so the field can show current value
        try:
            inst_proj = getattr(self.instance, 'project', None)
            if inst_proj and inst_proj.pk and not qs.filter(pk=inst_proj.pk).exists():
                qs = (Project.objects.filter(active=True) | Project.objects.filter(pk=inst_proj.pk)).distinct()
        except Exception:
            pass
        self.fields["project"].queryset = qs
        # Show an empty label for unassigned
        if hasattr(self.fields["project"], 'empty_label'):
            self.fields["project"].empty_label = "Unassigned"

        if self.user:
            self.instance.user = self.user

        # If editing an existing instance, populate time fields
        if self.instance and getattr(self.instance, 'start_time', None):
            self.fields['start_time_time'].initial = self.instance.start_time.time()
        if self.instance and getattr(self.instance, 'end_time', None):
            self.fields['end_time_time'].initial = self.instance.end_time.time()

    def clean(self):
        cleaned = super().clean()
        work_date = cleaned.get('work_date')
        start_t = cleaned.get('start_time_time')
        end_t = cleaned.get('end_time_time')

        # If times provided, ensure logical ordering
        if start_t and end_t:
            start_dt = _dt.datetime.combine(work_date, start_t)
            end_dt = _dt.datetime.combine(work_date, end_t)
            if end_dt <= start_dt:
                raise ValidationError('End time must be after start time.')

        # Prevent overlapping entries for this user on the same date
        if self.user and work_date and start_t and end_t:
            tz = timezone.get_current_timezone()
            new_start = timezone.make_aware(_dt.datetime.combine(work_date, start_t), tz)
            new_end = timezone.make_aware(_dt.datetime.combine(work_date, end_t), tz)
            qs = TimesheetEntry.objects.filter(user=self.user, work_date=work_date)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            for e in qs:
                e_start = e.start_time
                # If existing entry lacks a start_time, skip it (cannot reliably compare)
                if not e_start:
                    continue
                e_end = e.end_time or (timezone.now() + _dt.timedelta(days=365))

                # Ensure both sides are timezone-aware before comparing
                tz = timezone.get_current_timezone()
                try:
                    from django.utils import timezone as dj_tz
                    # normalize existing entry datetimes if naive
                    if hasattr(e_start, 'tzinfo') and dj_tz.is_naive(e_start):
                        e_start = dj_tz.make_aware(e_start, tz)
                    if e_end and hasattr(e_end, 'tzinfo') and dj_tz.is_naive(e_end):
                        e_end = dj_tz.make_aware(e_end, tz)
                except Exception:
                    # ignore normalization failures and rely on DB-stored datetimes
                    pass

                # overlap if not (new_end <= e_start or new_start >= e_end)
                if not (new_end <= e_start or new_start >= e_end):
                    raise ValidationError('This time range overlaps an existing entry.')

        return cleaned

    def clean_billable(self):
        """Convert 'True'/'False' string back to boolean."""
        value = self.cleaned_data["billable"]
        return value == "True"

    def save(self, commit=True):
        entry = super().save(commit=False)
        if self.user:
            entry.user = self.user
        if commit:
            entry.save()
        return entry
