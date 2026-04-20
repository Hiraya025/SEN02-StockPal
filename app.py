import os
import psycopg2
from flask import Flask, jsonify, request
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
    return jsonify({"message": "StockPal API is running!"})

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

if __name__ == '__main__':
    app.run(debug=True)
