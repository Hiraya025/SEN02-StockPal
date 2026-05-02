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

    # Create Stock Movements Table
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

@app.route('/api/inventory/<sku>', methods=['PUT'])
def update_inventory(sku):
    """Updates an existing item in the inventory."""
    try:
        data = request.json
        
        if not data:
            return jsonify({"error": "No update data provided"}), 400
            
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Dynamically build the update query based on provided keys
        update_fields = []
        values = []
        
        allowed_fields = ['item_name', 'category', 'current_stock', 'min_threshold']
        
        for key in allowed_fields:
            if key in data:
                update_fields.append(f"{key} = %s")
                values.append(data[key])
                
        if not update_fields:
            return jsonify({"error": "No valid fields provided to update"}), 400
            
        values.append(sku)
        query = f"UPDATE inventory SET {', '.join(update_fields)} WHERE sku = %s"
        
        cur.execute(query, tuple(values))
        rows_updated = cur.rowcount
        
        conn.commit()
        cur.close()
        conn.close()
        
        if rows_updated == 0:
            return jsonify({"error": "Item not found."}), 404
            
        return jsonify({"message": f"Item {sku} updated successfully!"}), 200
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

@app.route('/api/inventory/<sku>/movement', methods=['POST'])
def record_movement(sku):
    """Records a stock-in or stock-out and updates current stock transactionally."""
    try:
        data = request.json
        user_id = data.get('user_id')
        quantity = data.get('quantity_changed')
        movement_type = data.get('movement_type') # Expects 'stock-in' or 'stock-out'
        
        if not all([user_id, quantity, movement_type]):
            return jsonify({"error": "user_id, quantity_changed, and movement_type are required"}), 400
            
        if movement_type not in ['stock-in', 'stock-out']:
            return jsonify({"error": "movement_type must be 'stock-in' or 'stock-out'"}), 400

        # Ensure quantity is positive for our math
        quantity = abs(int(quantity))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Verify item exists and check stock levels
        cur.execute('SELECT current_stock FROM inventory WHERE sku = %s', (sku,))
        item = cur.fetchone()
        
        if not item:
            cur.close()
            conn.close()
            return jsonify({"error": "Item not found"}), 404
            
        if movement_type == 'stock-out' and item['current_stock'] < quantity:
            cur.close()
            conn.close()
            return jsonify({"error": f"Insufficient stock. Current stock is {item['current_stock']}"}), 400
            
        # Determine the modifier for the SQL update
        stock_modifier = quantity if movement_type == 'stock-in' else -quantity
        
        # 2. Update the inventory table
        cur.execute('''
            UPDATE inventory 
            SET current_stock = current_stock + %s 
            WHERE sku = %s
        ''', (stock_modifier, sku))
        
        # 3. Log the movement
        cur.execute('''
            INSERT INTO stock_movements (sku, user_id, quantity_changed, movement_type)
            VALUES (%s, %s, %s, %s)
        ''', (sku, user_id, quantity, movement_type))
        
        # Commit the transaction (both update and insert succeed together)
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"message": f"Successfully processed {movement_type} for {sku}."}), 201
        
    except Exception as e:
        # If anything fails, the connection closes without committing, acting as a rollback
        return jsonify({"error": str(e)}), 500

@app.route('/api/movements', methods=['GET'])
def get_movements():
    """Fetches a complete history of stock movements for the frontend UI."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # JOIN with inventory and users to give the frontend readable names
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
        
        cur.close()
        conn.close()
        
        return jsonify(movements), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
