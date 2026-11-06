from flask import Flask, request, send_file, render_template, url_for

from db import get_db_connection

from decimal import Decimal
from io import BytesIO

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, request, send_file
from fuel_routes import fuel_bp
app = Flask(__name__)
app.register_blueprint(fuel_bp)

@app.route("/")
def home():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM vehicles")
    total_vehicles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fuel_records")
    total_records = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(total_cost), 0)
        FROM fuel_records
    """)
    total_expenses = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return render_template(
        "index.html",
        total_vehicles=total_vehicles,
        total_records=total_records,
        total_expenses=total_expenses
    )

@app.route("/test-db")
def test_db():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM vehicles")
    result = cursor.fetchone()

    cursor.close()
    connection.close()

    return f"Database connected! Total vehicles: {result[0]}"
@app.route("/vehicles")
def get_vehicles():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM vehicles")
    vehicles = cursor.fetchall()

    cursor.close()
    connection.close()

    return vehicles

@app.route("/fuel-records", methods=["GET"])
def get_fuel_records():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    vehicle_id = request.args.get("vehicle_id")

    if vehicle_id:
        cursor.execute("""
            SELECT *
            FROM fuel_records
            WHERE vehicle_id = %s
            ORDER BY fill_date
        """, (vehicle_id,))
    else:
        cursor.execute("""
            SELECT *
            FROM fuel_records
            ORDER BY vehicle_id, fill_date
        """)

    records = cursor.fetchall()

    cursor.close()
    connection.close()

    return records

@app.route("/records")
def records_page():
    return render_template("fuel_records.html")
@app.route("/vehicle-management")
def vehicles_page():
    return render_template("vehicles.html")

@app.route("/reports")
def reports_index():
    return render_template("reports.html")

@app.route("/reports/mileage")
def mileage_report():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            v.vehicle_code,
            f.record_id,
            f.fill_date,
            f.odometer_km,
            f.litres,
            f.full_tank_flag
        FROM fuel_records f
        JOIN vehicles v ON f.vehicle_id = v.vehicle_id
        ORDER BY v.vehicle_id, f.fill_date, f.record_id
    """)

    records = cursor.fetchall()
    cursor.close()
    connection.close()

    report = []
    previous = {}

    for record in records:
        vehicle = record["vehicle_code"]
        mileage = None
        last = previous.get(vehicle)

        if (
            last is not None
            and last["full_tank_flag"]
            and record["full_tank_flag"]
        ):
            distance = (
                record["odometer_km"] - last["odometer_km"]
            )
            if distance > 0:
                mileage = round(
                    float(distance / record["litres"]), 2
                )

        report.append({
            "vehicle_code": vehicle,
            "fill_date": str(record["fill_date"]),
            "distance_km": (
                float(record["odometer_km"] - last["odometer_km"])
                if last is not None else None
            ),
            "mileage_kmpl": mileage
        })

        previous[vehicle] = record

    return render_template("mileage_report.html", records=report)
@app.route("/reports/expenses")
def expenses_report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT
            v.vehicle_code,
            v.vehicle_type,
            SUM(f.total_cost) AS total_fuel_expense,
            SUM(f.litres) AS total_litres,
            COUNT(f.record_id) AS total_fillings
        FROM vehicles v
        JOIN fuel_records f
            ON v.vehicle_id = f.vehicle_id
        GROUP BY v.vehicle_id, v.vehicle_code, v.vehicle_type
        ORDER BY total_fuel_expense DESC
    """

    cursor.execute(query)
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    summary = {
        "total_litres": sum(
            (row["total_litres"] or Decimal("0") for row in results),
            Decimal("0")
        ),
        "total_expense": sum(
            (row["total_fuel_expense"] or Decimal("0") for row in results),
            Decimal("0")
        ),
        "total_fillings": sum((row["total_fillings"] or 0 for row in results), 0)
    }

    return render_template(
        "expenses_report.html",
        records=results,
        summary=summary
    )
@app.route("/reports/monthly")
def monthly_report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT
            v.vehicle_code,
            v.vehicle_type,
            DATE_FORMAT(f.fill_date, '%Y-%m') AS month,
            SUM(f.litres) AS total_litres,
            SUM(f.total_cost) AS total_expense,
            COUNT(f.record_id) AS total_fillings
        FROM vehicles v
        JOIN fuel_records f
            ON v.vehicle_id = f.vehicle_id
        GROUP BY
            v.vehicle_id,
            v.vehicle_code,
            v.vehicle_type,
            DATE_FORMAT(f.fill_date, '%Y-%m')
        ORDER BY month DESC, v.vehicle_code
    """

    cursor.execute(query)
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    summary = {
        "total_litres": sum(
            (row["total_litres"] or Decimal("0") for row in results),
            Decimal("0")
        ),
        "total_expense": sum(
            (row["total_expense"] or Decimal("0") for row in results),
            Decimal("0")
        ),
        "total_fillings": sum((row["total_fillings"] or 0 for row in results), 0)
    }

    return render_template(
        "monthly_report.html",
        records=results,
        summary=summary
    )

@app.route("/analysis/expenses")
def analyze_expenses():
    conn = get_db_connection()

    query = """
        SELECT
            v.vehicle_code,
            v.vehicle_type,
            f.litres,
            f.total_cost,
            f.fill_date
        FROM vehicles v
        JOIN fuel_records f
            ON v.vehicle_id = f.vehicle_id
    """

    df = pd.read_sql(query, conn)
    conn.close()

    result = (
        df.groupby(["vehicle_code", "vehicle_type"])
        .agg(
            total_litres=("litres", "sum"),
            total_expense=("total_cost", "sum"),
            average_fill_cost=("total_cost", "mean")
        )
        .reset_index()
    )

    return {
        "analysis": "Fuel Expense Analysis",
        "data": result.to_dict(orient="records")
    }
def _get_expense_data():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT v.vehicle_code,
                   COALESCE(SUM(f.total_cost), 0) AS total_expense
            FROM vehicles v
            LEFT JOIN fuel_records f ON f.vehicle_id = v.vehicle_id
            GROUP BY v.vehicle_id, v.vehicle_code
            ORDER BY v.vehicle_code
        """)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    frame = pd.DataFrame(rows, columns=["vehicle_code", "total_expense"])
    if not frame.empty:
        frame["total_expense"] = pd.to_numeric(
            frame["total_expense"], errors="coerce"
        ).fillna(0)
    return frame


def _expense_chart_response(chart_type):
    frame = _get_expense_data()
    figure, axis = plt.subplots(figsize=(8, 4.8))
    positive = frame[frame["total_expense"] > 0] if not frame.empty else frame

    if frame.empty or (chart_type == "pie" and positive.empty):
        axis.text(0.5, 0.5, "No expense data available", ha="center", va="center")
        axis.axis("off")
    elif chart_type == "pie":
        colors = [
            "#11aabd", "#087f99", "#42c4d2", "#15536a", "#91e0e6",
            "#52a8bd", "#2b6e86", "#8ecfd5", "#174b5b", "#b0e7ea"
        ]
        axis.pie(
            positive["total_expense"],
            labels=positive["vehicle_code"],
            autopct="%1.1f%%",
            startangle=90,
            colors=colors,
            textprops={"color": "#244652", "fontsize": 9}
        )
        axis.set_title("Share of Fuel Expenses by Vehicle", color="#103c4b", pad=16)
        axis.axis("equal")
    else:
        axis.bar(frame["vehicle_code"], frame["total_expense"], color="#0c9fb6", width=0.62)
        axis.set_title("Total Fuel Expense by Vehicle", color="#103c4b", pad=16)
        axis.set_xlabel("Vehicle", color="#49656e")
        axis.set_ylabel("Total expense (₹)", color="#49656e")
        axis.grid(axis="y", linestyle="--", alpha=0.22)
        axis.set_axisbelow(True)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(axis="x", rotation=25, labelcolor="#49656e")
        axis.tick_params(axis="y", labelcolor="#49656e")

    figure.tight_layout()
    image = BytesIO()
    try:
        figure.savefig(image, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)
    image.seek(0)
    response = send_file(image, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/charts/expenses")
def expense_chart():
    frame = _get_expense_data()
    return {
        "message": "Expense chart is ready",
        "chart_file": "served dynamically",
        "chart_url": url_for("expense_chart_image"),
        "data": frame.to_dict(orient="records")
    }


@app.route("/charts/expenses/image")
def expense_chart_image():
    return _expense_chart_response("bar")


@app.route("/charts/expenses/pie")
def expense_pie_chart():
    frame = _get_expense_data()
    return {
        "message": "Expense distribution chart is ready",
        "chart_url": url_for("expense_pie_chart_image"),
        "data": frame.to_dict(orient="records")
    }


@app.route("/charts/expenses/pie/image")
def expense_pie_chart_image():
    return _expense_chart_response("pie")


@app.route("/add-fuel")
def add_fuel_page():
    return render_template("add_fuel.html")
@app.route("/charts")
def charts_page():
    return render_template("charts.html")
if __name__ == "__main__":
    app.run(debug=True)