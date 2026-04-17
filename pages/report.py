"""
Report Page
"""
import flet as ft
from config import theme

def create_report_page():
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("REPORT", size=22, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    ft.Container(expand=True),
                                ],
                                height=48,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(color=ft.Colors.GREY_400, height=1, thickness=1),
                        ],
                        spacing=4,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                ),
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )
