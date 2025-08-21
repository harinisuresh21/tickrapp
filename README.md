# 🕒 Timesheet & Reporting App

A Django-based Timesheet & Reporting application that allows employees to log their working hours, submit reports, and track tasks. Managers can view submissions, approve/reject reports, and monitor performance through a dashboard.

---

## 🚀 Features

- **Employee Dashboard**
  - Start/stop a timer to track working hours.
  - Submit daily/weekly reports.
  - View personal report history.

- **Manager Dashboard**
  - View employee submissions.
  - Approve/reject reports based on performance.
  - Monitor active tasks and working hours.

- **Authentication**
  - Custom user model (`CustomUser`) for employees and managers.
  - Login, logout, and role-based redirects.

- **Reporting**
  - Detailed report submission by employees.
  - Approval workflow for managers.

- **UI**
  - Bootstrap-based responsive design.
  - Profile dropdown and user-friendly navigation.

---

## ⚙️ Tech Stack

- **Backend:** Django 5.1
- **Frontend:** Bootstrap 5, HTML, CSS
- **Database:** SQLite (development), can be switched to MySQL/PostgreSQL for production
- **Deployment:** PythonAnywhere / AWS
- **Others:** `django-widget-tweaks` for template customization

---

## 📂 Project Structure
timesheet_project/
│── timesheet_app/ # Core app (models, views, templates, static)
│── staticfiles/ # Collected static files for production
│── media/ # Uploaded files (profile pictures, reports)
│── templates/ # HTML templates
│── db.sqlite3 # Database (development)
│── requirements.txt # Dependencies
│── manage.py # Django management script


## 🔧 Installation & Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/timesheet.git
   cd timesheet
   
2.  Create a virtual environment
   python -m venv venv
   source venv/bin/activate   # On Linux/Mac
   venv\Scripts\activate      # On Windows

 3.  Install dependencies
     pip install -r requirements.txt

 4.  Run migrations
     python manage.py migrate

 5.  Create a superuser
     python manage.py createsuperuser

 6.  Run the server
     python manage.py runserver

 7.  Visit http://127.0.0.1:8000/
 
 ---
 
 ## 🌍 Deployment (PythonAnywhere)

Run python manage.py collectstatic

Configure Static files in the PythonAnywhere Web tab:

/static/ → /home/username/timesheet_project/staticfiles

/media/ → /home/username/timesheet_project/media

Reload the web app.

---

## 📌 Future Enhancements

Email notifications for approvals/rejections.

Export reports to Excel/PDF.

Integration with third-party payroll/HR systems.

Enhanced role-based permissions.

