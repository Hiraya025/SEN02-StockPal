import os
import sys
from unittest.mock import patch, MagicMock

# 1. INJECT FAKE ENVIRONMENT VARIABLES
os.environ['JWT_SECRET_KEY'] = 'test-secret-key-123'
os.environ['DATABASE_URL'] = 'postgresql://dummy-test-db'

import pytest
import json
import io
import csv

# 2. INTERCEPT THE DATABASE CONNECTION AT IMPORT TIME
# We must mock the connection *before* app.py finishes loading so init_db() doesn't crash.
with patch('psycopg2.connect') as mock_connect:
    # Set up a fake database connection object
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    
    # Now it is safe to import the app
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
    token = create_access_token(identity={"id": 1, "role": "admin"})
    return {'Authorization': f'Bearer {token}'}

@pytest.fixture
def employee_headers(client):
    """Generates an employee JWT token to test Role-Based Access Control."""
    from flask_jwt_extended import create_access_token
    token = create_access_token(identity={"id": 2, "role": "employee"})
    return {'Authorization': f'Bearer {token}'}

# --- TESTS ---

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

    assert response.status_code == 200
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
    
    assert response.status_code == 201
    assert b"Item added successfully" in response.data
    mock_conn.commit.assert_called_once()

@patch('app.get_db_connection')
def test_add_inventory_employee_unauthorized(mock_db, client, employee_headers):
    """Tests that Role-Based Access Control prevents employees from adding items."""
    payload = {"sku": "NEW-01", "item_name": "Monitor"}

    response = client.post('/api/inventory', data=json.dumps(payload), content_type='application/json', headers=employee_headers)
    
    assert response.status_code == 403
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
    
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/csv; charset=utf-8'
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
    
    assert response.status_code == 200
    assert b"deleted successfully" in response.data
    mock_conn.commit.assert_called_once()
