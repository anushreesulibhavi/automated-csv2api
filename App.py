from flask import Flask, request, jsonify, session, render_template,send_from_directory,Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename
#from models import FileRecord  # Import your model
import time
import pandas as pd
import os
import re
import numpy as np
from flask_cors import CORS

#app = Flask(__name__, static_folder="../frontend/build", static_url_path="/")
app = Flask(__name__, static_folder='static')
app.secret_key = "supersecretpassword"  
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
        return jsonify({"message": "Login successful!!"}), 200
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
    
    if not file.filename.lower().endswith('.csv'):
        print("Uploaded file is not a CSV")
        return jsonify({"error": "File must be a CSV"}), 400

    filename = secure_filename(file.filename)
    table_name = filename.split(".")[0].replace(" ", "_").replace("-", "_").lower()

    # Check if the table already exists in the database
    existing_record = FileRecord.query.filter_by(table_name=table_name).first()
    if existing_record:
        return jsonify({
            "success": False,
            "message": f'File already exists. You can fetch data using the API: "{table_name}"'
        }), 400
    
    # Save file
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        # Load CSV into Pandas
        df = pd.read_csv(filepath)
        df.fillna(value=np.nan, inplace=True)  # Ensure missing values are NaN

        # Create SQL table dynamically
        with app.app_context():
            db.session.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
            df.to_sql(table_name, db.engine, index=False, if_exists="replace")

            # Save file metadata
            file_record = FileRecord(filename=filename, table_name=table_name)
            db.session.add(file_record)
            db.session.commit()
        print(f"Generated API Name: {table_name}")  # Debugging purpose
        return jsonify({"message": f'File uploaded successfully 🎉 \n API created at /api/{table_name}\n api_name: {table_name}'}), 201
    except Exception as e:
        print(f"Error processing file: {str(e)}")  # Log the error
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500



@app.route("/api/generate/<table_name>", methods=["POST"])
def generate_api(table_name):
    # This endpoint can be used to confirm API generation
    with app.app_context():
        inspector = inspect(db.engine)

        if table_name not in inspector.get_table_names():
            return jsonify({"error": "Table not found"}), 404
        
    return jsonify({"message": f"API generated at /api/{table_name}","api_name":{table_name}}), 200
   

@app.route("/api/<table_name>/search", methods=["GET"])
def search_data(table_name):
    param = request.args.get("param")
    value = request.args.get("value")

    with app.app_context():
        try:
            inspector = inspect(db.engine)
            if table_name not in inspector.get_table_names():
                return jsonify({"error": "Table not found"}), 404
            
            table_name = re.sub(r'[^a-z0-9_]+', '', table_name.lower())

            # Fetch data from the database
            query = text(f'SELECT * FROM "{table_name}"')
            result = db.session.execute(query, {"value": value}).fetchall()

            # Convert result to a list of dicts
            columns = [col for col in result[0]._fields]
            data = [dict(zip(columns, row)) for row in result]

            
            if not data:
                return jsonify({"error": "No data found"}), 404
            
            # Get the current index based on the current time
            current_index = int(time.time()) % len(data)

            # Get the row at the current index
            row = data[current_index]
            timestamp = row.get('Timestamp', f"2023-10-01 12:00:0{current_index}")
            if param in row:
                value = row[param]
                result_string = f"value for {param} at {timestamp}: {value}"
                return Response(result_string, mimetype="text/plain"), 200

            return Response("Parameter not found in data"), 404

        except Exception as e:
            return Response(str(e)), 500
            
        
@app.route("/api/<table_name>/parameters", methods=["GET"])
def get_parameters(table_name):
    # Clean the table name to prevent SQL injection
    table_name = re.sub(r'[^a-z0-9_]+', '', table_name.lower())

    with app.app_context():
        try:
            inspector = inspect(db.engine)
            if table_name not in inspector.get_table_names():
                return jsonify({"error": "Table not found"}), 404
            
            # Fetch the column names from the specified table
            result = db.session.execute(text(f'SELECT * FROM "{table_name}" LIMIT 1')).keys()
            parameters = list(result)  # Get the column names as parameters

            return jsonify({"parameters": parameters}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/tables", methods=["GET"])
def list_tables():
    with app.app_context():
        try:
            # Get all file records
            records = FileRecord.query.all()
            tables = [{
                "filename": record.filename,
                "table_name": record.table_name,
                "api_endpoint": f"/api/{record.table_name}"
            } for record in records]
            
            return jsonify({
                "count": len(tables),
                "tables": tables
            })
        except Exception as e:
            return jsonify({
                "error": "Database error",
                "message": str(e)
            }), 500



if __name__ == "__main__":
    app.run(debug=True)


