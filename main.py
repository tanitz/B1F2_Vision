"""
O-Ring Quality Inspection Dashboard
โครงสร้างแบบมืออาชีพ - แยกไฟล์ตามหน้าที่
"""
import flet as ft
from config import theme
from components.sidebar import Sidebar
from pages.home import create_home_page
from pages.report import create_report_page
from pages.settings import create_settings_page


def main(page: ft.Page):
    """Main application"""
    # ตั้งค่าหน้าต่าง - เต็มจอไม่มี title bar
    page.title = "O-Ring Quality Dashboard"
    page.bgcolor = "#ffffff"
    page.padding = 0
    page.spacing = 0
    page.window.maximized = True
    page.window.title_bar_hidden = True
    page.window.frameless = True
    
    # Content area
    content_area = ft.Container(expand=True, bgcolor="#ffffff")
    
    # หน้าทั้งหมด
    pages = [
        create_home_page,
        create_report_page,
        create_settings_page,
    ]
    
    def on_menu_change(index: int):
        """เปลี่ยนหน้าเมื่อคลิกเมนู"""
        if 0 <= index < len(pages):
            content_area.content = pages[index]()
            page.update()
    
    # สร้าง Sidebar
    sidebar = Sidebar(page, on_menu_change)
    
    # Layout หลัก
    page.add(
        ft.Row(
            [
                sidebar.build(),
                content_area,
            ],
            spacing=0,
            expand=True,
        )
    )
    
    # แสดงหน้า Home เป็นค่าเริ่มต้น
    on_menu_change(0)


if __name__ == "__main__":
    ft.run(main)
