"""
Home Page
"""
import flet as ft
from config import theme

def create_home_page():
    """สร้างหน้า Home"""
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "DASHBOARD",
                                size=32,
                                weight=ft.FontWeight.BOLD,
                                color=theme.TEXT_PRIMARY,
                            ),
                            ft.Divider(color=ft.Colors.GREY_300, height=20),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                        spacing=-10,
                    ),
                    padding=15,
                    expand=True,
                ),
            ],
            spacing=0,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )
