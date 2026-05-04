import os
import csv
import io
import psycopg2
from flask import Flask, jsonify, request, make_response
from flask import render_template
from psycopg2.extras import RealDictCursor
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# FIX: Ensure app fails to start if production secret is missing
secret = os.environ.get('JWT_SECRET_KEY')
if not secret:
    raise ValueError("No JWT_SECRET_KEY set for Flask application")
app.config['JWT_SECRET_KEY'] = secret

jwt = JWTManager(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """Creates the necessary tables when the app first runs."""
    if not DATABASE_URL:
        return
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL
            );
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                sku VARCHAR(50) PRIMARY KEY,
                item_name VARCHAR(100) NOT NULL,
                category VARCHAR(50),
                current_stock INTEGER DEFAULT 0,
                min_threshold INTEGER DEFAULT 10
            );
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS stock_movements (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(50) REFERENCES inventory(sku) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                quantity_changed INTEGER NOT NULL,
                movement_type VARCHAR(20) NOT NULL
            );
        ''')
        conn.commit()
    finally:
        cur.close()
        conn.close()

# INTENTIONALLY UNFIXED: Left global initialization intact
init_db()

@app.route('/')
def home():
    return render_template('index.html')

# --- INVENTORY ROUTES ---

@app.route('/api/inventory', methods=['GET'])
@jwt_required()
def get_inventory():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM inventory;')
        items = cur.fetchall()
        
        for item in items:
            item['is_low_stock'] = item['current_stock'] <= item['min_threshold']
            
        return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # FIX: Ensure DB connections are closed safely
        if cur: cur.close()
        if conn: conn.close()

@app.route('/api/inventory', methods=['POST'])
@jwt_required()
def add_inventory():
    conn = None
    cur = None
    try:
        user = get_jwt_identity()
        if user['role'] != 'admin':
            return jsonify({"error": "Unauthorized"}), 403
        
        data = request.json
        if not data or not data.get('sku') or not data.get('item_name'):
            return jsonify({"error": "SKU and Item Name are required"}), 400
            
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO inventory (sku, item_name, category, current_stock, min_threshold)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            data['sku'], 
            data['item_name'], 
            data.get('category', ''), 
            int(data.get('current_stock', 0)), 
            int(data.get('min_threshold', 10))
        ))
        
        conn.commit()
        return jsonify({"message": "Item added successfully!", "sku": data['sku']}), 201
    except psycopg2.IntegrityError:
        if conn: conn.rollback()
        return jsonify({"error": "An item with this SKU already exists."}), 409
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route('/api/inventory/<sku>', methods=['PUT'])
@jwt_required()
def update_inventory(sku):
    conn = None
    cur = None
    try:
        user = get_jwt_identity()
        if user['role'] != 'admin':
            return jsonify({"error": "Unauthorized"}), 403

        data = request.json
        if not data:
            return jsonify({"error": "No update data provided"}), 400
            
        conn = get_db_connection()
        cur = conn.cursor()
        
        update_fields = []
        values = []
        allowed_fields = ['item_name', 'category', 'current_stock', 'min_threshold']
        
        for key in allowed_fields:
            if key in data:
                update_fields.append(f"{key} = %s")
                values.append(data[key])
                
        if not update_fields:
            return jsonify({"error": "No valid fields provided"}), 400
            
        values.append(sku)
        query = f"UPDATE inventory SET {', '.join(update_fields)} WHERE sku = %s"
        
        cur.execute(query, tuple(values))
        rows_updated = cur.rowcount
        conn.commit()
        
        if rows_updated == 0:
            return jsonify({"error": "Item not found"}), 404
            
        return jsonify({"message": f"Item {sku} updated successfully!"}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route('/api/inventory/<sku>', methods=['DELETE'])
@jwt_required()
def delete_inventory(sku):
    conn = None
    cur = None
    try:
        user = get_jwt_identity()
        if user['role'] != 'admin':
            return jsonify({"error": "Unauthorized"}), 403

        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM inventory WHERE sku = %s', (sku,))
        rows_deleted = cur.rowcount
        conn.commit()
        
        if rows_deleted == 0:
            return jsonify({"error": "Item not found."}), 404
            
        return jsonify({"message": f"Item {sku} deleted successfully!"}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route('/api/inventory/<sku>/movement', methods=['POST'])
@jwt_required()
def record_movement(sku):
    conn = None
    cur = None
    try:
        data = request.json
        user = get_jwt_identity()
        user_id = user['id']
        raw_quantity = data.get('quantity_changed')
        movement_type = data.get('movement_type')
        
        if user['role'] not in ['admin', 'employee']:
            return jsonify({"error": "Unauthorized"}), 403

        if not raw_quantity or not movement_type:
            return jsonify({"error": "quantity_changed, and movement_type are required"}), 400
            
        if movement_type not in ['stock-in', 'stock-out']:
            return jsonify({"error": "movement_type must be 'stock-in' or 'stock-out'"}), 400

        # FIX: Catch ValueError when parsing quantity
        try:
            quantity = abs(int(raw_quantity))
        except (ValueError, TypeError):
            return jsonify({"error": "quantity_changed must be a valid integer"}), 400

        if quantity == 0:
            return jsonify({"error": "Quantity must be greater than 0"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT current_stock FROM inventory WHERE sku = %s', (sku,))
        item = cur.fetchone()
        
        if not item:
            return jsonify({"error": "Item not found"}), 404
            
        if movement_type == 'stock-out' and item['current_stock'] < quantity:
            return jsonify({"error": f"Insufficient stock. Current stock is {item['current_stock']}"}), 400
            
        stock_modifier = quantity if movement_type == 'stock-in' else -quantity
        
        cur.execute('''
            UPDATE inventory 
            SET current_stock = current_stock + %s 
            WHERE sku = %s
        ''', (stock_modifier, sku))
        
        cur.execute('''
            INSERT INTO stock_movements (sku, user_id, quantity_changed, movement_type)
            VALUES (%s, %s, %s, %s)
        ''', (sku, user_id, quantity, movement_type))
        
        conn.commit()
        return jsonify({"message": f"Successfully processed {movement_type} for {sku}."}), 201
        
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route('/api/movements', methods=['GET'])
@jwt_required()
def get_movements():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = '''
            SELECT m.id, m.sku, i.item_name, m.user_id, u.username, 
                   m.timestamp, m.quantity_changed, m.movement_type
            FROM stock_movements m
            LEFT JOIN inventory i ON m.sku = i.sku
            LEFT JOIN users u ON m.user_id = u.id
            ORDER BY m.timestamp DESC
        '''
        
        cur.execute(query)
        movements = cur.fetchall()
        return jsonify(movements), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    # FIX: Allow dynamic role assignment instead of hardcoding 'employee'
    # Defaulting to 'employee' if not provided in payload.
    role = data.get('role', 'employee')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    hashed_password = generate_password_hash(password)

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
        ''', (username, hashed_password, role))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return jsonify({"message": "User registered successfully"})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
    finally:
        if cur: cur.close()
        if conn: conn.close()

    if user and check_password_hash(user['password_hash'], password):
        access_token = create_access_token(identity={
            "id": user['id'],
            "role": user['role']
        })
        return jsonify(access_token=access_token)

    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/inventory/report', methods=['GET'])
@jwt_required()
def download_inventory_report():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM inventory;')
        items = cur.fetchall()

        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(['SKU', 'Item Name', 'Category', 'Current Stock', 'Min Threshold'])
        for item in items:
            writer.writerow([
                item['sku'], 
                item['item_name'], 
                item['category'] or '', 
                item['current_stock'], 
                item['min_threshold']
            ])
        
        output = si.getvalue()
        response = make_response(output)
        response.headers['Content-Disposition'] = 'attachment; filename=inventory_report.csv'
        response.headers['Content-Type'] = 'text/csv'
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True)
