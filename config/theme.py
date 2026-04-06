"""
Theme configuration - สีและสไตล์ตามในรูป Dashboard
"""
import flet as ft

# Main Colors - พื้นขาว Tab เทา/น้ำเงินตามในรูป
BG_COLOR = "#ffffff"  # สีพื้นหลังขาว
SIDEBAR_COLOR = "#eeeeee"  # สีเมนูข้างเทาอ่อน
CARD_BG = "#ffffff"  # การ์ดพื้นขาว
HEADER_BG = "#e0e0e0"  # หัวข้อสีเทา

# Text Colors
TEXT_PRIMARY = "#1a1a1a"
TEXT_SECONDARY = "#666666"
TEXT_ON_DARK = "#1a1a1a"
TEXT_ON_ACTIVE = "#ffffff"

# Accent Colors
ACCENT_GREEN = "#4caf50"  # OK
ACCENT_RED = "#f44336"    # NG
ACCENT_ORANGE = "#ff9800"  # NA
ACCENT_BLUE = "#2196f3"   # Total

# Sidebar
SIDEBAR_WIDTH = 50
SIDEBAR_ITEM_NORMAL = "#9e9e9e"  # Tab ปกติสีเทา
SIDEBAR_ITEM_ACTIVE = "#2196f3"  # Tab เลือกสีน้ำเงิน
SIDEBAR_ITEM_HOVER = "#bdbdbd"  # Hover สีเทาอ่อน

def get_card_style():
    """สไตล์การ์ดมาตรฐาน"""
    return {
        "bgcolor": CARD_BG,
        "border_radius": 12,
        "padding": 20,
        "shadow": ft.BoxShadow(
            spread_radius=1,
            blur_radius=10,
            color="#00000020",
            offset=ft.Offset(0, 2)
        )
    }

def get_stat_card_style(color):
    """สไตล์การ์ดสถิติ"""
    return {
        "bgcolor": CARD_BG,
        "border_radius": 12,
        "padding": 30,
        "border": ft.border.all(2, color),
        "shadow": ft.BoxShadow(
            spread_radius=1,
            blur_radius=8,
            color="#00000015",
            offset=ft.Offset(0, 2)
        )
    }
