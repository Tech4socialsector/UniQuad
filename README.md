<p align="center">
  <img src="slcm/public/icons/desktop_icons/subtle/slcm.svg" width="140" alt="SLCM Logo">
</p>

<h1 align="center">SLCM — Student Life Cycle Management</h1>

<p align="center">
  <b>A comprehensive Higher Education & Student Lifecycle Management system built on Frappe Framework.</b>
</p>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-key-features">Key Features</a> •
  <a href="#-required-apps--stack">Required Apps</a> •
  <a href="#-installation-process">Installation</a> •
  <a href="#-development--contributing">Development</a> •
  <a href="#-contact--support">License & Support</a>
</p>

---

## 📌 Overview

**SLCM (Student Life Cycle Management)** is an enterprise-grade ERP application built on top of the [Frappe Framework](https://frappeframework.com). Developed by **Tech4socialsector (TFSS)** / Azim Premji Foundation, SLCM digitizes and automates the complete student journey—from admissions, entrance tests, and merit seat allocations to student onboarding, attendance, fee demands, academic progression, and official transcripts.

---

## ✨ Key Features

### 🎓 Admissions & Applicant Portal
- **Online Application Forms**: Responsive web forms for university degree programs & PACE courses.
- **Seat Allocation & Merit Lists**: Dynamic matrix allocation for entrance tests, interviews, waitlists, and merit list publishing.
- **Scholarships & Financial Aid**: Automated eligibility verification and scholarship distribution.
- **Offer Letters**: Automated offer issuance, acceptance tracking, and payment deadline management.

### 📋 Student Registration & Workflow
- **Multi-Stage Onboarding**: Multi-role verification workflows involving REGO (Registrar), FINO (Finance), IT Admin, and Residence teams.
- **ID Card Generation**: Automated student ID card printing logs and template rendering.

### 🏫 Academic & Attendance Management
- **Course & Timetable Management**: Course offerings, academic terms, and automated Google Calendar timetable sync.
- **RFID & Device Ingestion**: Live HTTP & SQL Server device push for real-time RFID attendance logging.
- **Condonation & FA/MFA**: Student attendance condonation workflows and automated absence alerts for parents.
- **Transcripts**: Official year-based and term-based student academic transcript generation.

### 💳 Fee Management & Payments
- **Fee Demands & Invoices**: Automatic demand generation, due reminders, and late payment reconciliation.
- **Payment Gateway Integration**: Built on top of the standard Frappe `payments` app.

### 🌐 Multi-Portal Access
- **Student Portal**: Course overview, attendance summaries, fee statements, venue booking, and support tickets.
- **Faculty Portal**: Class schedules, live attendance marking, marks entry, and communication.
- **Parent Portal**: Real-time student attendance monitoring, RFID alerts, and fee summaries.

---

## 🛠️ Required Apps & Stack

- **Frappe Framework**: `develop` / v15+
- **Python**: 3.10+
- **Database**: MariaDB / PostgreSQL
- **Required Frappe Apps**:
  - `payments`

---

## 🚀 Installation Process

Install SLCM on your bench CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/Tech4socialsector/SLCM.git --branch develop
bench install-app slcm
```

---

## 💻 Development & Contributing

### Pre-commit Configuration

This repository uses `pre-commit` for linting and code quality. Before pushing, install and configure `pre-commit`:

```bash
cd apps/slcm
pre-commit install
```

Pre-commit runs the following tools:
- **Ruff** (Python linter & formatter)
- **ESLint** & **Prettier** (JavaScript & CSS formatting)
- **Pyupgrade**

### Testing & Code Quality

Run tests using bench CLI:

```bash
bench --site [your-site] run-tests --app slcm
```

Run pre-commit checks manually across all files:

```bash
pre-commit run --all-files
```

---

## 📧 Contact & Support

- **Publisher**: Tech4socialsector (TFSS)
- **Email**: tech4socialsector@azimpremjifoundation.org
- **License**: MIT License
