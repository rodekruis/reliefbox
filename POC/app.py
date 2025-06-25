from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import PendingRollbackError
import os
from datetime import timedelta, datetime
from urllib import parse
import secrets
import pandas as pd
from utils import delete_beneficiary_data, pandas_to_html
from dotenv import load_dotenv
import re

load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)

app = Flask(__name__)

server = "510-emergencies.database.windows.net"
database = "relief-app-users"
username = os.getenv("SQL_USERNAME")
password = os.getenv("SQL_PASSWORD")
driver = "{ODBC Driver 17 for SQL Server}"
odbc_str = (
    "DRIVER="
    + driver
    + ";SERVER="
    + server
    + ";PORT=1433;UID="
    + username
    + ";DATABASE="
    + database
    + ";PWD="
    + password
)
app.config["SECRET_KEY"] = secrets.token_urlsafe(16)
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "mssql+pyodbc:///?odbc_connect=" + parse.quote_plus(odbc_str)
)
app.config["SQLALCHEMY_COMMIT_ON_TEARDOWN"] = True
db = SQLAlchemy(app)


class User(UserMixin, db.Model):
    id = db.Column(
        db.Integer, primary_key=True
    )  # primary keys are required by SQLAlchemy
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))


class Distribution(db.Model):
    __table_args__ = {"extend_existing": True}
    id = db.Column(
        db.Integer, primary_key=True
    )  # primary keys are required by SQLAlchemy
    user_email = db.Column(db.String(100))
    name = db.Column(db.String(100))
    place = db.Column(db.String(100))
    date = db.Column(db.Date)
    items = db.Column(db.String(100))
    donor = db.Column(db.String(100))


login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


@login_manager.unauthorized_handler
def unauthorized_handler():
    return render_template("login.html")


def check_login(email):
    for try_ in range(100):
        try:
            user = User.query.filter_by(email=email).first()
            return user
        except PendingRollbackError:
            db.session.rollback()


@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    # login code goes here
    email = request.form.get("email")
    password = request.form.get("password")

    # check if connection still active
    user = check_login(email=email)

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or user.password.strip() != password:
        flash("Please check your login details and try again.")
        return redirect(
            url_for("login")
        )  # if the user doesn't exist or password is wrong, reload the page

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=False, duration=timedelta(days=1))

    return render_template(
        "index_distrib.html", email=current_user.email
    )  # url_for('main.index'))


@app.route("/signup", methods=["GET"])
def signup():
    return render_template("signup.html")


@app.route("/signup", methods=["POST"])
def signup_post():

    # code to validate and add user to database goes here
    email = request.form.get("email")
    name = request.form.get("name")
    password = request.form.get("password")

    if email == "" or name == "" or password == "":
        flash("Insert your email, name and password")
        return redirect(url_for("signup"))
    if (
        len(password) < 8
        or not any(not c.isalnum() for c in password)
        or not any(c.isupper() for c in password)
    ):
        flash(
            "Password must be at least 8 characters long and contain at least one special character and one uppercase letter"
        )
        return redirect(url_for("signup"))
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        flash("Use a valid email address")
        return redirect(url_for("signup"))

    user = check_login(email=email)

    if (
        user
    ):  # if a user is found, we want to redirect back to signup page so user can try again
        flash("This email address is already associated with a ReliefBox account")
        return redirect(url_for("signup"))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = User(email=email, name=name, password=password)

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    return redirect(url_for("login"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


@app.route("/index_distrib")
@login_required
def index_distrib():
    return render_template("index_distrib.html", email=current_user.email)


@app.route("/name_distrib", methods=["GET"])
@login_required
def name_distrib():
    return render_template("name_distrib.html")


@app.route("/create_distrib", methods=["POST"])
@login_required
def create_distrib():
    if "distrib_name" in request.form.keys():

        if (
            request.form["distrib_name"] == ""
            or request.form["distrib_place"] == ""
            or request.form["distrib_date"] == ""
        ):
            flash("Specify name, location and date of the distribution.")
            return redirect(url_for("name_distrib"))
        if (
            datetime.strptime(request.form["distrib_date"], "%Y-%m-%d").date()
            < datetime.now().date()
        ):
            flash("Date of the distribution cannot be in the past.")
            return redirect(url_for("name_distrib"))

        # create distrib
        distrib = Distribution.query.filter_by(
            user_email=current_user.email, name=request.form["distrib_name"]
        ).first()  # if this returns a distribution, then the name already exists in database

        if distrib:  # if a distribution is found, redirect back to name_distrib
            flash(f"Distribution {request.form['distrib_name']} already exists")
            return redirect(url_for("name_distrib"))

        # create a new distribution
        new_distrib = Distribution(
            user_email=current_user.email,
            name=request.form["distrib_name"],
            place=request.form["distrib_place"],
            date=datetime.strptime(request.form["distrib_date"], "%Y-%m-%d").date(),
            items=request.form["distrib_items"],
            donor=request.form["distrib_donor"],
        )

        # add the new distribution to the database
        db.session.add(new_distrib)
        db.session.commit()

        db.session.flush()

        session["distrib_id"] = new_distrib.id
        for feature in ["name", "place", "date", "items", "donor"]:
            session[f"distrib_{feature}"] = request.form[f"distrib_{feature}"]
        return redirect(url_for("main.index_with_distrib", distrib_id=new_distrib.id))
    else:
        return render_template("name_distrib.html")


def get_list_distrib():
    distributions = Distribution.query.filter_by(user_email=current_user.email)
    distrib_list = pd.DataFrame()
    for distrib_ in distributions:
        distrib_features = {}
        distrib_features["Name"] = distrib_.name
        distrib_features["Location"] = distrib_.place
        distrib_features["Date"] = distrib_.date
        distrib_features["Items distributed"] = distrib_.items
        distrib_features["Donor"] = distrib_.donor
        distrib_features["Distribution ID"] = distrib_.id
        df_dictionary = pd.DataFrame([distrib_features])
        distrib_list = pd.concat([distrib_list, df_dictionary], ignore_index=True)
    return distrib_list


@app.route("/list_distrib", methods=["GET"])
@login_required
def list_distrib():
    distrib_list = get_list_distrib()
    if len(distrib_list) == 0:
        return render_template("no_distrib.html")
    else:
        columns, rows = pandas_to_html(distrib_list, titlecase=True)
        return render_template("list_distrib.html", columns=columns, rows=rows)


@app.route("/select_distrib", methods=["POST"])
@login_required
def select_distrib():
    if "distrib_id" in request.form.keys():
        distrib_ = Distribution.query.filter_by(
            user_email=current_user.email, id=int(float(request.form["distrib_id"]))
        ).first()
        session[f"distrib_id"] = distrib_.id
        session[f"distrib_name"] = distrib_.name
        session[f"distrib_place"] = distrib_.place
        session[f"distrib_date"] = distrib_.date
        session[f"distrib_items"] = distrib_.items
        session[f"distrib_donor"] = distrib_.donor
        return redirect(url_for("main.index_with_distrib", distrib_id=distrib_.id))
    else:
        return render_template("list_distrib.html")


@app.route("/list_distrib_delete", methods=["GET"])
@login_required
def list_distrib_delete():
    distrib_list = get_list_distrib()
    if len(distrib_list) == 0:
        return render_template("no_distrib.html")
    else:
        columns, rows = pandas_to_html(distrib_list, titlecase=True)
        return render_template("list_distrib_delete.html", columns=columns, rows=rows)


@app.route("/delete_distrib_confirm", methods=["POST"])
@login_required
def delete_distrib_confirm():
    if "distrib_id" in request.form.keys():
        session["distrib_id"] = int(float(request.form["distrib_id"]))
        return render_template(
            "delete_distrib_confirm.html", distrib_id=session["distrib_id"]
        )
    else:
        return render_template("list_distrib_delete.html")


@app.route("/delete_distrib", methods=["POST"])
@login_required
def delete_distrib():
    if "distrib_id" in request.form.keys():
        session["distrib_id"] = int(float(request.form["distrib_id"]))
        # delete beneficiaries
        delete_beneficiary_data(
            user_email=current_user.email, distrib_id=session["distrib_id"]
        )
        # delete distribution
        distrib_to_delete = Distribution.query.filter_by(
            id=session["distrib_id"]
        ).first()
        db.session.delete(distrib_to_delete)
        db.session.commit()
        return render_template("index_distrib.html", email=current_user.email)
    else:
        return render_template("list_distrib_delete.html")


from main import main as main_blueprint

app.register_blueprint(main_blueprint)

if __name__ == "__main__":
    app.run()
