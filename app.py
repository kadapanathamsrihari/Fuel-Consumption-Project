from flask import Flask, request

from db import get_db_connection

from decimal import Decimal

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, request, send_file

app = Flask(__name__)
@app.route("/")
def home():
    return "Fuel Consumption Analysis System"

from fuel_routes import fuel_bp

app.register_blueprint(fuel_bp)


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
@app.route("/fuel-records")
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

@app.route("/reports")
def reports_index():
    return {
        "section": "Fuel Consumption Reports",
        "reports": [
            {
                "name": "Mileage Report",
                "url": "/reports/mileage",
                "description": "Calculate distance and fuel efficiency"
            },
            {
                "name": "Expense Report",
                "url": "/reports/expenses",
                "description": "Calculate fuel expenses per vehicle"
            },
            {
                "name": "Monthly Report",
                "url": "/reports/monthly",
                "description": "Summarize fuel usage by month"
            }
        ]
    }
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

    return report
@app.route("/reports/expenses")
def expenses_report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT
            v.vehicle_code,
            v.vehicle_type,
            SUM(f.total_cost) AS total_fuel_expense
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

    return {
        "report": "Fuel Expense Report",
        "data": results
    }
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
        ORDER BY month, v.vehicle_code
    """

    cursor.execute(query)
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "report": "Monthly Fuel Report",
        "data": results
    }

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
@app.route("/charts/expenses")
def expense_chart():
    conn = get_db_connection()

    query = """
        SELECT
            v.vehicle_code,
            SUM(f.total_cost) AS total_expense
        FROM vehicles v
        JOIN fuel_records f
            ON v.vehicle_id = f.vehicle_id
        GROUP BY v.vehicle_id, v.vehicle_code
        ORDER BY v.vehicle_code
    """

    df = pd.read_sql(query, conn)
    conn.close()

    plt.figure(figsize=(8, 5))
    plt.bar(df["vehicle_code"], df["total_expense"])
    plt.title("Total Fuel Expense by Vehicle")
    plt.xlabel("Vehicle")
    plt.ylabel("Total Expense (₹)")
    plt.tight_layout()

    plt.savefig("fuel_expenses.png")
    plt.close()

    return {
        "message": "Expense chart generated successfully",
        "chart_file": "fuel_expenses.png",
        "data": df.to_dict(orient="records")
    }

@app.route("/charts/expenses/image")
def expense_chart_image():
    return send_file("fuel_expenses.png", mimetype="image/png")
if __name__ == "__main__":
    app.run(debug=True)