
from flask import Blueprint, request
from db import get_db_connection
from decimal import Decimal
from datetime import date

fuel_bp = Blueprint("fuel", __name__)


@fuel_bp.route("/fuel-records", methods=["POST"])
def add_fuel_record():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400

    required = [
        "vehicle_id", "fill_date", "odometer_km",
        "litres", "total_cost", "full_tank_flag"
    ]

    missing = [key for key in required if key not in data]

    if missing:
        return {"error": "Missing fields", "fields": missing}, 400

    try:
        vehicle_id = int(data["vehicle_id"])
        odometer = Decimal(str(data["odometer_km"]))
        litres = Decimal(str(data["litres"]))
        total_cost = Decimal(str(data["total_cost"]))
        full_tank = data["full_tank_flag"]
        fill_date = data["fill_date"]

        if vehicle_id <= 0:
            raise ValueError()

        if not all(x.is_finite() for x in
                   (odometer, litres, total_cost)):
            raise ValueError()

        if odometer < 0 or litres <= 0 or total_cost < 0:
            raise ValueError()

        if type(full_tank) not in (int, bool) or full_tank not in (0, 1):
            raise ValueError()

        if not isinstance(fill_date, str):
            raise ValueError()

        date.fromisoformat(fill_date)

    except (ValueError, TypeError, ArithmeticError):
        return {"error": "Invalid fuel record data"}, 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT vehicle_id FROM vehicles WHERE vehicle_id = %s",
            (vehicle_id,)
        )

        if cursor.fetchone() is None:
            return {"error": "Vehicle not found"}, 404

        cursor.execute("""
            SELECT MAX(odometer_km) AS max_odometer
            FROM fuel_records
            WHERE vehicle_id = %s
        """, (vehicle_id,))

        previous = cursor.fetchone()["max_odometer"]

        if previous is not None and odometer < previous:
            return {"error": "Odometer reading is too low"}, 400

        cursor.execute("""
            INSERT INTO fuel_records
            (vehicle_id, fill_date, odometer_km, litres,
             total_cost, full_tank_flag)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            vehicle_id, fill_date, odometer,
            litres, total_cost, int(full_tank)
        ))

        connection.commit()

        return {
            "message": "Fuel record added successfully",
            "record_id": cursor.lastrowid
        }, 201

    except Exception:
        if connection is not None:
            connection.rollback()

        return {"error": "Could not save fuel record"}, 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()
