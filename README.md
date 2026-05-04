# 📦 StockPal: Inventory Management System

[![Live Demo](https://img.shields.io/badge/Live_Demo-Vercel-black?style=for-the-badge&logo=vercel)](https://sen-02-stock-pal.vercel.app/)
[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge&logo=github)](https://github.com/Hiraya025/SEN02-StockPal)

**StockPal** is a lightweight, secure, and intuitive web-based inventory management system designed to help businesses track stock levels, monitor movements, and manage user access. 

This repository and document serve as the final software prototype and engineering documentation for our Software Engineering course.

---

## 🚀 Live Application
Access the deployed web application here: **[StockPal on Vercel](https://sen-02-stock-pal.vercel.app/)**

---

## ✨ Key Features

* **Role-Based Access Control (RBAC):** Secure JWT-based authentication supporting `Admin` and `Employee` roles with distinct permission levels.
* **Inventory Dashboard:** Real-time overview of all stock, categorized and searchable.
* **Automated Low-Stock Alerts:** Visual indicators flag items that fall below user-defined minimum threshold levels.
* **Stock Movement Auditing:** A comprehensive, immutable log of all stock-in and stock-out transactions, tracking who made the change, when, and by how much.
* **Data Export:** One-click generation of CSV reports for current inventory levels.
* **Admin User Management:** Dedicated interface for administrators to create and manage system user accounts.

---

## 🛠️ Technology Stack

This project adheres to modern software engineering practices, utilizing a decoupled architecture and robust testing methodologies.

* **Backend:** Python 3, Flask
* **Database:** PostgreSQL (with `psycopg2` for database operations)
* **Authentication:** JSON Web Tokens (`flask-jwt-extended`), Werkzeug password hashing
* **Frontend:** HTML5, CSS3, Vanilla JavaScript, Bootstrap 5
* **Testing:** `pytest` (Unit and Integration testing with mocking)
* **Deployment:** Vercel (CI/CD via `vercel.json`)

---

## 💻 Local Development Setup

To run StockPal locally on your machine, follow these steps:

### 1. Prerequisites
* Python 3.8+ installed
* PostgreSQL database server running locally or accessible via URL.

### 2. Clone the Repository
```bash
git clone [https://github.com/Hiraya025/SEN02-StockPal.git](https://github.com/Hiraya025/SEN02-StockPal.git)
cd SEN02-StockPal
```

### 3. Set Up a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a .env file in the root directory
```Code snippet
JWT_SECRET_KEY=your_super_secret_jwt_key_here
DATABASE_URL=postgresql://username:password@localhost:5432/stockpal_db
```

### 5. Run the Application
The application will automatically initialize the database tables on startup.
```bash
python app.py
```
_Note: If the database is completely empty upon startup, the system will automatically seed an initial administrator account (Username: admin, Password: admin123)_

---

## 🧪 Quality Assurance & Testing Logs (Evidence of Software Quality)

To ensure high software quality, maintainability, and security, we implemented an automated test suite using pytest. The tests heavily utilize the unittest.mock library to simulate database connections and interactions, allowing us to test our API logic and Role-Based Access Control (RBAC) in isolation without risking database corruption.

### Automated Test Execution Output
Below is the console output from our final test run, verifying that all core functionalities, access controls, and edge cases perform as expected.
```Shell
$ python -m pytest test_app.py -v
======================== test session starts =========================
platform win32 -- Python 3.14.0, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\robrob\AppData\Local\Python\pythoncore-3.14-64\python.exe
cachedir: .pytest_cache
rootdir: C:\ROB\SEN02\SEN02-StockPal
collected 8 items                                                     

test_app.py::test_unauthenticated_access PASSED                 [ 12%]
test_app.py::test_get_inventory_and_low_stock_logic PASSED      [ 25%]
test_app.py::test_add_inventory_admin PASSED                    [ 37%]
test_app.py::test_add_inventory_duplicate_sku PASSED            [ 50%]
test_app.py::test_add_inventory_employee_unauthorized PASSED    [ 62%]
test_app.py::test_download_inventory_report PASSED              [ 75%]
test_app.py::test_delete_inventory_item PASSED                  [ 87%]
test_app.py::test_record_stock_movement_audit PASSED            [100%]

========================= 8 passed in 0.47s ==========================
```

### Testing Breakdown:
  1. test_unauthenticated_access: Validates that the API strictly blocks requests to protected routes if no JWT is provided, returning a 401 Unauthorized error.
  2. test_get_inventory_and_low_stock_logic: Validates that the GET /api/inventory route successfully retrieves items and correctly calculates the is_low_stock boolean flag based on current stock vs. threshold.
  3. test_add_inventory_admin: Verifies that a user with an admin JWT claim can successfully POST new items to the database and receives a 201 Created response.
  4. test_add_inventory_duplicate_sku: Tests edge-case database handling; ensures that attempting to add an existing SKU gracefully throws a 409 Conflict error and rolls back the transaction without crashing the server.
  5. test_add_inventory_employee_unauthorized: Validates our RBAC security protocol. Ensures that if an employee attempts to execute an admin-level POST request, the API blocks the action and returns a 403 Forbidden error.
  6. test_download_inventory_report: Confirms the CSV export functionality properly formats the database records and returns the correct text/csv headers for immediate browser download.
  7. test_delete_inventory_item: Ensures the DELETE endpoint safely removes items and triggers the correct database commit sequence.
  8. test_record_stock_movement_audit: Proves that when an employee executes a stock movement, the system successfully extracts their user_id from the JWT payload and securely binds it to the immutable audit log in the database.

---

## 📈 Version Control

To manage our collaborative workload and ensure code stability, our team utilized Git for version control.

---

## 👥 Development Team
This project was built collaboratively by a four-person team. Tasks were divided evenly across frontend UI/UX development, backend API engineering, database management, and deployment/testing.

* Roman IV R. Canlas - Backend/Database Lead
* Carlo Glenn F. Dalusung - Frontend/Design Lead
* Robert Benj S. Manuel - Analytics, Testing, & Team Lead
* Emmanuel James V. Sagcal - Security Lead
