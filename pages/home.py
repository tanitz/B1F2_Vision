"""
Home Page - Dashboard with camera views
"""
import flet as ft
from config import theme

def create_home_page():
    """สร้างหน้า Home"""

    # ── State ──────────────────────────────────────────────────────────────
    is_running = {"value": False}

    # ── OK/NG indicator ────────────────────────────────────────────────────
    ok_ng_label = ft.Text("OK/NG", size=16, weight=ft.FontWeight.BOLD, color="#ffffff")
    ok_ng_box = ft.Container(
        content=ok_ng_label,
        border_radius=4,
        padding=ft.padding.symmetric(horizontal=16, vertical=8),
        bgcolor="#888888",
        width=100,
        height=50,
        alignment=ft.Alignment(0, 0),
    )

    # ── Model dropdown ────────────────────────────────────────────────────
    model_dropdown = ft.Dropdown(
        options=[
            ft.dropdown.Option("Model A"),
            ft.dropdown.Option("Model B"),
            ft.dropdown.Option("Model C"),
        ],
        value="Model A",
        width=150,
        text_size=13,
        content_padding=ft.padding.only(left=10, right=0, top=4, bottom=4),
        border_color="#cccccc",
        border_radius=4,
    )

    # ── Start/Stop button ──────────────────────────────────────────────────
    start_btn = ft.ElevatedButton(
        "Start",
        width=90,
        height=40,
        style=ft.ButtonStyle(
            bgcolor={"": "#2196f3"},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )

    def toggle_start(e):
        is_running["value"] = not is_running["value"]
        if is_running["value"]:
            start_btn.text = "Stop"
            start_btn.style.bgcolor = {"": "#f44336"}
            ok_ng_label.value = "OK"
            ok_ng_box.bgcolor = theme.ACCENT_GREEN
        else:
            start_btn.text = "Start"
            start_btn.style.bgcolor = {"": "#2196f3"}
            ok_ng_label.value = "OK/NG"
            ok_ng_box.bgcolor = "#888888"
        e.page.update()

    start_btn.on_click = toggle_start

    # ── Image box helper ───────────────────────────────────────────────────
    def img_box(label="IMG", expand=False, width=None, height=None):
        return ft.Container(
            content=ft.Text(label, color="#2196f3", weight=ft.FontWeight.BOLD, size=14),
            border=ft.border.all(1, "#aaaaaa"),
            border_radius=4,
            alignment=ft.Alignment(0, 0),
            bgcolor="#ffffff",
            expand=expand,
            width=width,
            height=height,
        )

    # ── Right column: OK/NG (fixed) + scrollable small images ─────────────
    ok_ng_box.width = 130
    ok_ng_box.height = 75

    scroll_imgs = ft.Column(
        [img_box(width=130, height=75) for _ in range(10)],
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    right_col = ft.Column(
        [ok_ng_box, scroll_imgs],
        spacing=6,
        expand=True,
    )

    # ── Layout ────────────────────────────────────────────────────────────
    return ft.Container(
        content=ft.Column(
            [
                # Header row
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("DASHBOARD", size=22, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    ft.Container(expand=True),
                                    model_dropdown,
                                    start_btn,
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(color=ft.Colors.GREY_400, height=1, thickness=1),
                        ],
                        spacing=4,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                ),

                # Image grid: center big + right column (OK/NG + small imgs)
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(content=img_box(label="IMG", expand=True), expand=9),
                            ft.Container(content=right_col, expand=1),
                        ],
                        spacing=6,
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    padding=ft.padding.only(left=12, right=12, bottom=12, top=8),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )

