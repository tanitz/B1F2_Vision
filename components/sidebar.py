"""
Sidebar Navigation Component
"""
import flet as ft
from config import theme

TAB_HEIGHT = 210  # ความสูงคงที่ของแต่ละ tab

class Sidebar:
    """เมนูแนวตั้งด้านซ้าย"""

    def __init__(self, page: ft.Page, on_menu_change):
        self.page = page
        self.on_menu_change = on_menu_change
        self.selected_index = 0
        self.nav_buttons = []

        self.menu_items = [
            {"label": "HOME",    "index": 0},
            {"label": "REPORT",  "index": 1},
            {"label": "SETTINGS", "index": 2},
            {"label": "EXIT",    "index": 3},
        ]

    def create_nav_button(self, item):
        is_selected = self.selected_index == item["index"]

        async def on_click(e):
            if item["index"] == 3:
                await self.page.window.destroy()
                return
            self.selected_index = item["index"]
            for i, btn in enumerate(self.nav_buttons):
                active = i == self.selected_index
                btn.bgcolor = theme.SIDEBAR_ITEM_ACTIVE if active else theme.SIDEBAR_COLOR
                btn.content.color = "#ffffff" if active else "#555555"
            self.page.update()
            self.on_menu_change(item["index"])

        btn = ft.Container(
            content=ft.Text(
                item["label"],
                size=12,
                weight=ft.FontWeight.BOLD,
                color="#ffffff" if is_selected else "#555555",
                text_align=ft.TextAlign.CENTER,
                no_wrap=True,
                width=TAB_HEIGHT,
                rotate=ft.Rotate(angle=-1.5708, alignment=ft.Alignment(0, 0)),
                overflow=ft.TextOverflow.VISIBLE,
            ),
            width=theme.SIDEBAR_WIDTH,
            height=TAB_HEIGHT,
            clip_behavior=ft.ClipBehavior.NONE,
            alignment=ft.Alignment(0, 0),
            bgcolor=theme.SIDEBAR_ITEM_ACTIVE if is_selected else theme.SIDEBAR_COLOR,
            border=ft.border.only(bottom=ft.BorderSide(1, "#cccccc")),
            on_click=on_click,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )
        return btn

    def build(self):
        self.nav_buttons = [self.create_nav_button(item) for item in self.menu_items]

        return ft.Container(
            content=ft.Column(
                self.nav_buttons,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=theme.SIDEBAR_WIDTH,
            bgcolor=theme.SIDEBAR_COLOR,
            border=ft.border.only(right=ft.BorderSide(1, "#cccccc")),
        )
