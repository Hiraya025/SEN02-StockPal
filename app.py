import os
import psycopg2
from flask import Flask, jsonify, request
from flask import render_template
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Fetch the database URL from Vercel's environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    """Creates the necessary tables when the app first runs."""
    if not DATABASE_URL:
        return
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create Users Table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL
        );
    ''')
    
    # Create Inventory Table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            sku VARCHAR(50) PRIMARY KEY,
            item_name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            current_stock INTEGER DEFAULT 0,
            min_threshold INTEGER DEFAULT 10
        );
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

# Initialize the database tables
init_db()

@app.route('/')
def home():
    return render_template('index.html')

# --- INVENTORY ROUTES ---

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    """Fetches all items and flags the ones below minimum threshold."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM inventory;')
        items = cur.fetchall()
        cur.close()
        conn.close()
        
        # Analytics / Low-Stock Alert Logic
        for item in items:
            item['is_low_stock'] = item['current_stock'] <= item['min_threshold']
            
        return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/inventory', methods=['POST'])
def add_inventory():
    """Adds a new item to the inventory."""
    try:
        data = request.json
        
        # Basic validation
        if not data or not data.get('sku') or not data.get('item_name'):
            return jsonify({"error": "SKU and Item Name are required"}), 400
            
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert the new item
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
        cur.close()
        conn.close()
        
        return jsonify({"message": "Item added successfully!", "sku": data['sku']}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "An item with this SKU already exists."}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/inventory/<sku>', methods=['DELETE'])
def delete_inventory(sku):
    """Deletes an item from the inventory."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM inventory WHERE sku = %s', (sku,))
        rows_deleted = cur.rowcount
        
        conn.commit()
        cur.close()
        conn.close()
        
        if rows_deleted == 0:
            return jsonify({"error": "Item not found."}), 404
            
        return jsonify({"message": f"Item {sku} deleted successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
