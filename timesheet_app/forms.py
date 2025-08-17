from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import TimesheetEntry, Project

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
        user.role = self.cleaned_data["role"]  # ✅ Save role
        if commit:
            user.save()
        return user


class TimesheetEntryForm(forms.ModelForm):
    # ✅ Override billable to use Yes/No radios
    billable = forms.ChoiceField(
        choices=[(True, "Yes"), (False, "No")],
        widget=forms.RadioSelect,
        label="Billable",
    )

    class Meta:
        model = TimesheetEntry
        fields = [
            "project",
            "work_date",
            "start_time",
            "end_time",
            "break_minutes",
            "billable",
            "notes",
        ]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "start_time": forms.TimeInput(attrs={"type": "time", "required": True}),
            "end_time": forms.TimeInput(attrs={"type": "time", "required": True}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)  # ✅ capture logged-in user
        super().__init__(*args, **kwargs)

        # make required fields explicit (server-side, not just HTML)
        for field in ["work_date", "start_time", "end_time", "break_minutes", "billable"]:
            self.fields[field].required = True
        self.fields["notes"].required = False

        # project is optional now (to prevent IntegrityError if empty)
        self.fields["project"].required = False
        self.fields["project"].queryset = Project.objects.filter(active=True)

        # ✅ Ensure user is set on the instance immediately
        if self.user:
            self.instance.user = self.user

    def clean_billable(self):
        """Convert 'True'/'False' string back to boolean."""
        value = self.cleaned_data["billable"]
        return value == "True"

    def clean(self):
        cleaned_data = super().clean()
        # ✅ reinforce user assignment before model.clean() runs
        if self.user:
            self.instance.user = self.user
        return cleaned_data

    def save(self, commit=True):
        entry = super().save(commit=False)
        if self.user:
            entry.user = self.user
        if commit:
            entry.save()
        return entry
