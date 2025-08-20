from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser
from datetime import datetime
from django.db.models.signals import post_save
from django.dispatch import receiver
import os

# ------------------- Constants -------------------
ROLE_EMPLOYEE = "employee"
ROLE_MANAGER = "manager"

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

ROLE_CHOICES = [
    (ROLE_EMPLOYEE, "Employee"),
    (ROLE_MANAGER, "Manager"),
]

STATUS_CHOICES = [
    (STATUS_DRAFT, "Draft"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_REJECTED, "Rejected"),
]

# ------------------- Custom User -------------------
class CustomUser(AbstractUser):
    """Custom user model with role selection"""
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.username} ({self.role})"


# ------------------- Profile (avatar) -------------------
def avatar_upload_to(instance, filename):
    # store uploads under media/avatars/<username>/<filename>
    base, ext = os.path.splitext(filename)
    return f"avatars/{instance.user.username}/{base}{ext}"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to=avatar_upload_to, null=True, blank=True)

    def __str__(self):
        return f"Profile for {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

# ------------------- Project -------------------
class Project(models.Model):
    """Project for timesheet entries"""
    name = models.CharField(max_length=120)
    client = models.CharField(max_length=120)
    billable_default = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.client})"

# ------------------- Timesheet Entry -------------------
class TimesheetEntry(models.Model):
    """Individual timesheet entry for an employee"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, null=True, blank=True)
    work_date = models.DateField(null=False, blank=False)
    # start_time should be set explicitly (either by the timer or the form)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    break_minutes = models.PositiveIntegerField(default=0)
    duration_minutes = models.PositiveIntegerField(default=0, editable=False)
    billable = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "work_date"]),
            models.Index(fields=["project", "work_date"]),
        ]
        ordering = ["work_date", "start_time"]

    def clean(self):
        """Validate timesheet logic"""
        # Skip validation if required fields are missing. Use user_id to avoid RelatedObjectDoesNotExist
        if not getattr(self, 'user_id', None) or not self.work_date or not self.start_time or not self.end_time:
            return

        # start_time and end_time may already be datetimes; ensure we have proper datetimes
        start_dt = self.start_time if isinstance(self.start_time, datetime) else datetime.combine(self.work_date, self.start_time)
        end_dt = self.end_time if isinstance(self.end_time, datetime) else datetime.combine(self.work_date, self.end_time)

        if end_dt <= start_dt:
            raise ValidationError("End time must be after start time.")

        raw_minutes = int((end_dt - start_dt).total_seconds() // 60) - self.break_minutes
        if raw_minutes <= 0:
            raise ValidationError("Duration must be greater than zero after break.")

        # Prevent overlapping entries for the same user/day
        qs = TimesheetEntry.objects.filter(user=self.user, work_date=self.work_date)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        for e in qs:
            if not (self.end_time <= e.start_time or self.start_time >= e.end_time):
                raise ValidationError("Overlapping entry for this day exists.")

        # Store duration_minutes for later calculations
        self.duration_minutes = raw_minutes

    def __str__(self):
        return f"{self.user} · {self.project} · {self.work_date}"

# ------------------- Week Summary -------------------
class WeekSummary(models.Model):
    """Summary of weekly timesheet entries"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    week_start = models.DateField(help_text="Monday date of the week")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_weeks",
        null=True,
        blank=True
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    audit_note = models.TextField(blank=True)
    # Manager's comment or feedback when approving/rejecting
    manager_comment = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("user", "week_start")

    def __str__(self):
        return f"{self.user} · {self.week_start} · {self.status}"
