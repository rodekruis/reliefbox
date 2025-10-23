from flask import Blueprint, render_template, Response, jsonify, request, send_file, session, url_for, redirect, g, flash, abort
import base64
from flask_login import login_required, current_user
from .extensions import db
from .models import Distribution, User
from .utils import (
    get_beneficiary_entry,
    get_beneficiary_data,
    save_beneficiary_data,
    save_single_beneficiary,
    delete_beneficiary_data,
    delete_single_beneficiary,
    pandas_to_html,
    update_beneficiary_entry,
    get_cosmos_db,
)
import os
import pandas as pd
from datetime import datetime
import logging
from functools import wraps
from html import escape

cosmos_db = get_cosmos_db()
main = Blueprint("main", __name__)


def basic_auth_required(f):
    """Decorator that supports both Flask-Login and HTTP Basic Authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            return f(*args, **kwargs)
        
        auth = request.authorization
        if auth:
            try:
                user = User.query.filter_by(email=auth.username).first()
                if user and user.password.strip() == auth.password:
                    g.current_user = user
                    return f(*args, **kwargs)
            except Exception as e:
                logging.error(f"Error during basic authentication: {str(e)}")
        
        response = jsonify({"error": "Authentication required", "message": "Please provide valid credentials.", "status_code": 401})
        response.status_code = 401
        response.headers['WWW-Authenticate'] = 'Basic realm="ReliefBox API"'
        return response
    
    return decorated_function

def cleankobodata(data: dict) -> dict:
    try:
        keys = list(data.keys())
        start_index = keys.index("formhub/uuid") + 1
        end_index = keys.index("__version__")
        trimmed_keys = keys[start_index:end_index]
        return {key.split("/")[-1].lower(): data[key] for key in trimmed_keys}
    except ValueError:
        return {}

def get_current_user_from_context():
    """Get the current user from either Flask-Login or Basic Auth."""
    if current_user.is_authenticated:
        return current_user
    return getattr(g, 'current_user', None)


@main.route("/choose_input_method", methods=["GET"])
@login_required
def choose_input_method():
    return render_template("choose_input_method.html")


@main.route("/save_input_method", methods=["POST"])
@login_required
def save_input_method():
    session["input_method"] = request.form.get("input_method", "text")
    if session["input_method"] == "video":
        return render_template("input_video.html")
    elif session["input_method"] == "search":
        return redirect(url_for("main.search"))
    return render_template("input.html")


@main.route("/input", methods=["GET"])
@login_required
def get_input():
    if session.get("input_method") == "video":
        return render_template("input_video.html")
    elif session.get("input_method") == "search":
        return redirect(url_for("main.search"))
    return render_template("input.html")


@main.route("/entry", methods=["POST", "GET"])
@login_required
def beneficiary():
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))

    code = request.form.get("code") or request.args.get("code")
    if not code or not code.strip():
        return render_template("input.html")

    beneficiary_data = get_beneficiary_entry(
        beneficiary_id=f"{session['distrib_id']}{code.strip()}",
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
    )
    if beneficiary_data in ["not_found", "no_data"]:
        return render_template(f"{beneficiary_data}.html")
    
    # Remove internal fields before rendering
    beneficiary_data.pop("id", None)
    beneficiary_data.pop("distrib_id", None)
    beneficiary_data.pop("partitionKey", None)
    return render_template("entry.html", data=beneficiary_data)


@main.route("/received", methods=["POST"])
@login_required
def received():
    code = request.form.get("code")
    if not code:
        return redirect(url_for("main.get_input"))

    notes = request.form.get("notes", "").strip()
    replace_body = {
        "recipient": "Yes",
        "received_when": datetime.now().strftime("%m/%d/%Y, %H:%M:%S"),
    }
    if notes and notes.lower() != "none":
        replace_body["notes"] = escape(notes[:255])

    result = update_beneficiary_entry(
        beneficiary_id=f"{session['distrib_id']}{code}",
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
        replace_body=replace_body,
    )
    if result in ["not_found", "no_data"]:
        return render_template(f"{result}.html")
    
    return redirect(url_for("main.get_input"))


@main.route("/collect_signature", methods=["POST"])
@login_required
def collect_signature():
    """Redirect to signature collection page before marking as received."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    code = request.form.get("code")
    if not code:
        return redirect(url_for("main.get_input"))
    
    notes = request.form.get("notes", "").strip()
    
    # Get beneficiary data to display on signature page
    beneficiary_data = get_beneficiary_entry(
        beneficiary_id=f"{session['distrib_id']}{code}",
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
    )
    
    if beneficiary_data in ["not_found", "no_data"]:
        return render_template(f"{beneficiary_data}.html")
    
    # Remove internal fields before rendering
    beneficiary_data.pop("id", None)
    beneficiary_data.pop("distrib_id", None)
    beneficiary_data.pop("partitionKey", None)
    
    return render_template("signature.html", 
                         data=beneficiary_data, 
                         notes=notes)


@main.route("/confirm_receipt_with_signature", methods=["POST"])
@login_required
def confirm_receipt_with_signature():
    """Process the final confirmation with signature data."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    code = request.form.get("code")
    signature_data = request.form.get("signature_data")
    notes = request.form.get("notes", "").strip()
    
    if not code or not signature_data:
        return redirect(url_for("main.get_input"))
    
    # Prepare the update body
    replace_body = {
        "recipient": "Yes",
        "received_when": datetime.now().strftime("%m/%d/%Y, %H:%M:%S"),
        "signature": signature_data,  # Store the signature as base64 data
    }
    
    if notes and notes.lower() != "none":
        replace_body["notes"] = escape(notes[:255])
    
    # Update the beneficiary record
    result = update_beneficiary_entry(
        beneficiary_id=f"{session['distrib_id']}{code}",
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
        replace_body=replace_body,
    )
    
    if result in ["not_found", "no_data"]:
        return render_template(f"{result}.html")
    
    return redirect(url_for("main.get_input"))


@main.route("/view_signature/<code>")
@login_required
def view_signature(code):
    """Display a signature for verification purposes."""
    
    # First try to use session distrib_id if available
    if "distrib_id" in session:
        beneficiary_data = get_beneficiary_entry(
            beneficiary_id=f"{session['distrib_id']}{code}",
            user_email=current_user.email,
            distrib_id=session["distrib_id"],
        )
        
        if beneficiary_data not in ["not_found", "no_data"]:
            signature_data = beneficiary_data.get("signature")
            if signature_data and signature_data.startswith('data:image'):
                received_when = beneficiary_data.get("received_when")
                return render_template("signature_view.html", 
                                     code=code, 
                                     signature_data=signature_data,
                                     received_when=received_when)
    
    # If no session or not found, search through all user's distributions
    from .models import Distribution
    distributions = Distribution.query.filter_by(user_email=current_user.email).all()
    
    for distribution in distributions:
        beneficiary_data = get_beneficiary_entry(
            beneficiary_id=f"{distribution.id}{code}",
            user_email=current_user.email,
            distrib_id=distribution.id,
        )
        
        if beneficiary_data not in ["not_found", "no_data"]:
            signature_data = beneficiary_data.get("signature")
            if signature_data and signature_data.startswith('data:image'):
                received_when = beneficiary_data.get("received_when")
                return render_template("signature_view.html", 
                                     code=code, 
                                     signature_data=signature_data,
                                     received_when=received_when,
                                     distribution_name=distribution.name)
    
    # No signature found in any distribution
    abort(404)


@main.route("/test_route")
def test_route():
    """Simple test route to verify blueprint is working."""
    return "Blueprint route is working!"


@main.route("/signature_image/<code>")
@login_required  
def signature_image(code):
    """Return raw signature image data for embedding or download."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    beneficiary_data = get_beneficiary_entry(
        beneficiary_id=f"{session['distrib_id']}{code}",
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
    )
    
    if beneficiary_data in ["not_found", "no_data"]:
        abort(404)
    
    signature_data = beneficiary_data.get("signature")
    if not signature_data or not signature_data.startswith('data:image/png;base64,'):
        abort(404)
    
    # Extract base64 data and return as PNG
    image_data = signature_data.split('data:image/png;base64,')[1]
    image_binary = base64.b64decode(image_data)
    return Response(image_binary, mimetype='image/png')


def process_data(partition_key, distrib_id):
    raw_data_path = "data/data_raw.xlsx"
    try:
        df = pd.read_excel(raw_data_path)
        df.columns = df.columns.str.lower()
        df["code"] = df["code"].astype(str)
        if df["code"].duplicated().any():
            return "duplicates"
        
        df = df.drop([col for col in df.columns if col.startswith("_")], axis=1)
        df.setdefault("recipient", "No")
        df.setdefault("received_when", None)
        df.setdefault("notes", None)

        save_beneficiary_data(data=df, distrib_id=distrib_id, user_email=partition_key)
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
    if 'file' not in request.files:
        return redirect(url_for("main.upload_data"))
    
    f = request.files["file"]
    f.save("data/data_raw.xlsx")
    
    delete_beneficiary_data(user_email=current_user.email, distrib_id=session["distrib_id"])
    
    df = process_data(partition_key=current_user.email, distrib_id=session["distrib_id"])
    if isinstance(df, str):
        if df == "duplicates":
            return render_template("duplicate_error.html")
        return render_template("upload_error.html")
        
    columns, rows = pandas_to_html(
        df,
        replace_values={"received_when": {"None": ""}, "notes": {"None": ""}},
        replace_columns={"received_when": "received when"},
        titlecase=True,
    )
    return render_template("view_data.html", columns=columns, rows=rows)


@main.route("/view_data", methods=["POST"])
@login_required
def view_data():
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=session["distrib_id"])
    if data is None:
        return render_template("no_data.html")
    
    columns, rows = pandas_to_html(
        data,
        replace_values={"received_when": {"None": ""}, "notes": {"None": ""}},
        replace_columns={"received_when": "received when"},
        titlecase=True,
    )
    return render_template("view_data.html", columns=columns, rows=rows)


@main.route("/missing", methods=["POST"])
@login_required
def missing():
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=session["distrib_id"])
    if data is None:
        return render_template("no_data.html")
    
    data = data[data["recipient"] == "No"]
    columns, rows = pandas_to_html(
        data,
        replace_values={"received_when": {"None": ""}, "notes": {"None": ""}},
        replace_columns={"received_when": "received when"},
        titlecase=True,
    )
    return render_template("view_data.html", columns=columns, rows=rows)


@main.route("/download_data", methods=["POST"])
@login_required
def download_data():
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=session["distrib_id"])
    if data is None:
        return render_template("no_data.html")
    
    data_path = "data/data_processed.xlsx"
    with pd.ExcelWriter(data_path, engine="xlsxwriter") as writer:
        data.to_excel(writer, sheet_name="DATA", index=False)
        worksheet = writer.sheets["DATA"]
        for idx, col in enumerate(data.columns):
            series = data[col]
            max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 1
            worksheet.set_column(idx, idx, max_len)
    return send_file(data_path, as_attachment=True)


@main.route("/search", methods=["GET"])
@login_required
def search():
    """Display the search form with available columns."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=session["distrib_id"])
    if data is None:
        return render_template("no_data.html")
    
    # Get available columns (exclude system columns)
    columns = [col for col in data.columns if col not in ['recipient', 'received_when', 'notes']]
    return render_template("search.html", columns=columns)


@main.route("/search_beneficiaries", methods=["POST"])
@login_required
def search_beneficiaries():
    """Handle the search request and return results."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    search_column = request.form.get("search_column")
    search_value = request.form.get("search_value")
    exact_match = request.form.get("exact_match") is not None
    
    if not search_column or not search_value:
        return redirect(url_for("main.search"))
    
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=session["distrib_id"])
    if data is None:
        return render_template("no_data.html")
    
    # Perform the search
    if exact_match:
        # Exact match search
        results_df = data[data[search_column].astype(str).str.lower() == search_value.lower()]
    else:
        # Partial match search (contains)
        results_df = data[data[search_column].astype(str).str.lower().str.contains(search_value.lower(), na=False)]
    
    # Convert results to list of dictionaries
    results = results_df.to_dict('records')
    
    # Get columns for display (exclude system columns from display)
    display_columns = [col for col in data.columns if col not in ['recipient', 'received_when', 'notes']]
    
    return render_template("search_results.html", results=results, columns=display_columns)


@main.route("/edit_beneficiary", methods=["GET"])
@login_required
def edit_beneficiary():
    """Display the edit form for a beneficiary."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    code = request.args.get("code")
    if not code:
        return redirect(url_for("main.get_input"))
    
    beneficiary_data = get_beneficiary_entry(
        beneficiary_id=f"{session['distrib_id']}{code}",
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
    )
    
    if beneficiary_data in ["not_found", "no_data"]:
        return render_template(f"{beneficiary_data}.html")
    
    # Remove internal fields before rendering
    beneficiary_data.pop("id", None)
    beneficiary_data.pop("distrib_id", None)
    beneficiary_data.pop("partitionKey", None)
    
    return render_template("edit_beneficiary.html", data=beneficiary_data)


@main.route("/update_beneficiary", methods=["POST"])
@login_required
def update_beneficiary():
    """Process the beneficiary update."""
    if "distrib_id" not in session:
        return redirect(url_for("main.index"))
    
    original_code = request.form.get("original_code")
    if not original_code:
        return redirect(url_for("main.get_input"))
    
    # Get the current beneficiary data
    original_beneficiary_id = f"{session['distrib_id']}{original_code}"
    current_data = get_beneficiary_entry(
        beneficiary_id=original_beneficiary_id,
        user_email=current_user.email,
        distrib_id=session["distrib_id"],
    )
    
    if current_data in ["not_found", "no_data"]:
        return render_template(f"{current_data}.html")
    
    # Prepare update data
    update_data = {}
    
    # Get all form fields
    for field_name in request.form:
        if field_name != "original_code" and field_name != "reset_distribution_status":
            value = request.form.get(field_name, "").strip()
            if value:  # Only update non-empty values
                update_data[field_name] = value
    
    # Handle distribution status reset
    if request.form.get("reset_distribution_status"):
        update_data["recipient"] = "No"
        update_data["received_when"] = None
        update_data["notes"] = request.form.get("notes", "").strip() or None
    
    # Handle code changes (this requires special handling)
    new_code = request.form.get("code", "").strip()
    if new_code and new_code != original_code:
        # We need to create a new entry and delete the old one
        # First check if the new code already exists
        new_beneficiary_id = f"{session['distrib_id']}{new_code}"
        existing_check = get_beneficiary_entry(
            beneficiary_id=new_beneficiary_id,
            user_email=current_user.email,
            distrib_id=session["distrib_id"],
        )
        
        if existing_check not in ["not_found", "no_data"]:
            # Code already exists, can't update
            flash(f"Error: Beneficiary code '{new_code}' already exists. Please use a different code.")
            return redirect(url_for("main.edit_beneficiary", code=original_code))
        
        # Create new entry with updated data
        new_data = current_data.copy()
        new_data.update(update_data)
        new_data["code"] = new_code
        new_data["id"] = new_beneficiary_id
        
        # Save the new entry
        save_single_beneficiary(
            beneficiary_data=new_data,
            user_email=current_user.email,
            distrib_id=session["distrib_id"]
        )
        
        # Delete the old entry
        delete_single_beneficiary(
            beneficiary_id=original_beneficiary_id,
            user_email=current_user.email,
            distrib_id=session["distrib_id"]
        )
        
        # Redirect to the new entry
        return redirect(url_for("main.beneficiary") + f"?code={new_code}")
    else:
        # Normal update (no code change)
        result = update_beneficiary_entry(
            beneficiary_id=original_beneficiary_id,
            user_email=current_user.email,
            distrib_id=session["distrib_id"],
            replace_body=update_data,
        )
        
        if result in ["not_found", "no_data"]:
            return render_template(f"{result}.html")
        
        # Redirect back to the entry view
        return redirect(url_for("main.beneficiary") + f"?code={original_code}")


@main.route("/download_template", methods=["POST"])
@login_required
def download_template():
    return send_file("data/data_template.xlsx", as_attachment=True)


@main.route("/")
@login_required
def index():
    if "distrib_id" not in session:
        return redirect(url_for("index_distrib"))
    return redirect(url_for("main.index_with_distrib", distrib_id=session["distrib_id"]))

@main.route("/distribution/<int:distrib_id>")
@login_required
def index_with_distrib(distrib_id):
    distribution = Distribution.query.filter_by(id=distrib_id, user_email=current_user.email).first()
    if not distribution:
        return redirect(url_for("index_distrib"))
    
    session["distrib_id"] = distrib_id
    session["distrib_name"] = distribution.name
    
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=distrib_id)
    number_beneficiaries = len(data) if data is not None else 0
    number_recipients = len(data[data["recipient"] == "Yes"]) if number_beneficiaries > 0 and "recipient" in data.columns else 0
    
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
@login_required
def profile():
    return render_template("profile.html", name=current_user.name)


@main.route("/add_beneficiary", methods=["POST"])
@basic_auth_required
def add_beneficiary():
    user = get_current_user_from_context()
    if not user:
        return jsonify({"error": "Authentication error", "message": "Unable to identify authenticated user", "status_code": 401}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided", "message": "Request must contain valid JSON data", "status_code": 400}), 400
    
    data = cleankobodata(data)
    code = data.get("code")
    distrib_id_str = data.get("distrib_id")

    if not code or not str(code).strip():
        return jsonify({"error": "Field 'code' is required", "message": "Beneficiary code must be provided and cannot be empty", "status_code": 400}), 400
    if not distrib_id_str:
        return jsonify({"error": "Field 'distrib_id' is required", "message": "Distribution ID must be provided", "status_code": 400}), 400

    try:
        distrib_id = int(distrib_id_str)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid distribution ID format", "message": "Distribution ID must be an integer", "status_code": 400}), 400

    distribution = Distribution.query.filter_by(id=distrib_id, user_email=user.email).first()
    if not distribution:
        return jsonify({"error": "Distribution not found or access denied", "message": f"Distribution with ID {distrib_id} not found or access denied.", "status_code": 404}), 404

    beneficiary_id = f"{distrib_id}{str(code).strip()}"
    existing_beneficiary = get_beneficiary_entry(beneficiary_id=beneficiary_id, user_email=user.email, distrib_id=distrib_id)
    if existing_beneficiary not in ["not_found", "no_data"]:
        return jsonify({"error": "Beneficiary already exists", "message": f"Beneficiary with code '{code}' already exists in this distribution.", "status_code": 409}), 409

    data.setdefault("recipient", "No")
    data.setdefault("received_when", None)
    data.setdefault("notes", None)
    
    cleaned_data = {k: str(v).strip() if v is not None else None for k, v in data.items() if k not in ["id", "partitionKey"]}

    try:
        saved_id = save_single_beneficiary(beneficiary_data=cleaned_data, distrib_id=distrib_id, user_email=user.email)
        if not saved_id:
            return jsonify({"error": "Save operation failed", "message": "Beneficiary could not be saved.", "status_code": 500}), 500
    except Exception as e:
        logging.error(f"Error saving beneficiary: {str(e)}")
        return jsonify({"error": "Database save error", "message": "Failed to save beneficiary to database.", "details": str(e), "status_code": 500}), 500

    return jsonify({
        "success": True,
        "message": f"Beneficiary with code '{code}' added successfully.",
        "beneficiary_id": saved_id,
        "distribution_id": distrib_id,
        "status_code": 201
    }), 201


@main.route("/distribution/<int:distrib_id>/beneficiaries", methods=["GET"])
@login_required
def view_beneficiaries(distrib_id):
    distribution = Distribution.query.filter_by(id=distrib_id, user_email=current_user.email).first()
    if not distribution:
        return jsonify({"error": "Distribution not found or access denied"}), 404
    
    data = get_beneficiary_data(user_email=current_user.email, distrib_id=distrib_id)
    if data is None:
        return jsonify({"beneficiaries": [], "count": 0}), 200
    
    return jsonify({
        "beneficiaries": data.to_dict('records'),
        "count": len(data),
        "distribution": {"id": distrib_id, "name": distribution.name}
    }), 200

@main.route("/distribution/<int:distrib_id>/beneficiaries/<code>", methods=["GET"])
@login_required
def get_beneficiary(distrib_id, code):
    distribution = Distribution.query.filter_by(id=distrib_id, user_email=current_user.email).first()
    if not distribution:
        return jsonify({"error": "Distribution not found or access denied"}), 404
    
    beneficiary_id = f"{distrib_id}{code}"
    beneficiary_data = get_beneficiary_entry(beneficiary_id=beneficiary_id, user_email=current_user.email, distrib_id=distrib_id)
    
    if beneficiary_data in ["not_found", "no_data"]:
        return jsonify({"error": f"Beneficiary with code '{code}' not found."}), 404
    
    beneficiary_data.pop("id", None)
    beneficiary_data.pop("distrib_id", None)
    beneficiary_data.pop("partitionKey", None)
    
    return jsonify({"beneficiary": beneficiary_data, "distribution_id": distrib_id}), 200

@main.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

