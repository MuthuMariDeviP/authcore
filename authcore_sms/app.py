import os
import sys
import json
import sqlite3
import pandas as pd
import numpy as np
import cv2
import qrcode
import face_recognition

from datetime import datetime
from dotenv import load_dotenv
from flask import g

from flask import (
    Flask, render_template, request,
    session, redirect, url_for,
    flash, Response, send_file
)

from pyzbar.pyzbar import decode

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
now = datetime.now()


app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "authcore_secret"

DB = "authcore_sms.db"

def get_db():
    return sqlite3.connect(DB)


def load_known_faces():
    known_encodings = []
    known_ids = []

    base_path = os.path.join("static", "faces", "enrolled")

    if not os.path.exists(base_path):
        return known_encodings, known_ids

    for staff_id in os.listdir(base_path):
        staff_folder = os.path.join(base_path, staff_id)

        for img_name in os.listdir(staff_folder):
            img_path = os.path.join(staff_folder, img_name)
            image = face_recognition.load_image_file(img_path)
            encodings = face_recognition.face_encodings(image)

            if encodings:
                known_encodings.append(encodings[0])
                known_ids.append(staff_id)
                if not encodings:
                 print("NO FACE DETECTED")
                else:
                 print("FACE DETECTED SUCCESSFULLY")

    return known_encodings, known_ids

# ---------- HOME ----------
@app.route("/")
def home():
    return render_template("home.html")

# ---------- STAFF REGISTRATION ----------
@app.route("/staff/register", methods=["GET", "POST"])
def staff_register():
    if request.method == "POST":
        staff_id = request.form["staff_id"]
        name = request.form["name"]
        department = request.form["department"]
        designation = request.form["designation"]
        mobile = request.form["mobile"]

        try:
            con = sqlite3.connect("authcore_sms.db")
            cur = con.cursor()

            cur.execute("""
                INSERT INTO staff 
                (staff_id, name, department, designation, mobile) 
                VALUES (?, ?, ?, ?, ?)
            """, (staff_id, name, department, designation, mobile))

            con.commit()

            # -------- Generate QR Code --------
            qr_data = staff_id
            qr = qrcode.make(qr_data)

            qr_folder = os.path.join("static", "qrcodes")
            os.makedirs(qr_folder, exist_ok=True)

            qr.save(os.path.join(qr_folder, f"{staff_id}.png"))

            con.close()

            flash("Staff registered successfully!", "success")
            return redirect(url_for("staff_register"))

        except sqlite3.IntegrityError:
            con.close()
            flash("Staff ID already exists!", "error")
            return redirect(url_for("staff_register"))

        except Exception as e:
            con.close()
            print("QR Error:", e)
            flash("Error generating QR code!", "error")
            return redirect(url_for("staff_register"))

    return render_template("staff_register.html")

# ---------- QR ATTENDANCE PAGE ----------
@app.route("/attendance/qr")
def qr_attendance():
    return render_template("qr_attendance.html")

@app.route("/scan_qr")
def scan_qr():

    camera = cv2.VideoCapture(0)

    print("🎥 QR CAMERA STARTED")

    while True:
        success, frame = camera.read()
        if not success:
            break

        qr_codes = decode(frame)

        for qr in qr_codes:
            qr_data = qr.data.decode("utf-8")

            print("✅ QR DETECTED:", qr_data)

            session["qr_staff_id"] = qr_data

            camera.release()
            cv2.destroyAllWindows()

            return redirect(url_for("face_verify"))

        # ✅ SHOW CAMERA
        cv2.imshow("QR Scanner", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()

    return "QR Scan Failed"

@app.route('/verify_qr', methods=['POST'])
def verify_qr():
    # your QR logic here
    
    return render_template('face_verify.html', message="QR Verified Successfully")

@app.route("/face_verify")
def face_verify():

    staff_id = session.get("qr_staff_id")

    if not staff_id:
        return "QR not scanned"

    return render_template("face_verify.html", staff_id=staff_id)

@app.route("/face/verify")
def face_verify_camera():

    if "qr_staff_id" not in session:
        return "QR not scanned yet."

    staff_id = session["qr_staff_id"]

    known_encodings, known_ids = load_known_faces()

    camera = cv2.VideoCapture(0)

    while True:
        success, frame = camera.read()
        if not success:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        faces = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, faces)

        for encoding in encodings:

            matches = face_recognition.compare_faces(known_encodings, encoding)

            if True in matches:

                matched_index = matches.index(True)
                matched_id = known_ids[matched_index]

                if matched_id == staff_id:

                    save_attendance(staff_id, "QR+Face")

                    camera.release()
                    cv2.destroyAllWindows()

                    return f"Attendance Marked for {staff_id}"

        cv2.imshow("Face Verification", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()

    return "Face not verified"

def generate_face_frames():

    if "qr_staff_id" not in session:
        return

    staff_id = session["qr_staff_id"]

    known_encodings, known_ids = load_known_faces()

    camera = cv2.VideoCapture(0)

    marked = False   # ✅ prevent duplicates

    while True:

        success, frame = camera.read()
        if not success:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        faces = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, faces)

        for encoding in encodings:

            matches = face_recognition.compare_faces(known_encodings, encoding)

            if True in matches:

                index = matches.index(True)
                matched_id = known_ids[index]

                print("MATCHED:", matched_id, "SESSION:", staff_id)

                # ✅ FINAL CHECK
                if matched_id == staff_id and not marked:

                    print("✅ FACE VERIFIED")

                    # ✅ SAVE HERE
                    result = save_attendance(staff_id, "QR+Face")

                    if result:
                        print("✅ SAVED TO DB")
                    else:
                        print("⚠️ ALREADY EXISTS")

                    marked = True

        # show camera
        ret, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
        )

    camera.release()

    
@app.route("/face_camera")
def face_camera():

    if "qr_staff_id" not in session:
        return "QR not scanned"

    staff_id = session["qr_staff_id"]

    known_encodings, known_ids = load_known_faces()

    camera = cv2.VideoCapture(0)

    marked = False
    frame_count = 0   # ✅ ensure camera shows first

    print("🎥 CAMERA STARTED")

    while True:

        success, frame = camera.read()
        if not success:
            break

        frame_count += 1

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        faces = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, faces)

        for encoding in encodings:

            matches = face_recognition.compare_faces(known_encodings, encoding)

            if True in matches:

                index = matches.index(True)
                matched_id = known_ids[index]

                print("MATCH:", matched_id, "| EXPECTED:", staff_id)

                # ✅ WAIT FEW FRAMES BEFORE SAVING
                if matched_id == staff_id and not marked and frame_count > 20:

                    print("✅ FACE VERIFIED")

                    save_attendance(staff_id, "QR+Face")

                    marked = True

        # ✅ ALWAYS SHOW CAMERA
        cv2.imshow("Face Verification", frame)

        # ✅ BREAK AFTER SUCCESS (so user sees camera)
        if marked:
            cv2.waitKey(2000)  # show for 2 seconds
            break

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()

    return redirect(url_for("face_success"))

@app.route("/face_success")
def face_success():
    return render_template("attendance_success.html", msg="Attendance Marked Successfully")


@app.route("/face/enroll/<staff_id>")
def face_enroll(staff_id):

    save_path = os.path.join("static", "faces", "enrolled", staff_id)
    os.makedirs(save_path, exist_ok=True)

    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    count = 0

    while count < 20:
        success, frame = camera.read()
        if not success:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = face_recognition.face_locations(rgb)

        for (top, right, bottom, left) in faces:
            face_img = frame[top:bottom, left:right]
            cv2.imwrite(f"{save_path}/{count}.jpg", face_img)
            count += 1

        cv2.imshow("Face Enrollment - Press Q to Exit", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()

    return f"Face enrolled successfully for {staff_id}"

@app.route("/face/enroll")
def face_enroll_page():
    return render_template("face_enroll.html")

@app.route("/face/video/<staff_id>")
def face_video(staff_id):
    return Response(
        generate_enroll_frames(staff_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


def generate_enroll_frames(staff_id):

    save_path = os.path.join("static", "faces", "enrolled", staff_id)
    os.makedirs(save_path, exist_ok=True)

    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    count = 0

    while True:
        success, frame = camera.read()
        if not success:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = face_recognition.face_locations(rgb)

        for (top, right, bottom, left) in faces:
            if count < 20:
                face_img = frame[top:bottom, left:right]
                cv2.imwrite(f"{save_path}/{count}.jpg", face_img)
                count += 1

        cv2.putText(frame, f"Captured: {count}/20",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2)

        ret, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )

        if count >= 20:
            break

    camera.release()
    cv2.destroyAllWindows()

def save_attendance(staff_id, mode):

    conn = sqlite3.connect("authcore_sms.db")
    cursor = conn.cursor()

    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S")

    print("💾 TRY SAVE:", staff_id)

    # prevent duplicate
    cursor.execute(
        "SELECT 1 FROM attendance WHERE staff_id=? AND date=?",
        (staff_id, date)
    )

    if cursor.fetchone():
        print("⚠️ ALREADY EXISTS")
        conn.close()
        return False

    cursor.execute(
        "SELECT name, department FROM staff WHERE staff_id=?",
        (staff_id,)
    )

    staff = cursor.fetchone()

    if not staff:
        print("❌ STAFF NOT FOUND")
        conn.close()
        return False

    name, department = staff

    cursor.execute("""
        INSERT INTO attendance (staff_id, name, department, date, time, mode, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (staff_id, name, department, date, time, mode, "Present"))

    conn.commit()
    conn.close()

    print("✅ SAVED SUCCESSFULLY")
    return True

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    staff_id = request.form.get("staff_id")
    mode = request.form.get("mode")  # "QR" or "Face"
    
    if not staff_id:
        return "Staff ID missing", 400

    
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    con = get_db()
    cur = con.cursor()
    
    # Get staff name and department
    cur.execute("SELECT name, department FROM staff WHERE staff_id=?", (staff_id,))
    staff = cur.fetchone()
    
    if not staff:
        con.close()
        return "Invalid Staff ID", 400
    
    name, department = staff
    
    # Check if already marked today
    cur.execute("SELECT * FROM attendance WHERE staff_id=? AND date=?", (staff_id, date_str))
    existing = cur.fetchone()
    
    if existing:
        con.close()
        return render_template("attendance_success.html", 
                               message="Attendance already marked today.",
                               staff_id=staff_id)
    
    # Insert attendance with name & department
    cur.execute(
        "INSERT INTO attendance (staff_id, name, department, date, time, mode, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (staff_id, name, department, date_str, time_str, mode, "Present")
    )
    con.commit()
    con.close()
    
    return render_template("attendance_success.html", 
                           message="Attendance marked successfully!", 
                           staff_id=staff_id)

@app.route("/dashboard")
def dashboard():

    con = get_db()
    cur = con.cursor()

    # total staff
    cur.execute("SELECT COUNT(*) FROM staff")
    total_staff = cur.fetchone()[0]

    # present today
    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("""
    SELECT COUNT(DISTINCT staff_id)
    FROM attendance
    WHERE date = ?
    """, (today,))
    present_today = cur.fetchone()[0]

    absent_today = total_staff - present_today

    # staff list
    cur.execute("SELECT staff_id, name, department FROM staff")
    staff = cur.fetchall()

    con.close()

    return render_template(
        "dashboard_staff.html",
        total_staff=total_staff,
        present_today=present_today,
        absent_today=absent_today,
        staff=staff
    )

@app.route("/staff/dashboard/<staff_id>")
def staff_dashboard(staff_id):

    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT staff_id,name,department,designation,mobile
        FROM staff
        WHERE staff_id=?
    """,(staff_id,))

    staff = cur.fetchone()

    cur.execute("""
        SELECT date,time,mode
        FROM attendance
        WHERE staff_id=?
        ORDER BY date DESC
    """,(staff_id,))

    attendance = cur.fetchall()

    con.close()

    return render_template(
        "staff_dashboard.html",
        staff=staff,
        attendance=attendance
    )


@app.route("/view_attendance", methods=["GET", "POST"])
def view_attendance():

    conn = sqlite3.connect("authcore_sms.db")
    cursor = conn.cursor()

    records = []

    if request.method == "POST":

        date = request.form.get("date")
        status = request.form.get("status")

        # ✅ PRESENT FILTER
        if status == "Present":

            query = """
            SELECT staff_id, name, department, date, time, mode, status
            FROM attendance
            WHERE date = ?
            """
            cursor.execute(query, (date,))
            records = cursor.fetchall()

        # ✅ ABSENT FILTER (IMPORTANT FIX)
        elif status == "Absent":

            query = """
            SELECT s.staff_id, s.name, s.department, ?, '-', '-', 'Absent'
            FROM staff s
            WHERE s.staff_id NOT IN (
                SELECT staff_id FROM attendance WHERE date = ?
            )
            """
            cursor.execute(query, (date, date))
            records = cursor.fetchall()

        else:
            # ALL DATA
            cursor.execute("""
                SELECT staff_id, name, department, date, time, mode, status
                FROM attendance
                ORDER BY date DESC
            """)
            records = cursor.fetchall()

    else:
        cursor.execute("""
            SELECT staff_id, name, department, date, time, mode, status
            FROM attendance
            ORDER BY date DESC
        """)
        records = cursor.fetchall()

    conn.close()

    return render_template("view_attendance.html", records=records)

@app.route("/leave_ai", methods=["GET","POST"])
def leave_ai():

    response = ""

    if request.method == "POST":

        staff_id = request.form["staff_id"]
        question = request.form["question"]

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()

        if question == "casual_leave":

            response = "Employees are allowed 12 casual leaves per year."

        elif question == "leave_balance":

            total_leave = 12

            cursor.execute("""
            SELECT SUM(days)
            FROM leave_records
            WHERE staff_id=? AND leave_type='Casual'
            """,(staff_id,))

            used = cursor.fetchone()[0]

            if used is None:
                used = 0

            remaining = total_leave - used

            response = f"You have {remaining} casual leave days remaining."

        elif question == "leave_application":

            total_leave = 12

            cursor.execute("""
            SELECT SUM(days)
            FROM leave_records
            WHERE staff_id=? AND leave_type='Casual'
            """,(staff_id,))

            used = cursor.fetchone()[0]

            if used is None:
                used = 0

            remaining = total_leave - used

            if remaining > 0:
                response = f"Yes. You can apply for leave. You still have {remaining} leave days."
            else:
                response = "No. You have already used all your leaves."

        conn.close()

    return render_template("leave_ai.html", response=response)



@app.route("/reports")
def reports():
    return render_template("reports.html")

@app.route("/generate_report", methods=["POST"])
def generate_report():
    report_type = request.form["report_type"]
    staff_id = request.form.get("staff_id")
    department = request.form.get("department")
    from_date = request.form["from_date"]
    to_date = request.form["to_date"]

    conn = sqlite3.connect(DB)

    query = "SELECT * FROM attendance WHERE date BETWEEN ? AND ?"
    params = [from_date, to_date]

    if report_type == "individual":
        query += " AND staff_id=?"
        params.append(staff_id)

    elif report_type == "department":
        query += " AND department=?"
        params.append(department)

    # Run the query regardless of report_type
    df = pd.read_sql_query(query, conn, params=params)

    file_name = "attendance_report.xlsx"
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
