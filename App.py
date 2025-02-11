from flask import Flask, request, jsonify, session, render_template
from flask import send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
#from models import FileRecord  # Import your model
import pandas as pd
import os
import numpy as np
from flask_cors import CORS

#app = Flask(__name__, static_folder="../frontend/build", static_url_path="/")
app = Flask(__name__, static_folder='static')
app.secret_key = "supersecretpassword"  # Change this in production
CORS(app)

# Configure SQLite database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_PASSWORD = "admin123"

# Model to store uploaded file information
class FileRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=False, nullable=False)
    table_name = db.Column(db.String(100), unique=False, nullable=False)

# Initialize the database
with app.app_context():
    db.create_all()

@app.route("/")
def home():
    return render_template("index.html")

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"message": "Unauthorized"}), 401

@app.route("/upload", methods=["POST"])
def upload_csv():
    if "admin" not in session:
        return jsonify({"message": "Unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = file.filename
    table_name = filename.split(".")[0].replace(" ", "_").lower()

    # Save file
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # Load CSV into Pandas
    df = pd.read_csv(filepath, on_bad_lines='warn')
    df.fillna(value=np.nan, inplace=True)  # Ensure missing values are NaN

    # Create SQL table dynamically
    with app.app_context():
        db.session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        df.to_sql(table_name, db.engine, index=False)

        # Save file metadata
        file_record = FileRecord(filename=filename, table_name=table_name)
        db.session.add(file_record)
        db.session.commit()

    return jsonify({"message": f"API created at /api/{table_name}"}), 201

@app.route("/api/<table_name>", methods=["GET"])
def get_data(table_name):
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            print("Available tables:", inspector.get_table_names())  # Debugging

            result = db.session.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            if not result:
                return jsonify({"error": "No data found"}), 404

            # Convert result to a list of dicts
            columns = [col for col in result[0]._fields]
            data = [dict(zip(columns, row)) for row in result]
            return jsonify(data)
        except Exception as e:
            print("Error:", str(e))  # Debugging
            return jsonify({"error": "API not found or invalid table"}), 404

if __name__ == "__main__":
    app.run(debug=True)
