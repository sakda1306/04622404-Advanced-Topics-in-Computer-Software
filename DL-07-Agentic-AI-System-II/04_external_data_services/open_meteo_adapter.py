import json  # ใช้แปลงข้อมูล JSON จาก API เป็นข้อมูล Python และแสดงผลกลับเป็น JSON
import math  # ใช้ปฏิเสธตัวเลขที่ไม่สิ้นสุดหรือไม่ใช่ตัวเลขจริง
import socket  # ใช้จำแนกกรณีเครือข่ายหมดเวลารอ
from datetime import datetime, timedelta, timezone  # ใช้จัดการเวลา UTC และเวลาหมดอายุของข้อมูล
from urllib.error import HTTPError, URLError  # ใช้จำแนกข้อผิดพลาด HTTP และเครือข่าย
from urllib.parse import urlencode  # ใช้ประกอบพารามิเตอร์ใน URL ให้ถูกต้อง
from urllib.request import Request, urlopen  # ใช้สร้างคำขอและเรียก API ผ่าน HTTPS

BASE_URL = "https://api.open-meteo.com/v1/forecast"  # ที่อยู่ API พยากรณ์อากาศ
HOURLY_FIELDS = (  # รายชื่อข้อมูลรายชั่วโมงที่ต้องการจาก API
    "temperature_2m",  # อุณหภูมิอากาศที่ความสูง 2 เมตร หน่วยองศาเซลเซียส
    "rain",  # ปริมาณฝนของชั่วโมงก่อนหน้า หน่วยมิลลิเมตร
    "precipitation_probability",  # โอกาสเกิดฝนหรือหยาดน้ำฟ้า หน่วยเปอร์เซ็นต์
    "snowfall",  # ปริมาณหิมะของชั่วโมงก่อนหน้า หน่วยเซนติเมตร
    "wind_speed_10m",  # ความเร็วลมที่ความสูง 10 เมตร หน่วยกิโลเมตรต่อชั่วโมง
    "wind_direction_10m",  # ทิศทางลมที่ความสูง 10 เมตร หน่วยองศา
    "visibility",  # ระยะการมองเห็น หน่วยเมตร
    "weather_code",  # รหัสสภาพอากาศตามมาตรฐาน WMO
)  # จบรายชื่อข้อมูลที่ต้องการ


class WeatherProviderError(RuntimeError):  # ข้อผิดพลาดเมื่อเรียกผู้ให้บริการไม่สำเร็จ
    pass  # ให้ผู้เรียกแยกจากกรณีข้อมูลผิดรูปแบบได้


class WeatherDataError(ValueError):  # ข้อผิดพลาดเมื่อ JSON ที่ได้รับใช้ต่อไม่ได้
    pass  # ห้ามตีความข้อมูลผิดรูปแบบว่าอากาศปลอดภัย


def _load_weather_json(request: Request) -> dict:  # เรียก API และตรวจว่าได้ JSON object
    try:  # แยกสาเหตุที่เรียก API ไม่สำเร็จ
        with urlopen(request, timeout=10) as response:  # รอคำตอบไม่เกิน 10 วินาที
            data = json.load(response)  # แปลงคำตอบ JSON เป็นข้อมูล Python
    except HTTPError as error:  # เซิร์ฟเวอร์ตอบรหัส HTTP ที่เป็นข้อผิดพลาด
        raise WeatherProviderError(f"Open-Meteo HTTP {error.code}") from error  # ส่งรหัสให้ผู้เรียกจัดการ
    except (TimeoutError, socket.timeout) as error:  # การเชื่อมต่อหมดเวลารอ
        raise WeatherProviderError("Open-Meteo timeout") from error  # ไม่คืนค่าปลอมแทนข้อมูลจริง
    except URLError as error:  # เครือข่ายหรือ DNS มีปัญหา
        reason = "timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "network error"  # แยก timeout
        raise WeatherProviderError(f"Open-Meteo {reason}") from error  # แจ้งสาเหตุอย่างสั้น
    except (json.JSONDecodeError, UnicodeDecodeError) as error:  # คำตอบไม่ใช่ JSON ที่อ่านได้
        raise WeatherDataError("Open-Meteo returned invalid JSON") from error  # ไม่ส่งข้อมูลผิดรูปแบบต่อ

    if not isinstance(data, dict):  # คำตอบหลักต้องเป็น JSON object
        raise WeatherDataError("Open-Meteo response must be an object")  # ปฏิเสธ list หรือค่าอื่น
    return data  # คืนข้อมูลที่ผ่านการตรวจขั้นต้น


def _utc_time(value: object) -> datetime:  # แปลงเวลา ISO 8601 ที่ API ส่งมาเป็น UTC
    if not isinstance(value, str):  # เวลาต้องเป็นข้อความ
        raise WeatherDataError("Open-Meteo time is missing or invalid")  # ปฏิเสธค่าที่ขาดหรือผิดชนิด
    try:  # ตรวจรูปแบบวันที่และเวลา
        parsed = datetime.fromisoformat(value)  # อ่านเวลา ISO 8601
    except ValueError as error:  # ข้อความไม่ใช่เวลา ISO 8601
        raise WeatherDataError("Open-Meteo time is missing or invalid") from error  # ไม่เดาเวลา
    if parsed.tzinfo is None:  # API ถูกขอให้ส่ง UTC แต่ไม่แนบ offset
        return parsed.replace(tzinfo=timezone.utc)  # ระบุ UTC ให้เวลาแบบ naive
    return parsed.astimezone(timezone.utc)  # แปลง offset ที่แนบมาเป็น UTC


def _weather_value(value: object, field: str) -> int | float | None:  # ตรวจค่าตัวเลขของฟิลด์อากาศ
    if value is None:  # ผู้ให้บริการอาจไม่มีข้อมูลฟิลด์นี้
        return None  # เก็บว่าข้อมูลขาด ไม่สร้างตัวเลขใหม่
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):  # ตรวจชนิดและความสมเหตุสมผลเบื้องต้น
        raise WeatherDataError(f"Open-Meteo {field} must be a finite number")  # ไม่ส่งข้อความหรือค่า NaN ต่อ
    return value  # คืนค่าตัวเลขจริงจาก API


def fetch_current_weather(latitude: float, longitude: float) -> dict:  # ดึงสภาพอากาศใกล้เวลาปัจจุบันของหนึ่งพิกัด
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):  # ตรวจช่วงพิกัดก่อนเรียก API
        raise ValueError("Invalid latitude or longitude")  # แจ้งเมื่อพิกัดไม่ถูกต้อง

    params = {  # เตรียมพารามิเตอร์สำหรับข้อมูล current
        "latitude": latitude,  # ละติจูดของจุดที่สนใจ
        "longitude": longitude,  # ลองจิจูดของจุดที่สนใจ
        "current": ",".join(HOURLY_FIELDS),  # ขอข้อมูลอากาศชนิดเดียวกับพยากรณ์
        "timezone": "UTC",  # ขอเวลาเป็น UTC เพื่อเทียบข้ามระบบได้
        "temperature_unit": "celsius",  # ขอหน่วยองศาเซลเซียส
        "wind_speed_unit": "kmh",  # ขอความเร็วลมเป็นกิโลเมตรต่อชั่วโมง
        "precipitation_unit": "mm",  # ขอปริมาณฝนเป็นมิลลิเมตร
    }  # จบพารามิเตอร์
    request_url = f"{BASE_URL}?{urlencode(params)}"  # ประกอบ URL พร้อมพารามิเตอร์
    request = Request(request_url, headers={"User-Agent": "Team-D-travel-project/0.1"})  # ระบุชื่อโปรแกรม

    data = _load_weather_json(request)  # เรียก API พร้อมตรวจข้อผิดพลาด

    current = data.get("current")  # เลือกส่วนข้อมูลใกล้เวลาปัจจุบัน
    if not isinstance(current, dict) or not current.get("time") or current.get("temperature_2m") is None:  # ตรวจข้อมูลจำเป็น
        raise WeatherDataError("Open-Meteo current temperature is unavailable")  # ไม่สร้างค่าอุณหภูมิทดแทน

    valid_at = _utc_time(current["time"])  # แปลงเวลาของข้อมูลเป็น UTC
    fetched_at = datetime.now(timezone.utc)  # บันทึกเวลาที่เราเรียกสำเร็จ
    values = {field: _weather_value(current.get(field), field) for field in HOURLY_FIELDS}  # ตรวจทุกค่าที่ API ส่งมา
    missing = any(value is None for value in values.values())  # ตรวจฟิลด์ที่ API ไม่ส่งมา
    return {  # คืน record ที่แยกจากข้อมูลพยากรณ์
        "schema_version": "weather-record-v0.1",  # รุ่นทดลองของรูปแบบข้อมูล
        "data_kind": "model_current",  # ระบุว่าเป็นค่าปัจจุบันจากแบบจำลอง ไม่ใช่เครื่องวัดสด
        "latitude": latitude,  # พิกัดละติจูด
        "longitude": longitude,  # พิกัดลองจิจูด
        "valid_at": valid_at.isoformat(),  # เวลาที่ข้อมูลอากาศนี้อ้างอิง
        "fetched_at": fetched_at.isoformat(),  # เวลาที่ดึงข้อมูล
        "expires_at": (fetched_at + timedelta(minutes=30)).isoformat(),  # เวลาหมดอายุแคชทดลอง 30 นาที
        "source": "Open-Meteo",  # ผู้ให้บริการข้อมูล
        "source_lineage": request_url,  # URL ต้นทางสำหรับตรวจสอบย้อนกลับ
        "quality_flags": ["incomplete"] if missing else [],  # ทำเครื่องหมายเมื่อบางฟิลด์ไม่มีค่า
        "temperature_c": values["temperature_2m"],  # อุณหภูมิใกล้เวลาปัจจุบัน
        "rain_mm": values["rain"],  # ปริมาณฝนที่ API ส่งมา
        "rain_probability_percent": values["precipitation_probability"],  # โอกาสเกิดฝน
        "snowfall_cm": values["snowfall"],  # ปริมาณหิมะ
        "wind_speed_kmh": values["wind_speed_10m"],  # ความเร็วลม
        "wind_direction_degrees": values["wind_direction_10m"],  # ทิศทางลม
        "visibility_m": values["visibility"],  # ทัศนวิสัย
        "weather_code": values["weather_code"],  # รหัสสภาพอากาศ
    }  # จบ record


def fetch_weather_forecast(latitude: float, longitude: float) -> list[dict]:  # รับพิกัดหนึ่งจุดและคืนข้อมูลพยากรณ์รายชั่วโมง
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):  # ตรวจช่วงค่าพิกัดที่โลกยอมรับได้
        raise ValueError("Invalid latitude or longitude")  # แจ้งข้อผิดพลาดถ้าพิกัดไม่ถูกต้อง

    params = {  # เตรียมพารามิเตอร์ที่จะส่งไปยัง Open-Meteo
        "latitude": latitude,  # ละติจูดของจุดที่ต้องการข้อมูล
        "longitude": longitude,  # ลองจิจูดของจุดที่ต้องการข้อมูล
        "hourly": ",".join(HOURLY_FIELDS),  # รวมชื่อข้อมูลรายชั่วโมงเป็นข้อความคั่นด้วยจุลภาค
        "timezone": "UTC",  # ขอให้ API ส่งเวลามาเป็นเวลา UTC
        "forecast_days": 2,  # ขอพยากรณ์สองวันเพื่อทดลอง
        "temperature_unit": "celsius",  # ขออุณหภูมิเป็นองศาเซลเซียส
        "wind_speed_unit": "kmh",  # ขอความเร็วลมเป็นกิโลเมตรต่อชั่วโมง
        "precipitation_unit": "mm",  # ขอปริมาณฝนเป็นมิลลิเมตร
    }  # จบชุดพารามิเตอร์
    query = urlencode(params)  # แปลงพารามิเตอร์เป็นรูปแบบที่ใช้ต่อท้าย URL
    request_url = f"{BASE_URL}?{query}"  # รวมที่อยู่ API กับพารามิเตอร์
    request = Request(request_url, headers={"User-Agent": "Team-D-travel-project/0.1"})  # สร้างคำขอพร้อมชื่อโปรแกรม

    data = _load_weather_json(request)  # เรียก API พร้อมตรวจข้อผิดพลาด

    hourly = data.get("hourly")  # เลือกส่วนข้อมูลพยากรณ์รายชั่วโมง
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list) or not hourly["time"]:  # ตรวจโครงสร้างจำเป็น
        raise WeatherDataError("Open-Meteo hourly time is unavailable")  # ไม่ส่งพยากรณ์ที่ไร้เวลา
    fetched_at = datetime.now(timezone.utc)  # บันทึกเวลาที่เราได้รับข้อมูลเป็น UTC
    records = []  # เตรียมรายการเก็บผลลัพธ์ที่แปลงแล้ว

    for index, hour in enumerate(hourly["time"]):  # วนทีละชั่วโมงพร้อมตำแหน่งในรายการ
        values = {}  # เตรียมข้อมูลอากาศของชั่วโมงปัจจุบัน
        for field in HOURLY_FIELDS:  # วนอ่านข้อมูลอากาศทุกชนิดที่ร้องขอ
            field_values = hourly.get(field)  # อ่านรายการค่าของข้อมูลชนิดนี้ ถ้าไม่มีจะได้ None
            if isinstance(field_values, list) and index < len(field_values):  # ตรวจว่ามีค่าตรงกับชั่วโมงนี้จริง
                values[field] = _weather_value(field_values[index], field)  # ตรวจและเก็บค่าจาก API
            else:  # กรณี API ไม่ส่งข้อมูลชนิดนี้หรือส่งมาไม่ครบ
                values[field] = None  # ใช้ None เพื่อบอกว่าไม่มีข้อมูล ไม่เดาค่าขึ้นมา

        flags = ["incomplete"] if any(value is None for value in values.values()) else []  # ทำเครื่องหมายเมื่อข้อมูลบางช่องขาด
        valid_at = _utc_time(hour).isoformat()  # แปลงเวลาพยากรณ์เป็น ISO 8601 พร้อม UTC
        record = {  # สร้างข้อมูลมาตรฐานหนึ่งรายการสำหรับพิกัดและชั่วโมงนี้
            "schema_version": "weather-record-v0.1",  # รุ่นของรูปแบบข้อมูลนี้ ยังเป็นรุ่นทดลอง
            "data_kind": "forecast",  # แยกข้อมูลพยากรณ์ออกจาก model_current
            "latitude": latitude,  # พิกัดละติจูดของข้อมูล
            "longitude": longitude,  # พิกัดลองจิจูดของข้อมูล
            "valid_at": valid_at,  # เวลาที่ค่าพยากรณ์นี้ใช้ได้
            "fetched_at": fetched_at.isoformat(),  # เวลาที่ระบบดึงข้อมูลมา
            "expires_at": (fetched_at + timedelta(minutes=30)).isoformat(),  # เวลาหมดอายุแคชที่กำหนดไว้ทดลอง 30 นาที
            "source": "Open-Meteo",  # ชื่อผู้ให้บริการข้อมูล
            "source_lineage": request_url,  # URL ที่ใช้ดึงข้อมูลเพื่อย้อนตรวจแหล่งที่มา
            "quality_flags": flags,  # รายการข้อสังเกตเกี่ยวกับคุณภาพข้อมูล
            "temperature_c": values["temperature_2m"],  # อุณหภูมิ หน่วยองศาเซลเซียส
            "rain_mm": values["rain"],  # ปริมาณฝน หน่วยมิลลิเมตร
            "rain_probability_percent": values["precipitation_probability"],  # โอกาสเกิดฝน หน่วยเปอร์เซ็นต์
            "snowfall_cm": values["snowfall"],  # ปริมาณหิมะ หน่วยเซนติเมตร
            "wind_speed_kmh": values["wind_speed_10m"],  # ความเร็วลม หน่วยกิโลเมตรต่อชั่วโมง
            "wind_direction_degrees": values["wind_direction_10m"],  # ทิศทางลม หน่วยองศา
            "visibility_m": values["visibility"],  # ทัศนวิสัย หน่วยเมตร
            "weather_code": values["weather_code"],  # รหัสสภาพอากาศ
        }  # จบข้อมูลของชั่วโมงนี้
        records.append(record)  # เพิ่มข้อมูลชั่วโมงนี้เข้าในผลลัพธ์ทั้งหมด

    return records  # ส่งข้อมูลพยากรณ์ทุกชั่วโมงกลับไปให้ผู้เรียก


if __name__ == "__main__":  # ส่วนนี้ทำงานเมื่อสั่งรันไฟล์นี้โดยตรง
    current_weather = fetch_current_weather(13.7563, 100.5018)  # ดึงอากาศปัจจุบันของพิกัดตัวอย่างกรุงเทพฯ
    forecast = fetch_weather_forecast(13.7563, 100.5018)  # ดึงพยากรณ์รายชั่วโมงของพิกัดเดียวกัน
    now = datetime.now(timezone.utc)  # ดูเวลา UTC ขณะนี้
    future = [record for record in forecast if datetime.fromisoformat(record["valid_at"]) >= now]  # เลือกชั่วโมงอนาคต
    preview = {  # เตรียมผลสาธิตที่อ่านได้โดยไม่พิมพ์ทุกชั่วโมง
        "current_weather": current_weather,  # ข้อมูลอากาศใกล้เวลาปัจจุบัน
        "forecast_hours_available": len(future),  # จำนวนชั่วโมงอนาคตที่ฟังก์ชันคืนให้
        "next_hour_forecast": future[0] if future else None,  # ตัวอย่างพยากรณ์ชั่วโมงถัดไป
    }  # จบผลสาธิต
    print(json.dumps(preview, ensure_ascii=False, indent=2))  # แสดง JSON ให้อ่านง่าย
