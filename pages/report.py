"""
Report Page - แสดงสถิติผลการตรวจสอบ
"""
import flet as ft
from config import theme

def create_report_page():
    """สร้างหน้า Report พร้อมสถิติ OK/NG/NA/Total"""
    
    # สถิติแต่ละประเภท
    stats = [
        {"label": "OK", "value": "90", "color": theme.ACCENT_GREEN},
        {"label": "NG", "value": "11", "color": theme.ACCENT_RED},
        {"label": "NA", "value": "2", "color": theme.ACCENT_ORANGE},
        {"label": "Total", "value": "103", "color": theme.ACCENT_BLUE},
    ]
    
    # สร้างการ์ดสถิติ
    stat_cards = []
    for stat in stats:
        card = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        stat["label"],
                        size=18,
                        color=theme.TEXT_SECONDARY,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Text(
                        stat["value"],
                        size=48,
                        color=stat["color"],
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            **theme.get_stat_card_style(stat["color"]),
            expand=True,
        )
        stat_cards.append(card)
    
    return ft.Container(
        content=ft.Column(
            [
                # Header
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        "PROGRESS REPORT",
                                        size=28,
                                        weight=ft.FontWeight.BOLD,
                                        color=theme.TEXT_PRIMARY,
                                    ),
                                    ft.Container(expand=True),
                                    ft.Text(
                                        "OK:90  NG:11  NA:2  Total:103",
                                        size=14,
                                        color=theme.TEXT_SECONDARY,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Divider(color=ft.Colors.GREY_300, height=20),
                        ],
                    ),
                    padding=20,
                ),
                
                # Content - Stat Cards
                ft.Container(
                    content=ft.Row(
                        stat_cards,
                        spacing=16,
                    ),
                    padding=20,
                    expand=True,
                ),
            ],
            spacing=0,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )
