from flask import Flask, jsonify

# This is the "app" variable Vercel is looking for!
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "StockPal MVP Backend is Live!"
    })

if __name__ == '__main__':
    app.run(debug=True)
