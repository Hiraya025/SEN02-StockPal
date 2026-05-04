import os
import sys
from unittest.mock import patch, MagicMock

# 1. INJECT FAKE ENVIRONMENT VARIABLES
os.environ['JWT_SECRET_KEY'] = 'super-secret-test-key-that-is-long-enough-for-hs256'
os.environ['DATABASE_URL'] = 'postgresql://dummy-test-db'

import pytest
import json
import psycopg2

# 2. INTERCEPT THE DATABASE CONNECTION AT IMPORT TIME
with patch('psycopg2.connect') as mock_connect:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    from app import app

@pytest.fixture
def client():
    """Sets up a test client for the Flask application."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            yield client

@pytest.fixture
def admin_headers(client):
    """Generates an admin JWT token for protected routes."""
    from flask_jwt_extended import create_access_token
    token = create_access_token(identity="admin", additional_claims={"id": 1, "role": "admin"})
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return {'Authorization': f'Bearer {token}'}

@pytest.fixture
def employee_headers(client):
    """Generates an employee JWT token to test Role-Based Access Control."""
    from flask_jwt_extended import create_access_token
    token = create_access_token(identity="employee", additional_claims={"id": 2, "role": "employee"})
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return {'Authorization': f'Bearer {token}'}

# --- TESTS ---

# ---------------------------------------------------------
# Test SEC-01: Unauthenticated Access
# ---------------------------------------------------------
def test_unauthenticated_access(client):
    """Tests that accessing a protected route without a JWT returns 401."""
    response = client.get('/api/inventory')
    
    assert response.status_code == 401
    assert b"Missing Authorization Header" in response.data

@patch('app.get_db_connection')
def test_get_inventory_and_low_stock_logic(mock_db, client, admin_headers):
    """Tests fetching inventory and verifies the low-stock boolean logic."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    
    mock_cur.fetchall.return_value = [
        {"sku": "ITEM-01", "item_name": "Chair", "current_stock": 50, "min_threshold": 10},
        {"sku": "ITEM-02", "item_name": "Desk", "current_stock": 5, "min_threshold": 10}
    ]

    response = client.get('/api/inventory', headers=admin_headers)
    data = json.loads(response.data)

    assert response.status_code == 200, f"API Failed: {response.data.decode('utf-8')}"
    assert len(data) == 2
    assert data[0]['is_low_stock'] is False
    assert data[1]['is_low_stock'] is True

@patch('app.get_db_connection')
def test_add_inventory_admin(mock_db, client, admin_headers):
    """Tests that an admin can successfully add an item."""
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn

    payload = {
        "sku": "NEW-01",
        "item_name": "Monitor",
        "category": "Electronics",
        "current_stock": 20,
        "min_threshold": 5
    }

    response = client.post('/api/inventory', data=json.dumps(payload), content_type='application/json', headers=admin_headers)
    
    assert response.status_code == 201, f"API Failed: {response.data.decode('utf-8')}"
    assert b"Item added successfully" in response.data
    mock_conn.commit.assert_called_once()

# ---------------------------------------------------------
# Test DB-02: Duplicate SKU Error Handling
# ---------------------------------------------------------
@patch('app.get_db_connection')
def test_add_inventory_duplicate_sku(mock_db, client, admin_headers):
    """Tests that adding an existing SKU correctly throws a 409 Conflict error."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur

    # Simulate the PostgreSQL database throwing a unique constraint error
    mock_cur.execute.side_effect = psycopg2.IntegrityError("duplicate key value violates unique constraint")

    payload = {"sku": "EXISTING-01", "item_name": "Keyboard"}
    response = client.post('/api/inventory', data=json.dumps(payload), content_type='application/json', headers=admin_headers)

    assert response.status_code == 409
    assert b"already exists" in response.data
    mock_conn.rollback.assert_called_once() # Verify the transaction was rolled back

@patch('app.get_db_connection')
def test_add_inventory_employee_unauthorized(mock_db, client, employee_headers):
    """Tests that Role-Based Access Control prevents employees from adding items."""
    payload = {"sku": "NEW-01", "item_name": "Monitor"}

    response = client.post('/api/inventory', data=json.dumps(payload), content_type='application/json', headers=employee_headers)
    
    assert response.status_code == 403, f"API Failed: {response.data.decode('utf-8')}"
    assert b"Unauthorized" in response.data

@patch('app.get_db_connection')
def test_download_inventory_report(mock_db, client, admin_headers):
    """Tests the CSV export functionality."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    
    mock_cur.fetchall.return_value = [
        {"sku": "ITEM-01", "item_name": "Chair", "category": "Furniture", "current_stock": 50, "min_threshold": 10}
    ]

    response = client.get('/api/inventory/report', headers=admin_headers)
    
    assert response.status_code == 200, f"API Failed: {response.data.decode('utf-8')}"
    assert 'text/csv' in response.headers['Content-Type']
    assert response.headers['Content-Disposition'] == 'attachment; filename=inventory_report.csv'
    
    csv_content = response.data.decode('utf-8')
    assert "SKU,Item Name,Category,Current Stock,Min Threshold" in csv_content
    assert "ITEM-01,Chair,Furniture,50,10" in csv_content

@patch('app.get_db_connection')
def test_delete_inventory_item(mock_db, client, admin_headers):
    """Tests that an item can be deleted."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    
    mock_cur.rowcount = 1

    response = client.delete('/api/inventory/ITEM-01', headers=admin_headers)
    
    assert response.status_code == 200, f"API Failed: {response.data.decode('utf-8')}"
    assert b"deleted successfully" in response.data
    mock_conn.commit.assert_called_once()

# ---------------------------------------------------------
# Test AUD-01: Audit Trail Verification
# ---------------------------------------------------------
@patch('app.get_db_connection')
def test_record_stock_movement_audit(mock_db, client, employee_headers):
    """Tests that stock movements accurately log the ID of the user performing the action."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur

    # Mock the initial check for current stock level
    mock_cur.fetchone.return_value = {"current_stock": 50}

    payload = {
        "movement_type": "stock-in",
        "quantity_changed": 15
    }

    response = client.post('/api/inventory/ITEM-01/movement', data=json.dumps(payload), content_type='application/json', headers=employee_headers)

    assert response.status_code == 201
    mock_conn.commit.assert_called_once()

    # The backend route runs 3 queries: SELECT, UPDATE, then INSERT. 
    # We grab the arguments from the 3rd query (the INSERT into stock_movements)
    insert_call_args = mock_cur.execute.call_args_list[2][0] 
    query_vars = insert_call_args[1]
    
    # The employee_headers fixture provides a JWT with an ID of 2.
    # The second variable in the INSERT query is the user_id. We assert it matches the JWT.
    assert query_vars[1] == 2, f"Expected user_id 2 in audit log, but got {query_vars[1]}"
