# Celestial — Intelligent Freelance Workforce Management Platform

<div align="center">

### A next-generation freelance ecosystem built for enterprise-scale collaboration, automation, and intelligent workforce management.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-Backend-black?style=for-the-badge&logo=flask)
![SocketIO](https://img.shields.io/badge/Socket.IO-Real--Time-white?style=for-the-badge&logo=socketdotio)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite)
</div>

---

# Overview

**Celestial** is a powerful full-stack freelance management platform designed to streamline the entire project lifecycle — from client onboarding and proposal generation to intelligent team assignment, phased execution, payroll processing, and real-time collaboration.

Built with a modern architecture using **Flask**, **Socket.IO**, and a responsive SPA frontend, Celestial combines enterprise workflow management with AI-assisted decision systems to create a scalable and immersive operational experience.

---

# Core Features

## Multi-Role Enterprise Architecture

Celestial supports a complete role-based workflow system with dedicated dashboards and permissions for:

- **Admin**
- **Proposal Manager**
- **General Manager**
- **Client**
- **Team Leader**
- **Team Member**
- **Freelancer**
- **Accountant**
- **Bank Representative**

Each role has its own:
- Dashboard
- Permissions
- Notifications
- Workflow tools
- Financial visibility
- Real-time updates

---

# Complete Project Lifecycle Management

Manage projects seamlessly from start to finish:

```text
Client Request
    ↓
Proposal Creation
    ↓
Client Approval & Deposit
    ↓
Team Assignment
    ↓
AI-Assisted Phase Division
    ↓
Task Distribution
    ↓
Submission & Review
    ↓
Final Delivery
    ↓
Salary & Payment Processing
```

---

# Intelligent Automation Systems

## Reinforcement Learning Phase Division
Celestial uses a Q-learning inspired recommendation engine to intelligently suggest optimal project phase structures based on:

- Project complexity
- Required skills
- Historical GM evaluations
- Freelancer performance metrics
- Task completion efficiency

## Smart Skill Matching
The platform automatically ranks freelancers and team members using:
- Compatibility scoring
- Experience weighting
- Performance history
- Skill alignment
- Availability tracking

---

# Real-Time Collaboration

Powered by **Flask-SocketIO**, Celestial delivers live updates across the platform:

- Instant notifications
- Proposal updates
- Task activity
- Phase completion alerts
- Live dashboard synchronization
- Financial transaction updates
- Role-based room messaging

---

# Financial Management System

The built-in financial engine supports:

- Client deposits
- Remaining balance tracking
- Payroll processing
- Freelancer payouts
- Bulk salary operations
- Ledger management
- Transaction monitoring
- Bank-side auditing visibility

---

# Gamified Productivity System

Celestial introduces a progression-based freelancer ecosystem:

- Quest system
- Performance levels
- Training centers
- Achievement tracking
- Team ratings
- Productivity rewards

This encourages higher engagement and measurable growth within teams.

---

# User Experience & Interface

## Modern Cosmic Design System
- Galaxy-inspired UI
- Dark & light themes
- Animated nebula backgrounds
- Responsive layouts
- Smooth transitions
- Interactive dashboards
- Data visualization support

## Responsive SPA Frontend
The frontend is built as a high-performance single-page application with:
- Fast navigation
- Dynamic rendering
- Live state updates
- Mobile-friendly layouts

---

# Technology Stack

## Backend
- **Python**
- **Flask**
- **Flask-SocketIO**
- **SQLite (WAL Mode)**
- **Werkzeug Security**
- REST-style architecture
- RBAC middleware

## Frontend
- HTML5
- CSS3
- Vanilla JavaScript
- Socket.IO Client
- Chart.js

## AI & Automation
- Reinforcement Learning Engine
- Skill Matching Algorithm
- Smart Ranking Logic

---

# Project Structure

```text
celestial-platform/
│
├── app.py                         # Main Flask application
├── config.py                      # Application configuration
├── database.py                    # Database schema & helpers
├── rl_engine.py                   # RL phase division engine
├── socket_events.py               # Real-time socket handlers
│
├── routes/
│   ├── auth.py
│   ├── admin.py
│   ├── pm.py
│   ├── gm.py
│   ├── tl.py
│   ├── member.py
│   ├── freelancer.py
│   ├── accountant.py
│   ├── bank.py
│   └── shared.py
│
├── utils/
│   └── notify.py                  # Notification utilities
│
├── index.html                     # Main SPA frontend
├── celestial.db                   # SQLite database
├── attachments/                   # Uploaded files
└── README.md
```

---

# Prerequisites

Before running the project, ensure you have:

- **Python 3.8+**
- **pip**
- Modern browser:
  - Chrome
  - Firefox
  - Edge

---

# Installation

## 1️⃣ Clone the Repository

```bash
git clone https://github.com/yourusername/celestial-platform.git
cd celestial-platform
```

---

## 2️⃣ Create a Virtual Environment

### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS
```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install flask flask-cors flask-socketio werkzeug
```

Optional frontend dependency:

```bash
npm install socket.io-client
```

---

# Database Initialization

The SQLite database (`celestial.db`) is automatically initialized on startup with:
- Tables
- Relationships
- Seed accounts
- Default demo data

WAL journaling mode is enabled for improved concurrency and reliability.

---

# Running the Application

Start the Flask server:

```bash
python app.py
```

Application URL:

```text
http://localhost:5000
```

---

# Demo Accounts

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Admin |
| `pm` | `pm123` | Proposal Manager |
| `gm` | `gm123` | General Manager |
| `acc` | `acc123` | Accountant |
| `bank` | `bank123` | Bank Representative |
| `tl1` | `tl123` | Team Leader |
| `fl1` | `fl123` | Freelancer |
| `client1` | `client123` | Client |

---

# 📡 Real-Time Features

Celestial includes a complete live communication layer:

- Real-time notifications
- Live dashboard updates
- Instant proposal alerts
- Task activity synchronization
- Submission status tracking
- Phase completion broadcasts
- Financial event updates

---

# Security & Architecture

## RBAC (Role-Based Access Control)
Access to routes and actions is secured through:
- Permission decorators
- Role validation
- Protected APIs
- Session-based authentication

## Audit & Logging
The platform maintains:
- Activity logs
- Financial records
- Submission history
- User actions
- Workflow tracking

---

# 🧪 Development Workflow

## Adding a New Role

### 1. Add Role Definition
Update:
```python
ROLES = [...]
```

### 2. Create Blueprint
```text
routes/new_role.py
```

### 3. Register Blueprint
Inside:
```python
app.py
```

### 4. Configure Redirects
Update:
```python
ROLE_REDIRECTS
```

---

# Future Improvements

Planned upgrades include:

- JWT authentication
- PostgreSQL migration
- AI proposal generation
- Integrated messaging system
- Video meeting support
- Analytics dashboard
- Docker deployment
- Kubernetes scaling
- REST API documentation
- Machine learning recommendations

---

# Contributing

Contributions are welcome and appreciated.

## Contribution Workflow

```bash
# Fork the repository

# Create a feature branch
git checkout -b feature/amazing-feature

# Commit changes
git commit -m "Add amazing feature"

# Push branch
git push origin feature/amazing-feature
```

Then open a Pull Request.

---


# Acknowledgments

Celestial was built as an advanced demonstration of:
- Enterprise-grade Flask architecture
- Real-time collaborative systems
- AI-assisted project management
- Modern SPA design principles
- Intelligent freelance ecosystem workflows

Inspired by modern:
- Freelance marketplaces
- Agile management systems
- Enterprise collaboration platforms
