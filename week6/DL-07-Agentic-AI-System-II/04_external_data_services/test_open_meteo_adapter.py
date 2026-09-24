import importlib.util  # ใช้โหลดไฟล์ adapter ในโฟลเดอร์ที่ชื่อขึ้นต้นด้วยตัวเลข
import io  # ใช้จำลองข้อมูลที่ตอบกลับจาก API
import json  # ใช้แปลงข้อมูลทดสอบเป็น JSON
import socket  # ใช้จำลองการหมดเวลารอ
import unittest  # ใช้เขียนและรันชุดทดสอบมาตรฐานของ Python
from pathlib import Path  # ใช้หาไฟล์ adapter ที่อยู่ข้างไฟล์ทดสอบ
from unittest.mock import patch  # ใช้แทนการเรียกเครือข่ายจริง
from urllib.error import HTTPError  # ใช้จำลอง HTTP error


MODULE_PATH = Path(__file__).with_name("open_meteo_adapter.py")  # ที่อยู่ไฟล์ที่ต้องการทดสอบ
SPEC = importlib.util.spec_from_file_location("open_meteo_adapter", MODULE_PATH)  # เตรียมข้อมูลการโหลดไฟล์
adapter = importlib.util.module_from_spec(SPEC)  # สร้างโมดูลในหน่วยความจำ
SPEC.loader.exec_module(adapter)  # โหลดโค้ดโดยไม่รันส่วน __main__


def api_response(payload: dict) -> io.BytesIO:  # สร้างคำตอบ API จำลอง
    return io.BytesIO(json.dumps(payload).encode("utf-8"))  # คืนข้อมูล JSON ในรูป byte stream


class OpenMeteoAdapterTests(unittest.TestCase):  # รวมการทดสอบ adapter
    def setUp(self) -> None:  # เตรียมข้อมูลตัวอย่างใหม่ก่อนแต่ละ test
        self.current = {"time": "2026-09-19T05:45", **{field: 1 for field in adapter.HOURLY_FIELDS}}  # ข้อมูล current ครบ
        self.hourly = {"time": ["2026-09-19T06:00"], **{field: [1] for field in adapter.HOURLY_FIELDS}}  # ข้อมูลหนึ่งชั่วโมง

    def test_current_complete(self) -> None:  # ข้อมูลปัจจุบันครบต้องแปลงได้
        with patch.object(adapter, "urlopen", return_value=api_response({"current": self.current})):  # ไม่เรียก API จริง
            record = adapter.fetch_current_weather(13.7563, 100.5018)  # เรียกฟังก์ชันที่ทดสอบ
        self.assertEqual(record["temperature_c"], 1)  # ใช้ค่าจาก API จริงใน fixture
        self.assertEqual(record["quality_flags"], [])  # ไม่มีข้อมูลขาด
        self.assertEqual(record["valid_at"], "2026-09-19T05:45:00+00:00")  # เวลาถูกระบุเป็น UTC

    def test_current_optional_field_missing(self) -> None:  # ฟิลด์ที่ไม่ใช่อุณหภูมิขาดต้องถูกแจ้ง
        del self.current["visibility"]  # จำลอง API ไม่ส่งทัศนวิสัย
        with patch.object(adapter, "urlopen", return_value=api_response({"current": self.current})):  # ไม่เรียก API จริง
            record = adapter.fetch_current_weather(13.7563, 100.5018)  # แปลงคำตอบ
        self.assertIsNone(record["visibility_m"])  # ไม่เดาค่าทัศนวิสัย
        self.assertIn("incomplete", record["quality_flags"])  # แจ้งข้อมูลไม่ครบ

    def test_current_temperature_missing(self) -> None:  # ข้อมูลหลักขาดต้องไม่สร้าง record ปลอม
        del self.current["temperature_2m"]  # จำลองอุณหภูมิหายไป
        with patch.object(adapter, "urlopen", return_value=api_response({"current": self.current})):  # ไม่เรียก API จริง
            with self.assertRaises(adapter.WeatherDataError):  # ต้องแจ้งข้อมูลผิดรูปแบบ
                adapter.fetch_current_weather(13.7563, 100.5018)  # ลองแปลงคำตอบ

    def test_hourly_short_field_list(self) -> None:  # รายการค่าที่สั้นกว่ารายการเวลาต้องไม่พัง
        self.hourly["rain"] = []  # จำลองฝนไม่มีค่าในชั่วโมงนี้
        with patch.object(adapter, "urlopen", return_value=api_response({"hourly": self.hourly})):  # ไม่เรียก API จริง
            record = adapter.fetch_weather_forecast(13.7563, 100.5018)[0]  # อ่านชั่วโมงแรก
        self.assertIsNone(record["rain_mm"])  # ไม่เดาปริมาณฝน
        self.assertIn("incomplete", record["quality_flags"])  # แจ้งว่าข้อมูลไม่ครบ

    def test_hourly_time_missing(self) -> None:  # ไม่มีเวลาแล้วใช้พยากรณ์ไม่ได้
        with patch.object(adapter, "urlopen", return_value=api_response({"hourly": {}})):  # จำลองคำตอบผิด schema
            with self.assertRaises(adapter.WeatherDataError):  # ต้องแจ้งข้อผิดพลาด
                adapter.fetch_weather_forecast(13.7563, 100.5018)  # ลองอ่านพยากรณ์

    def test_non_numeric_weather_rejected(self) -> None:  # ตัวเลขที่กลายเป็นข้อความต้องถูกปฏิเสธ
        self.current["wind_speed_10m"] = "fast"  # จำลองข้อมูลผิดชนิด
        with patch.object(adapter, "urlopen", return_value=api_response({"current": self.current})):  # ไม่เรียก API จริง
            with self.assertRaises(adapter.WeatherDataError):  # ต้องไม่ส่งข้อความต่อให้โมดูล 05
                adapter.fetch_current_weather(13.7563, 100.5018)  # ลองแปลงคำตอบ

    def test_http_error(self) -> None:  # HTTP error ต้องแยกจากข้อมูลอากาศ
        error = HTTPError("https://example.test", 503, "unavailable", {}, None)  # จำลอง provider ล้มเหลว
        with patch.object(adapter, "urlopen", side_effect=error):  # ไม่เรียก API จริง
            with self.assertRaises(adapter.WeatherProviderError):  # ต้องแจ้งปัญหา provider
                adapter.fetch_current_weather(13.7563, 100.5018)  # ลองเรียกข้อมูล

    def test_timeout(self) -> None:  # timeout ต้องไม่กลายเป็นข้อมูลปลอม
        with patch.object(adapter, "urlopen", side_effect=socket.timeout()):  # จำลองการหมดเวลารอ
            with self.assertRaises(adapter.WeatherProviderError):  # ต้องแจ้งปัญหา provider
                adapter.fetch_current_weather(13.7563, 100.5018)  # ลองเรียกข้อมูล

    def test_invalid_json(self) -> None:  # คำตอบที่ไม่ใช่ JSON ต้องถูกปฏิเสธ
        with patch.object(adapter, "urlopen", return_value=io.BytesIO(b"not-json")):  # จำลองเนื้อหาผิดรูปแบบ
            with self.assertRaises(adapter.WeatherDataError):  # ต้องแจ้งปัญหาข้อมูล
                adapter.fetch_current_weather(13.7563, 100.5018)  # ลองอ่านคำตอบ

    def test_invalid_coordinates(self) -> None:  # พิกัดนอกโลกต้องไม่เรียก API
        with patch.object(adapter, "urlopen") as call:  # จับการเรียกเครือข่าย
            with self.assertRaises(ValueError):  # ต้องแจ้งพิกัดผิด
                adapter.fetch_current_weather(91, 100)  # ส่งละติจูดเกินขอบเขต
        call.assert_not_called()  # ยืนยันว่าไม่ได้เรียก API


if __name__ == "__main__":  # ทำงานเมื่อรันไฟล์ทดสอบโดยตรง
    unittest.main()  # เรียกชุดทดสอบทั้งหมด
