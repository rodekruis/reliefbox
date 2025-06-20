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

cosmos_db = get_cosmos_db()
main = Blueprint("main", __name__)


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
        data = get_beneficiary_data(
            user_email=current_user.email, distrib_id=session["distrib_id"]
        )
        number_beneficiaries, number_recipients = 0, 0
        if data is not None:
            number_beneficiaries = len(data)
        if number_beneficiaries > 0 and "recipient" in data.columns:
            number_recipients = len(data[data["recipient"] == "Yes"])
        return render_template(
            "index.html",
            distrib_name=str(session["distrib_name"]),
            distrib_place=str(session["distrib_place"]),
            distrib_date=str(session["distrib_date"]),
            number_beneficiaries=number_beneficiaries,
            number_recipients=number_recipients,
        )


@main.route("/profile")
def profile():
    return render_template("profile.html", name=current_user.name)


@main.route("/add_beneficiary", methods=["POST"])
@login_required
def add_beneficiary():
    """Add a single beneficiary record via JSON POST request."""
    try:
        # Check if distribution is selected
        if "distrib_id" not in session:
            return jsonify({"error": "No distribution selected"}), 400

        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        # Validate required fields
        if "code" not in data:
            return jsonify({"error": "Field 'code' is required"}), 400

        # Check if beneficiary with this code already exists
        beneficiary_id = str(session["distrib_id"]) + str(data["code"])
        existing_beneficiary = get_beneficiary_entry(
            beneficiary_id=beneficiary_id,
            user_email=current_user.email,
            distrib_id=session["distrib_id"],
        )

        if existing_beneficiary not in ["not_found", "no_data"]:
            return (
                jsonify(
                    {"error": f"Beneficiary with code '{data['code']}' already exists"}
                ),
                409,
            )

        # Set default values for required fields
        data.setdefault("recipient", "No")
        data.setdefault("received_when", None)

        # Save the new beneficiary using the single beneficiary function
        saved_id = save_single_beneficiary(
            beneficiary_data=data,
            distrib_id=session["distrib_id"], 
            user_email=current_user.email
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Beneficiary with code '{data['code']}' added successfully",
                    "beneficiary_id": saved_id,
                }
            ),
            201,
        )

    except Exception as e:
        logging.exception(e)
        return jsonify({"error": "Internal server error"}), 500
