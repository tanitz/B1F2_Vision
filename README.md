# Quality Inspection Dashboard

ระบบตรวจสอบคุณภาพชิ้นงานด้วยกล้อง HikRobot + Feature Point Matching

---

## ข้อกำหนดระบบ

- Windows 10/11 (64-bit)
- Python 3.11+
- HikRobot MVS SDK (สำหรับกล้อง)

---

## ขั้นตอนติดตั้งเครื่องใหม่

### 1. ติดตั้ง HikRobot MVS SDK (บังคับ)

ดาวน์โหลดและติดตั้ง MVS จาก HikRobot ให้ SDK อยู่ที่ path นี้:

```
C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport
```

> ถ้าติดตั้ง SDK ที่ path อื่น ให้แก้ `camera_manager.py` บรรทัด 14

---

### 2. คัดลอกโฟลเดอร์ B1F2 ไปเครื่องใหม่

```
คัดลอกทั้งโฟลเดอร์ B1F2\ ไปวางที่เครื่องใหม่
```

---

### 3. สร้าง Virtual Environment และติดตั้ง Packages

เปิด Command Prompt ใน folder B1F2 แล้วรัน:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

> ถ้า pip ช้าให้เพิ่ม `-i https://pypi.org/simple`

---

### 4. ตั้งค่า IP กล้อง

เปิดไฟล์ `config\camera.json` และแก้ไข IP ให้ตรงกับกล้องในเครือข่าย:

```json
{
  "camera_ip": "192.168.1.64"
}
```

---

### 5. รันโปรแกรม

**วิธีที่ 1** — ดับเบิลคลิก `run.bat`

**วิธีที่ 2** — Command Line:

```cmd
.venv\Scripts\activate.bat
python main.py
```

**วิธีที่ 3** — Web mode (เปิดจาก browser ได้):

```cmd
run_web.bat
```

---

## โครงสร้างโปรเจค

```
B1F2/
├── main.py                 # ไฟล์หลัก — เริ่มต้นแอป
├── camera_manager.py       # จัดการกล้อง HikRobot (MVS SDK)
├── fpm_matching.py         # Feature Point Matching engine
├── requirements.txt        # Python packages
├── run.bat                 # รัน desktop app
├── run_web.bat             # รัน web mode
│
├── config/                 # การตั้งค่าระบบ
│   ├── camera.json         # IP กล้อง
│   └── theme.py            # สีและสไตล์
│
├── pages/                  # หน้าต่างๆ
│   ├── home.py             # Dashboard หลัก + ตรวจสอบอัตโนมัติ
│   ├── report.py           # รายงานผล OK/NG
│   └── settings.py         # สร้าง Model + ตั้งค่ากล้อง
│
├── components/
│   └── sidebar.py          # เมนูด้านซ้าย
│
├── model/                  # โมเดลตรวจสอบ (สร้างผ่านหน้า Settings)
├── image/                  # ภาพทดสอบ
├── results/                # ผลการตรวจ CSV + ภาพ
└── bin/                    # ไฟล์ที่ไม่ได้ใช้งานแล้ว
```

---

## การใช้งาน

| หน้า | ฟังก์ชัน |
|------|----------|
| **Home** | กด Start → กล้องเชื่อมต่อและตรวจสอบอัตโนมัติทุก frame |
| **Report** | ดูสถิติ OK/NG รายวัน |
| **Settings** | สร้าง Model ใหม่, ตั้งค่า IO Trigger กล้อง |

---

## Dependencies หลัก

| Package | Version | ใช้สำหรับ |
|---------|---------|-----------|
| flet | 0.84.0 | UI Framework |
| opencv-python | 4.x | ประมวลผลภาพ |
| numpy | 2.x | จัดการ array |
| pillow | 12.x | วาด Text ภาษาไทย |

---

## หมายเหตุ

- Font ภาษาไทย `THSarabunNew.ttf` — ถ้าไม่มีจะใช้ Tahoma แทน (ติดตั้งได้จาก https://www.f0nt.com/release/th-sarabun-new/)
- กล้อง: HikRobot GigE (รุ่น MV-CS050-20GC หรือเข้ากันได้)
- เชื่อมต่อกล้องผ่าน GigE — ต้องตั้ง IP ของ NIC เครื่องให้อยู่ subnet เดียวกับกล้อง
