# Frontdesk – Ticket Management System

Frontdesk is a web-based ticket management system developed using Django. It helps manage customer support requests through ticket creation, assignment, status tracking, and Service Level Agreement (SLA) monitoring.

## Features

- **Ticket Management:** Create, view, and manage customer support tickets.
- **User Management:** Manage different user accounts and roles.
- **Ticket Assignment:** Assign tickets to support agents and managers.
- **Status Tracking:** Track ticket progress, including open, waiting, resolved, and closed states.
- **SLA Management:** Configure response and resolution time limits based on ticket priority.
- **SLA Monitoring:** Track remaining SLA time and pause SLA calculations while waiting for a customer response.
- **Ticket Reopening:** Reopen eligible closed tickets.
- **Activity Tracking:** Maintain records of ticket-related activities.
- **Automatic Ticket Closure:** Includes a management command to close tickets that exceed the configured customer-response waiting period.

## Technologies Used

| Category | Technology |
|---|---|
| Backend | Python, Django |
| API Framework | Django REST Framework |
| Frontend | HTML, CSS, JavaScript, Django Templates |
| Database | SQLite, MySQL, PostgreSQL |
| Static Files | WhiteNoise |
| Deployment | PythonAnywhere |
| Server | Gunicorn |

## Project Structure

```text
Frontdesk/
│
├── accounts/       # User accounts and authentication
├── audit/          # Activity and audit records
├── config/         # Django project configuration
├── customers/      # Customer management
├── dashboard/      # Dashboard functionality
├── sla/            # SLA configuration and calculations
├── tickets/        # Ticket management
├── static/         # CSS, JavaScript and static assets
├── templates/      # HTML templates
├── manage.py       # Django management utility
├── requirements.txt
├── render.yaml
└── .env.example    # Example environment configuration
```

## Installation and Setup

### 1. Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd Frontdesk
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

**Windows:**
```bash
venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file using the example configuration:

```bash
cp .env.example .env
```

Update the values in `.env`, especially:

```env
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DB_ENGINE=sqlite
DATABASE_URL=
```

Never commit your actual `.env` file or expose your Django secret key.

### 5. Apply Database Migrations

```bash
python manage.py migrate
```

### 6. Create an Administrator Account

```bash
python manage.py createsuperuser
```

Follow the prompts to create the administrator account.

### 7. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### 8. Run the Development Server

```bash
python manage.py runserver
```

Open the application at:

```text
http://127.0.0.1:8000/
```

## Automatic Ticket Closure

Frontdesk includes a Django management command for automatically closing tickets that have exceeded the configured customer-response waiting period.

The waiting period can be configured through:

```env
SLA_AUTO_CLOSE_BUSINESS_DAYS=5
```

Run the command manually using:

```bash
python manage.py close_waiting_tickets
```

For automatic execution, configure the command as a scheduled task on the deployment platform.

## Deployment

The application is deployed on PythonAnywhere.

**Live Application:**

https://thara.pythonanywhere.com

Production deployment requires appropriate environment variables, database configuration, static-file configuration, and secure secret-key management.

## Security Notes

- Keep `.env` files private.
- Use a strong, unique Django secret key.
- Disable Django debug mode in production.
- Configure allowed hosts and trusted CSRF origins correctly.
- Never commit passwords, secret keys, or database credentials to GitHub.

## License

This project is developed as a software development assignment.
