# Quality Inspection Dashboard

แอปพลิเคชันตรวจสอบคุณภาพ O-Ring พร้อมระบบรายงานและตั้งค่า

## โครงสร้างโปรเจค

```
B1F2/
├── main.py                 # ไฟล์หลัก - เริ่มต้นแอป
├── run.bat                 # ดับเบิลคลิกเพื่อรันแอป
│
├── config/                 # การตั้งค่าระบบ
│   ├── __init__.py
│   └── theme.py           # ธีมสี และสไตล์ตามรูป Dashboard
│
├── pages/                  # หน้าต่างๆ ของแอป
│   ├── __init__.py
│   ├── home.py            # หน้าหลัก
│   ├── report.py          # หน้ารายงาน (OK/NG/NA/Total)
│   └── settings.py        # หน้าตั้งค่า (Camera, Threshold)
│
└── components/             # ส่วนประกอบที่ใช้ซ้ำ
    ├── __init__.py
    └── sidebar.py         # เมนูด้านซ้าย

```

## วิธีใช้งาน

### 1. รันด้วย Batch File (ง่ายที่สุด)

ดับเบิลคลิก `run.bat`

### 2. รันด้วย Command Line

```cmd
cd e:\99IS\B1F2
.venv\Scripts\activate.bat
python main.py
```

## เมนู

- 🏠 **HOME** - หน้าหลักต้อนรับ
- 📊 **REPORT** - สถิติผลการตรวจสอบ (OK: 90, NG: 11, NA: 2, Total: 103)
- ⚙️ **SETTING** - ตั้งค่ากล้องและเกณฑ์การตรวจจับ
- 🚪 **EXIT** - ปิดโปรแกรม

## สีธีม

- **พื้นหลังหลัก** - สีม่วงอ่อน (#9b8ec9) ตามในรูป
- **Sidebar** - สีเข้ม (#2e2847)
- **การ์ด** - พื้นขาวสะอาดตา
- **สีสถิติ** - เขียว (OK), แดง (NG), ส้ม (NA), น้ำเงิน (Total)

## เทคโนโลยี

- **Flet** v0.84.0 - Python GUI Framework
- **Structure** - แยกไฟล์ตามหน้าที่ (Modular Design)

---

สร้างด้วย ❤️ โดยใช้ Flet Framework
