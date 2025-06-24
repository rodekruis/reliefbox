from flask import Blueprint, render_template
from flask_login import login_required, login_required, current_user
from flask import (
    Flask,
    render_template,
    Response,
    jsonify,
    request,
    send_file,
    session,
    url_for,
    redirect,
)
from utils import (
    get_beneficiary_entry,
    get_beneficiary_data,
    save_beneficiary_data,
    save_single_beneficiary,
    delete_beneficiary_data,
    pandas_to_html,
    update_beneficiary_entry,
    get_cosmos_db,
)
import os
import pandas as pd
from datetime import datetime
import logging
import base64
from functools import wraps

cosmos_db = get_cosmos_db()
main = Blueprint("main", __name__)


def basic_auth_required(f):
    """Decorator that supports both Flask-Login and HTTP Basic Authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is already logged in via Flask-Login
        if current_user.is_authenticated:
            return f(*args, **kwargs)
        
        # Try Basic Authentication
        auth = request.authorization
        if auth:
            # Import here to avoid circular imports
            from app import User
            
            try:
                # Find user by email (username in basic auth)
                user = User.query.filter_by(email=auth.username).first()
                
                if user and user.password.strip() == auth.password:
                    logging.info(f"Basic auth successful for user: {auth.username}")
                    # For API endpoints, we'll store user info in g for the request
                    from flask import g
                    g.current_user = user
                    return f(*args, **kwargs)
                else:
                    logging.warning(f"Basic auth failed for user: {auth.username}")
            except Exception as e:
                logging.error(f"Error during basic authentication: {str(e)}")
        
        # No valid authentication found
        response = jsonify({
            "error": "Authentication required",
            "message": "Please provide valid credentials via login session or HTTP Basic Authentication",
            "status_code": 401
        })
        response.status_code = 401
        response.headers['WWW-Authenticate'] = 'Basic realm="ReliefBox API"'
        return response
    
    return decorated_function

def cleankobodata(data: dict) -> dict:
    keys = list(data.keys())

    try:
        start_index = keys.index("end") + 1
        end_index = keys.index("__version__")
    except ValueError:
        return {}  # Return empty if "end" or "__version__" not found

    trimmed_keys = keys[start_index:end_index]
    cleaned = {}

    for key in trimmed_keys:
        short_key = key.split("/")[-1]
        cleaned[short_key] = data[key]

    return cleaned

def get_current_user():
    """Get the current user from either Flask-Login or Basic Auth."""
    if current_user.is_authenticated:
        return current_user
    
    # Check if user was set via basic auth
    from flask import g
    if hasattr(g, 'current_user'):
        return g.current_user
    
    return None


@main.route("/choose_input_method", methods=["GET", "POST"])
@login_required
def choose_input_method():
    return render_template("choose_input_method.html")


@main.route("/save_input_method", methods=["POST"])
@login_required
def save_input_method():
    if "input_method" in request.form.keys():
        session["input_method"] = request.form["input_method"]
        if session["input_method"] == "text":
            return render_template("input.html")
        elif session["input_method"] == "video":
            return render_template("input_video.html")
    else:
        return render_template("choose_input_method.html")


@main.route("/input", methods=["GET"])
@login_required
def get_input():
    if "input_method" in session.keys():
        if session["input_method"] == "text":
            return render_template("input.html")
        elif session["input_method"] == "video":
            return render_template("input_video.html")
    else:
        return render_template("choose_input_method.html")


@main.route("/entry", methods=["POST", "GET"])
@login_required
def beneficiary():
    """Get beneficiary data."""
    if "distrib_id" not in session.keys():
        return render_template("index_distrib.html")

    if "code" in request.form.keys():
        if request.form["code"].strip() == "":
            return render_template("input.html")
        else:
            code = str(request.form["code"])
    elif "code" in request.args.keys():
        if request.args["code"].strip() == "":
            return render_template("input.html")
        else:
            code = str(request.args["code"])
    else:
        return render_template("input.html")

    beneficiary_data = get_beneficiary_entry(
        beneficiary_id=str(session["distrib_id"]) + str(code),
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
    )
    if beneficiary_data == "not_found":
        return render_template("entry_not_found.html")
    elif beneficiary_data == "no_data":
        return render_template("no_data.html")
    else:
        for internal_field in ["id", "distrib_id", "partitionKey"]:
            if internal_field in beneficiary_data.keys():
                beneficiary_data.pop(internal_field)
        return render_template("entry.html", data=beneficiary_data)


@main.route("/received", methods=["POST"])
@login_required
def received():
    if "code" in request.form.keys():
        replace_body = {
            "recipient": "Yes",
            "received_when": datetime.now().strftime("%m/%d/%Y, %H:%M:%S"),
        }
        result = update_beneficiary_entry(
            beneficiary_id=str(session["distrib_id"]) + str(request.form["code"]),
            user_email=current_user.email,
            distrib_id=session["distrib_id"],
            replace_body=replace_body,
        )
        if result == "not_found":
            return render_template("entry_not_found.html")
        elif result == "no_data":
            return render_template("no_data.html")
        else:
            return get_input()


def process_data(partition_key):
    raw_data_path = "data/data_raw.xlsx"
    try:
        df = pd.read_excel(raw_data_path)
        df.columns = df.columns.str.lower()
        df["code"] = df["code"].astype(str)
        if df["code"].duplicated().any():  # flag duplicated codes
            return "duplicates"  # TBI
        df = df.drop(
            [col for col in df.columns if col.startswith("_")], axis=1
        )  # drop KoBo columns
        if "recipient" not in df.columns:
            df["recipient"] = "No"
        if "received_when" not in df.columns:
            df["received_when"] = None

        # drop KoBo internal fields
        df = df[[col for col in df.columns if not col.startswith("_")]]

        save_beneficiary_data(
            data=df, distrib_id=session["distrib_id"], user_email=partition_key
        )
        os.remove(raw_data_path)
        return df
    except Exception as e:
        logging.exception(e)
        return "error"


@main.route("/upload_data", methods=["GET"])
@login_required
def upload_data():
    return render_template("upload_data.html")


@main.route("/uploader", methods=["POST"])
@login_required
def uploader():
    f = request.files["file"]
    f.save("data/data_raw.xlsx")
    # empty existing database
    delete_beneficiary_data(
        user_email=current_user.email, distrib_id=session["distrib_id"]
    )
    # then upload the new one
    df = process_data(partition_key=current_user.email)
    if type(df) == str:
        if df == "duplicates":
            return render_template("duplicate_error.html")
        elif df == "error":
            return render_template("upload_error.html")
    columns, rows = pandas_to_html(
        df,
        replace_values={"received_when": {"None": ""}},
        replace_columns={"received_when": "received when"},
        titlecase=True,
    )
    return render_template("view_data.html", columns=columns, rows=rows)


@main.route("/view_data", methods=["POST"])
@login_required
def view_data():
    data = get_beneficiary_data(
        user_email=current_user.email, distrib_id=session["distrib_id"]
    )
    if data is None:
        return render_template("no_data.html")
    else:
        columns, rows = pandas_to_html(
            data,
            replace_values={"received_when": {"None": ""}},
            replace_columns={"received_when": "received when"},
            titlecase=True,
        )
        return render_template("view_data.html", columns=columns, rows=rows)


@main.route("/missing", methods=["POST"])
@login_required
def missing():
    data = get_beneficiary_data(
        user_email=current_user.email, distrib_id=session["distrib_id"]
    )
    if data is None:
        return render_template("no_data.html")
    else:
        data = data[data["recipient"] == "No"]
        columns, rows = pandas_to_html(
            data,
            replace_values={"received_when": {"None": ""}},
            replace_columns={"received_when": "received when"},
            titlecase=True,
        )
        return render_template("view_data.html", columns=columns, rows=rows)


@main.route("/download_data", methods=["POST"])
@login_required
def download_data():
    data = get_beneficiary_data(
        user_email=current_user.email, distrib_id=session["distrib_id"]
    )
    if data is None:
        return render_template("no_data.html")
    else:
        data_path = "data/data_processed.xlsx"
        data.to_excel(data_path, index=False)
        writer = pd.ExcelWriter(data_path, engine="xlsxwriter")
        data.to_excel(writer, sheet_name="DATA", index=False)  # send df to writer
        worksheet = writer.sheets["DATA"]  # pull worksheet object
        for idx, col in enumerate(data.columns):  # loop through all columns
            series = data[col]
            max_len = (
                max(
                    (
                        series.astype(str).map(len).max(),  # len of largest item
                        len(str(series.name)),  # len of column name/header
                    )
                )
                + 1
            )
            worksheet.set_column(idx, idx, max_len)  # set column width
        writer._save()
        return send_file(data_path, as_attachment=True)


@main.route("/download_template", methods=["POST"])
@login_required
def download_template():
    return send_file("data/data_template.xlsx", as_attachment=True)


@main.route("/")
@login_required
def index():
    if "distrib_name" not in session.keys() or "distrib_place" not in session.keys():
        return render_template("index_distrib.html", email=current_user.email)
    else:
        return redirect(url_for("main.index_with_distrib", distrib_id=session["distrib_id"]))

@main.route("/distribution/<int:distrib_id>")
@login_required
def index_with_distrib(distrib_id):
    # Verify user has access to this distribution
    from app import Distribution
    distribution = Distribution.query.filter_by(
        id=distrib_id, user_email=current_user.email
    ).first()
    
    if not distribution:
        return render_template("index_distrib.html", email=current_user.email)
    
    # Update session with current distribution
    session["distrib_id"] = distrib_id
    session["distrib_name"] = distribution.name
    session["distrib_place"] = distribution.place
    session["distrib_date"] = distribution.date
    
    data = get_beneficiary_data(
        user_email=current_user.email, distrib_id=distrib_id
    )
    number_beneficiaries, number_recipients = 0, 0
    if data is not None:
        number_beneficiaries = len(data)
    if number_beneficiaries > 0 and "recipient" in data.columns:
        number_recipients = len(data[data["recipient"] == "Yes"])
    return render_template(
        "index.html",
        distrib_name=str(distribution.name),
        distrib_place=str(distribution.place),
        distrib_date=str(distribution.date),
        distrib_id=distrib_id,
        number_beneficiaries=number_beneficiaries,
        number_recipients=number_recipients,
    )


@main.route("/profile")
def profile():
    return render_template("profile.html", name=current_user.name)


@main.route("/add_beneficiary", methods=["POST"])
@basic_auth_required
def add_beneficiary():
    """Add a single beneficiary record via JSON POST request with comprehensive error handling."""
    try:
        # Get the current user (from Flask-Login or Basic Auth)
        user = get_current_user()
        if not user:
            logging.error("No authenticated user found")
            return jsonify({
                "error": "Authentication error",
                "message": "Unable to identify authenticated user",
                "status_code": 401
            }), 401

        logging.info(f"Received request to add beneficiary from user: {user.email}")

        # Get JSON data from request first
        data = request.get_json()
        logging.debug(f"Request JSON data: {data}")
        data = cleankobodata(data)
        
        # Validate JSON payload exists
        if not data:
            logging.error("No JSON data provided in request")
            return jsonify({
                "error": "No JSON data provided",
                "message": "Request must contain valid JSON data",
                "status_code": 400
            }), 400

        # Validate required fields with detailed error messages
        if "code" not in data or not data["code"]:
            logging.error("Missing or empty required field: code")
            return jsonify({
                "error": "Field 'code' is required",
                "message": "Beneficiary code must be provided and cannot be empty",
                "status_code": 400
            }), 400
        
        if "distrib_id" not in data or not data["distrib_id"]:
            logging.error("Missing or empty required field: distrib_id")
            return jsonify({
                "error": "Field 'distrib_id' is required",
                "message": "Distribution ID must be provided and cannot be empty",
                "status_code": 400
            }), 400

        # Validate distrib_id is a valid integer
        try:
            distrib_id = int(data["distrib_id"])
            if distrib_id <= 0:
                raise ValueError("Distribution ID must be positive")
        except (ValueError, TypeError) as e:
            logging.error(f"Invalid distrib_id format: {data['distrib_id']}")
            return jsonify({
                "error": "Invalid distribution ID format",
                "message": "Distribution ID must be a positive integer",
                "status_code": 400
            }), 400

        # Validate code format (ensure it's not just whitespace)
        if not str(data["code"]).strip():
            logging.error("Beneficiary code is empty or whitespace only")
            return jsonify({
                "error": "Invalid beneficiary code",
                "message": "Beneficiary code cannot be empty or whitespace only",
                "status_code": 400
            }), 400

        # Verify user has access to this distribution
        try:
            from app import Distribution
            logging.info(f"Checking access for user {user.email} to distribution {distrib_id}")
            distribution = Distribution.query.filter_by(
                id=distrib_id, user_email=user.email
            ).first()
            
            if not distribution:
                logging.warning(f"Distribution {distrib_id} not found or access denied for user {user.email}")
                return jsonify({
                    "error": "Distribution not found or access denied",
                    "message": f"Distribution with ID {distrib_id} does not exist or you don't have permission to access it",
                    "status_code": 404
                }), 404
        except Exception as e:
            logging.error(f"Database error while checking distribution access: {str(e)}")
            return jsonify({
                "error": "Database error",
                "message": "Failed to verify distribution access",
                "status_code": 500
            }), 500

        # Check if beneficiary with this code already exists
        beneficiary_id = str(distrib_id) + str(data["code"]).strip()
        logging.info(f"Checking if beneficiary with id {beneficiary_id} already exists")
        
        try:
            existing_beneficiary = get_beneficiary_entry(
                beneficiary_id=beneficiary_id,
                user_email=user.email,
                distrib_id=distrib_id,
            )

            if existing_beneficiary not in ["not_found", "no_data"]:
                logging.warning(f"Beneficiary with code '{data['code']}' already exists in distribution {distrib_id}")
                return jsonify({
                    "error": "Beneficiary already exists",
                    "message": f"Beneficiary with code '{data['code']}' already exists in distribution '{distribution.name}'",
                    "status_code": 409,
                    "existing_beneficiary_id": beneficiary_id
                }), 409
        except Exception as e:
            logging.error(f"Error checking existing beneficiary: {str(e)}")
            return jsonify({
                "error": "Database error",
                "message": "Failed to check for existing beneficiary",
                "status_code": 500
            }), 500

        # Set default values for required fields
        data.setdefault("recipient", "No")
        data.setdefault("received_when", None)
        logging.debug(f"Beneficiary data to save: {data}")

        # Validate and clean the data
        cleaned_data = {}
        for key, value in data.items():
            if key not in ["id", "partitionKey"]:  # Skip internal fields
                cleaned_data[key] = str(value).strip() if value is not None else None

        # Save the new beneficiary using the single beneficiary function
        logging.info(f"Saving new beneficiary for distribution {distrib_id}")
        try:
            saved_id = save_single_beneficiary(
                beneficiary_data=cleaned_data,
                distrib_id=distrib_id, 
                user_email=user.email
            )
            
            if not saved_id:
                logging.error("Failed to save beneficiary - no ID returned")
                return jsonify({
                    "error": "Save operation failed",
                    "message": "Beneficiary could not be saved to database",
                    "status_code": 500
                }), 500
                
            logging.info(f"Beneficiary successfully saved with id {saved_id}")

        except Exception as e:
            logging.error(f"Error saving beneficiary: {str(e)}")
            return jsonify({
                "error": "Database save error",
                "message": "Failed to save beneficiary to database",
                "details": str(e),
                "status_code": 500
            }), 500

        # Success response - ensure 201 status
        success_response = {
            "success": True,
            "message": f"Beneficiary with code '{data['code']}' added successfully to distribution '{distribution.name}'",
            "beneficiary_id": saved_id,
            "distribution_id": distrib_id,
            "distribution_name": distribution.name,
            "authenticated_user": user.email,
            "authentication_method": "basic_auth" if hasattr(request, 'authorization') and request.authorization else "session",
            "status_code": 201
        }
        
        logging.info(f"Successfully created beneficiary {saved_id} for distribution {distrib_id} by user {user.email}")
        return jsonify(success_response), 201

    except Exception as e:
        logging.exception(f"Unexpected exception occurred while adding beneficiary: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred while processing your request",
            "details": str(e),
            "status_code": 500
        }), 500

# Distribution-specific routes with distrib_id in URL
@main.route("/distribution/<int:distrib_id>/beneficiaries", methods=["GET"])
@login_required
def view_beneficiaries(distrib_id):
    """View all beneficiaries for a specific distribution."""
    # Verify user has access to this distribution
    from app import Distribution
    distribution = Distribution.query.filter_by(
        id=distrib_id, user_email=current_user.email
    ).first()
    
    if not distribution:
        return jsonify({"error": "Distribution not found or access denied"}), 404
    
    data = get_beneficiary_data(
        user_email=current_user.email, distrib_id=distrib_id
    )
    
    if data is None:
        return jsonify({"beneficiaries": [], "count": 0}), 200
    
    # Convert to JSON-serializable format
    beneficiaries = data.to_dict('records')
    return jsonify({
        "beneficiaries": beneficiaries,
        "count": len(beneficiaries),
        "distribution": {
            "id": distrib_id,
            "name": distribution.name,
            "place": distribution.place,
            "date": str(distribution.date)
        }
    }), 200

@main.route("/distribution/<int:distrib_id>/beneficiaries/<code>", methods=["GET"])
@login_required
def get_beneficiary(distrib_id, code):
    """Get a specific beneficiary by code for a distribution."""
    # Verify user has access to this distribution
    from app import Distribution
    distribution = Distribution.query.filter_by(
        id=distrib_id, user_email=current_user.email
    ).first()
    
    if not distribution:
        return jsonify({"error": "Distribution not found or access denied"}), 404
    
    beneficiary_id = str(distrib_id) + str(code)
    beneficiary_data = get_beneficiary_entry(
        beneficiary_id=beneficiary_id,
        user_email=current_user.email,
        distrib_id=distrib_id,
    )
    
    if beneficiary_data == "not_found":
        return jsonify({"error": "Beneficiary not found"}), 404
    elif beneficiary_data == "no_data":
        return jsonify({"error": "No data available"}), 404
    else:
        # Remove internal fields
        for internal_field in ["id", "distrib_id", "partitionKey"]:
            if internal_field in beneficiary_data:
                beneficiary_data.pop(internal_field)
        
        return jsonify({
            "beneficiary": beneficiary_data,
            "distribution_id": distrib_id
        }), 200

@main.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify API is working."""
    return jsonify({
        "status": "healthy",
        "message": "API is running",
        "timestamp": datetime.now().isoformat(),
        "status_code": 200
    }), 200

@main.route("/api/test-status-codes", methods=["GET"])
def test_status_codes():
    """Test endpoint to verify different status codes are working."""
    test_type = request.args.get('type', 'success')
    
    if test_type == 'success':
        return jsonify({"message": "Success test", "status_code": 200}), 200
    elif test_type == 'created':
        return jsonify({"message": "Created test", "status_code": 201}), 201
    elif test_type == 'bad_request':
        return jsonify({"error": "Bad request test", "status_code": 400}), 400
    elif test_type == 'not_found':
        return jsonify({"error": "Not found test", "status_code": 404}), 404
    elif test_type == 'conflict':
        return jsonify({"error": "Conflict test", "status_code": 409}), 409
    elif test_type == 'server_error':
        return jsonify({"error": "Server error test", "status_code": 500}), 500
    else:
        return jsonify({"error": "Invalid test type", "status_code": 400}), 400
