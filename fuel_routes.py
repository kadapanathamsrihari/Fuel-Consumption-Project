
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

        if not all(x.is_finite() for x in (odometer, litres, total_cost)):
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


@fuel_bp.route("/vehicles", methods=["POST"])
def add_vehicle():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400

    vehicle_code = str(data.get("vehicle_code", "")).strip().upper()
    vehicle_type = str(data.get("vehicle_type", "")).strip()
    fuel_type = str(data.get("fuel_type", "")).strip()

    if not vehicle_code or not vehicle_type or not fuel_type:
        return {"error": "All vehicle fields are required"}, 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO vehicles (vehicle_code, vehicle_type, fuel_type)
            VALUES (%s, %s, %s)
        """, (vehicle_code, vehicle_type, fuel_type))

        connection.commit()

        return {
            "message": "Vehicle added successfully",
            "vehicle_id": cursor.lastrowid,
            "vehicle_code": vehicle_code
        }, 201

    except Exception as error:
        if connection is not None:
            connection.rollback()

        if getattr(error, "errno", None) == 1062:
            return {"error": "That vehicle code already exists"}, 409

        return {"error": "Could not save vehicle"}, 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

@fuel_bp.route("/fuel-records/<int:record_id>", methods=["PUT"])
def update_fuel_record(record_id):
    data = request.get_json(silent=True) or {}

    required = [
        "fill_date",
        "odometer_km",
        "litres",
        "total_cost",
        "full_tank_flag"
    ]

    if any(field not in data for field in required):
        return {"error": "All fields are required"}, 400

    try:
        odometer = int(data["odometer_km"])
        litres = Decimal(str(data["litres"]))
        total_cost = Decimal(str(data["total_cost"]))
        full_tank = int(data["full_tank_flag"])

        if odometer < 0 or litres <= 0 or total_cost < 0:
            return {"error": "Invalid numeric values"}, 400

        if full_tank not in (0, 1):
            return {"error": "full_tank_flag must be 0 or 1"}, 400

        from datetime import date
        date.fromisoformat(data["fill_date"])

    except (ValueError, TypeError, ArithmeticError):
        return {"error": "Invalid date or numeric values"}, 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT vehicle_id FROM fuel_records WHERE record_id = %s",
            (record_id,)
        )
        record = cursor.fetchone()

        if not record:
            return {"error": "Fuel record not found"}, 404

        cursor.execute(
            """
            SELECT MAX(odometer_km) AS max_odometer
            FROM fuel_records
            WHERE vehicle_id = %s AND record_id != %s
            """,
            (record["vehicle_id"], record_id)
        )
        result = cursor.fetchone()

        if result["max_odometer"] is not None:
            if odometer < result["max_odometer"]:
                return {
                    "error": "Odometer reading cannot be lower than another record for this vehicle"
                }, 400

        cursor.execute(
            """
            UPDATE fuel_records
            SET fill_date = %s,
                odometer_km = %s,
                litres = %s,
                total_cost = %s,
                full_tank_flag = %s
            WHERE record_id = %s
            """,
            (
                data["fill_date"],
                odometer,
                str(litres),
                str(total_cost),
                full_tank,
                record_id
            )
        )

        conn.commit()

        return {
            "message": "Fuel record updated successfully",
            "record_id": record_id
        }, 200

    except Exception:
        conn.rollback()
        return {"error": "Unable to update fuel record"}, 500

    finally:
        cursor.close()
        conn.close()


@fuel_bp.route("/fuel-records/<int:record_id>", methods=["DELETE"])
def delete_fuel_record(record_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM fuel_records WHERE record_id = %s",
            (record_id,)
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return {"error": "Fuel record not found"}, 404

        conn.commit()

        return {
            "message": "Fuel record deleted successfully",
            "record_id": record_id
        }, 200
    except Exception:
        conn.rollback()
        return {"error": "Unable to delete fuel record"}, 500

    finally:
        cursor.close()
        conn.close()
@fuel_bp.route("/vehicles/<int:vehicle_id>", methods=["PUT"])
def update_vehicle(vehicle_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body"}, 400

    vehicle_code = data.get("vehicle_code")
    vehicle_type = data.get("vehicle_type")
    fuel_type = data.get("fuel_type")

    if not all(isinstance(x, str) and x.strip()
               for x in [vehicle_code, vehicle_type, fuel_type]):
        return {"error": "All vehicle fields are required"}, 400

    vehicle_code = vehicle_code.strip().upper()
    vehicle_type = vehicle_type.strip()
    fuel_type = fuel_type.strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT vehicle_id FROM vehicles WHERE vehicle_id = %s",
            (vehicle_id,)
        )

        if cursor.fetchone() is None:
            return {"error": "Vehicle not found"}, 404

        cursor.execute("""
            UPDATE vehicles
            SET vehicle_code = %s,
                vehicle_type = %s,
                fuel_type = %s
            WHERE vehicle_id = %s
        """, (vehicle_code, vehicle_type, fuel_type, vehicle_id))

        conn.commit()

        return {
            "message": "Vehicle updated successfully",
            "vehicle_id": vehicle_id
        }, 200

    except Exception as error:
        if conn:
            conn.rollback()

        if getattr(error, "errno", None) == 1062:
            return {"error": "Vehicle code already exists"}, 409

        return {"error": "Could not update vehicle"}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
@fuel_bp.route("/vehicles/<int:vehicle_id>", methods=["DELETE"])
def delete_vehicle(vehicle_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT vehicle_id FROM vehicles WHERE vehicle_id = %s",
            (vehicle_id,)
        )

        if cursor.fetchone() is None:
            return {"error": "Vehicle not found"}, 404

        cursor.execute("""
            SELECT COUNT(*)
            FROM fuel_records
            WHERE vehicle_id = %s
        """, (vehicle_id,))

        record_count = cursor.fetchone()[0]

        if record_count > 0:
            return {
                "error": "Cannot delete vehicle because fuel records exist",
                "associated_records": record_count
            }, 409

        cursor.execute(
            "DELETE FROM vehicles WHERE vehicle_id = %s",
            (vehicle_id,)
        )

        conn.commit()

        return {
            "message": "Vehicle deleted successfully",
            "vehicle_id": vehicle_id
        }, 200

    except Exception:
        if conn:
            conn.rollback()

        return {"error": "Could not delete vehicle"}, 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()