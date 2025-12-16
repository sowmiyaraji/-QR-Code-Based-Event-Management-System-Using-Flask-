from flask import Flask, render_template, request, redirect, url_for, Response, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
import qrcode
import os
import csv

from config import Config
from extensions import db, login_manager
from models import User, Event, Registration


# =====================
# APP FACTORY
# =====================
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    with app.app_context():
        db.create_all()

    return app


app = create_app()


# =====================
# LOGIN MANAGER
# =====================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =====================
# AUTH ROUTES
# =====================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = User(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"]),
            role="user"
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# =====================
# EVENT CRUD (ADMIN)
# =====================
@app.route("/create_event", methods=["GET", "POST"])
@login_required
def create_event():
    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        event = Event(
            title=request.form["title"],
            description=request.form["description"],
            date=request.form["date"],
            time=request.form["time"],
            location=request.form["location"]
        )
        db.session.add(event)
        db.session.commit()
        return redirect(url_for("view_events"))

    return render_template("create_event.html")


# 🔹 EDIT EVENT
@app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    if current_user.role != "admin":
        return "Access Denied"

    event = Event.query.get_or_404(event_id)

    if request.method == "POST":
        event.title = request.form["title"]
        event.description = request.form["description"]
        event.date = request.form["date"]
        event.time = request.form["time"]
        event.location = request.form["location"]

        db.session.commit()
        return redirect(url_for("view_events"))

    return render_template("edit_event.html", event=event)


# 🔹 DELETE EVENT
@app.route("/delete_event/<int:event_id>")
@login_required
def delete_event(event_id):
    if current_user.role != "admin":
        return "Access Denied"

    event = Event.query.get_or_404(event_id)

    # also delete related registrations
    Registration.query.filter_by(event_id=event_id).delete()

    db.session.delete(event)
    db.session.commit()

    return redirect(url_for("view_events"))


@app.route("/events")
@login_required
def view_events():
    events = Event.query.all()
    return render_template("events.html", events=events)


# =====================
# EVENT REGISTRATION + QR
# =====================
@app.route("/register_event/<int:event_id>")
@login_required
def register_event(event_id):
    if current_user.role != "user":
        return "Only users can register for events"

    existing = Registration.query.filter_by(
        user_id=current_user.id,
        event_id=event_id
    ).first()

    if existing:
        return "You have already registered for this event"

    qr_data = f"user:{current_user.id}-event:{event_id}"
    qr = qrcode.make(qr_data)

    os.makedirs("qr_codes", exist_ok=True)
    qr_filename = f"qr_codes/user{current_user.id}_event{event_id}.png"
    qr.save(qr_filename)

    registration = Registration(
        user_id=current_user.id,
        event_id=event_id,
        qr_code=qr_filename
    )
    db.session.add(registration)
    db.session.commit()

    return "Registration successful! QR code generated."


@app.route("/my_registrations")
@login_required
def my_registrations():
    if current_user.role != "user":
        return "Access Denied"

    registrations = Registration.query.filter_by(
        user_id=current_user.id
    ).all()

    return render_template("my_registrations.html", registrations=registrations)


@app.route("/qr_codes/<path:filename>")
def qr_codes(filename):
    return send_from_directory("qr_codes", filename)


# =====================
# PARTICIPANT MANAGEMENT
# =====================
@app.route("/event_participants/<int:event_id>")
@login_required
def event_participants(event_id):
    if current_user.role != "admin":
        return "Access Denied"

    event = Event.query.get_or_404(event_id)
    registrations = Registration.query.filter_by(event_id=event_id).all()

    return render_template(
        "event_participants.html",
        event=event,
        registrations=registrations
    )


@app.route("/remove_participant/<int:reg_id>")
@login_required
def remove_participant(reg_id):
    if current_user.role != "admin":
        return "Access Denied"

    registration = Registration.query.get_or_404(reg_id)
    event_id = registration.event_id

    db.session.delete(registration)
    db.session.commit()

    return redirect(url_for("event_participants", event_id=event_id))


@app.route("/add_participant/<int:event_id>", methods=["POST"])
@login_required
def add_participant(event_id):
    if current_user.role != "admin":
        return "Access Denied"

    user_id = int(request.form["user_id"])

    existing = Registration.query.filter_by(
        user_id=user_id,
        event_id=event_id
    ).first()

    if not existing:
        reg = Registration(
            user_id=user_id,
            event_id=event_id,
            attendance="Absent"
        )
        db.session.add(reg)
        db.session.commit()

    return redirect(url_for("event_participants", event_id=event_id))


# =====================
# ATTENDANCE
# =====================
@app.route("/mark_attendance", methods=["GET", "POST"])
@login_required
def mark_attendance():
    if current_user.role != "admin":
        return "Access Denied"

    message = ""

    if request.method == "POST":
        try:
            qr_data = request.form["qr_data"]
            parts = qr_data.split("-")
            user_id = int(parts[0].split(":")[1])
            event_id = int(parts[1].split(":")[1])

            registration = Registration.query.filter_by(
                user_id=user_id,
                event_id=event_id
            ).first()

            if not registration:
                message = "Invalid QR Code"
            elif registration.attendance == "Present":
                message = "Attendance already marked"
            else:
                registration.attendance = "Present"
                db.session.commit()
                message = "Attendance marked successfully"

        except:
            message = "Invalid QR format"

    return render_template("mark_attendance.html", message=message)


# =====================
# ATTENDANCE REPORT
# =====================
@app.route("/attendance_report")
@login_required
def attendance_report():
    if current_user.role != "admin":
        return "Access Denied"

    registrations = Registration.query.all()
    return render_template("attendance_report.html", registrations=registrations)


@app.route("/attendance_report/download")
@login_required
def download_attendance_report():
    if current_user.role != "admin":
        return "Access Denied"

    registrations = Registration.query.all()

    def generate():
        yield "User ID,Event ID,Attendance\n"
        for reg in registrations:
            yield f"{reg.user_id},{reg.event_id},{reg.attendance}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_report.csv"}
    )


# =====================
# RUN
# =====================
if __name__ == "__main__":
    app.run(debug=True)
