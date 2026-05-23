"""
Report Page — card layout with saved result images
"""
import base64
import csv
import os
import cv2
import flet as ft
from config import theme

import calendar
import datetime

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
IMAGES_DIR  = os.path.join(BASE_DIR, "results", "images")


def _csv_path(date_str: str | None = None) -> str:
    if not date_str:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    return os.path.join(RESULTS_DIR, f"{date_str}.csv")


def _read_csv(date_str: str | None = None) -> list[dict]:
    path = _csv_path(date_str)
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_thumb_cache: dict[str, str | None] = {}

def _img_b64(img_id: str, w=240, h=160) -> str | None:
    if img_id in _thumb_cache:
        return _thumb_cache[img_id]
    path = os.path.join(IMAGES_DIR, f"{img_id}.jpg")
    if not os.path.isfile(path):
        _thumb_cache[img_id] = None
        return None
    img = cv2.imread(path)
    if img is None:
        _thumb_cache[img_id] = None
        return None
    ih, iw = img.shape[:2]
    scale = min(w / iw, h / ih, 1.0)
    img = cv2.resize(img, (int(iw * scale), int(ih * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    result = base64.b64encode(buf).decode()
    _thumb_cache[img_id] = result
    return result


def _badge(text, color, bg):
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=bg, border_radius=4,
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
    )


def _build_card(test_rows: list[dict]) -> ft.Container:
    r0      = test_rows[0]
    overall = r0.get("overall_result", "")
    img_id  = r0.get("result_image_id", "")

    is_pass    = overall == "PASS"
    border_clr = theme.ACCENT_GREEN if is_pass else theme.ACCENT_RED
    bg_clr     = "#f1f8e9" if is_pass else "#fce4ec"
    badge      = _badge(overall, "#ffffff", border_clr)

    # ── Result image thumbnail ────────────────────────────────────────────────
    b64 = _img_b64(img_id) if img_id else None
    if b64:
        thumb = ft.Image(src=f"data:image/jpeg;base64,{b64}", width=240, height=160,
                         fit="contain", border_radius=ft.BorderRadius.all(4))
    else:
        thumb = ft.Container(
            width=240, height=160, bgcolor="#e0e0e0", border_radius=4,
            alignment=ft.Alignment(0, 0),
            content=ft.Text("No Image", size=11, color="#9e9e9e"),
        )

    # ── Inspection rows ───────────────────────────────────────────────────────
    insp_rows = []
    for row in test_rows:
        res   = row.get("result", "")
        score = row.get("score", "")
        clr   = theme.ACCENT_GREEN if res == "PASS" else theme.ACCENT_RED
        insp_rows.append(
            ft.Row(
                [
                    ft.Text(row.get("inspection_name", ""), size=11,
                            expand=True, color=theme.TEXT_PRIMARY),
                    ft.Container(
                        content=ft.Text(res, size=10, weight=ft.FontWeight.BOLD,
                                        color="#ffffff", no_wrap=True),
                        bgcolor=clr, border_radius=3,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                        width=80, alignment=ft.Alignment(0, 0),
                    ),
                    ft.Text(score, size=11, width=54,
                            text_align=ft.TextAlign.RIGHT, color=theme.TEXT_SECONDARY),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    info_col = ft.Column(
        [
            ft.Row([
                ft.Text(r0.get("timestamp", ""), size=11, color=theme.TEXT_SECONDARY),
                ft.Container(expand=True),
                badge,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(f"Model: {r0.get('model', '')}", size=11, color=theme.TEXT_SECONDARY),
            ft.Divider(height=1, color="#dddddd"),
            ft.Row([
                ft.Text("Inspection", size=11, weight=ft.FontWeight.BOLD,
                        expand=True, color=theme.TEXT_SECONDARY),
                ft.Text("Result", size=11, weight=ft.FontWeight.BOLD,
                        width=80, text_align=ft.TextAlign.CENTER, color=theme.TEXT_SECONDARY),
                ft.Text("Score", size=11, weight=ft.FontWeight.BOLD,
                        width=54, text_align=ft.TextAlign.RIGHT, color=theme.TEXT_SECONDARY),
            ], spacing=6),
            *insp_rows,
        ],
        spacing=6,
        expand=True,
    )

    return ft.Container(
        content=ft.Row(
            [thumb, info_col],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        bgcolor=bg_clr,
        border=ft.Border.all(1.5, border_clr),
        border_radius=8,
        padding=ft.Padding.all(12),
        shadow=ft.BoxShadow(blur_radius=4, color="#00000012", offset=ft.Offset(0, 2)),
    )


def create_report_page(page=None):
    all_rows = _read_csv()  # defaults to today

    # ── Stat cards ────────────────────────────────────────────────────────────
    stat_total = ft.Text("–", size=28, weight=ft.FontWeight.BOLD, color=theme.ACCENT_BLUE)
    stat_pass  = ft.Text("–", size=28, weight=ft.FontWeight.BOLD, color=theme.ACCENT_GREEN)
    stat_fail  = ft.Text("–", size=28, weight=ft.FontWeight.BOLD, color=theme.ACCENT_RED)
    stat_rate  = ft.Text("–", size=28, weight=ft.FontWeight.BOLD, color="#ff9800")

    def _stat_card(label, val_widget, color):
        return ft.Container(
            content=ft.Column(
                [val_widget, ft.Text(label, size=11, color=theme.TEXT_SECONDARY)],
                spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=1, height=80, bgcolor="#ffffff",
            border_radius=8, border=ft.Border.all(2, color),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            alignment=ft.Alignment(0, 0),
            shadow=ft.BoxShadow(blur_radius=6, color="#00000015", offset=ft.Offset(0, 2)),
        )

    stat_row = ft.Row([
        _stat_card("Total", stat_total, theme.ACCENT_BLUE),
        _stat_card("PASS",        stat_pass,  theme.ACCENT_GREEN),
        _stat_card("FAIL",        stat_fail,  theme.ACCENT_RED),
        _stat_card("Pass Rate",   stat_rate,  "#ff9800"),
    ], spacing=12)

    # ── Filters ───────────────────────────────────────────────────────────────
    filter_model = ft.Dropdown(
        label="Model", width=180, text_size=12, value="All",
        options=[ft.dropdown.Option("All")], border_radius=6,
    )
    filter_result = ft.Dropdown(
        label="Overall", width=130, text_size=12, value="All",
        options=[ft.dropdown.Option(x) for x in ("All", "PASS", "FAIL")],
        border_radius=6,
    )
    _date_text  = ft.Text("YYYY-MM-DD", size=12, color="#aaaaaa", no_wrap=True)
    _date_label = ft.Text("Date", size=10, color="#888888")
    filter_date = ft.Container(
        content=ft.Column([_date_label, _date_text], spacing=0,
                          alignment=ft.MainAxisAlignment.CENTER),
        width=150, height=48,
        border=ft.Border.all(1, "#aaaaaa"),
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        bgcolor="#ffffff",
        on_click=lambda e: _open_cal(e),
        ink=True,
    )

    # ── Custom web-style calendar popup ──────────────────────────────────────
    _today = datetime.date.today()
    _cal_state  = {"year": _today.year, "month": _today.month, "selected": None, "date_str": ""}
    _refresh_seq = {"n": 0}

    cal_month_label = ft.Text("", size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    cal_grid        = ft.Column(spacing=1)

    def _build_cal_grid():
        year, month = _cal_state["year"], _cal_state["month"]
        cal_month_label.value = f"{calendar.month_name[month]} {year}"
        rows = [
            ft.Row(
                [ft.Text(d, size=10, width=32, text_align=ft.TextAlign.CENTER, color="#aaaaaa")
                 for d in ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]],
                spacing=2,
            )
        ]
        for week in calendar.Calendar(6).monthdayscalendar(year, month):
            cells = []
            for day in week:
                if day == 0:
                    cells.append(ft.Container(width=32, height=30))
                else:
                    d_obj      = datetime.date(year, month, day)
                    is_sel     = _cal_state["selected"] == d_obj
                    is_today   = d_obj == datetime.date.today()
                    cells.append(ft.Container(
                        content=ft.Text(
                            str(day), size=12, text_align=ft.TextAlign.CENTER,
                            color="#ffffff" if is_sel else ("#1565c0" if is_today else "#333333"),
                        ),
                        width=32, height=30, border_radius=4,
                        bgcolor="#1976d2" if is_sel else ("#e3f2fd" if is_today else None),
                        alignment=ft.Alignment(0, 0), ink=True,
                        on_click=lambda e, d=day: _on_day_click(e, d),
                    ))
            rows.append(ft.Row(cells, spacing=2))
        cal_grid.controls = rows

    def _on_day_click(e, day):
        d = datetime.date(_cal_state["year"], _cal_state["month"], day)
        _cal_state["selected"] = d
        _cal_state["date_str"] = d.strftime("%Y-%m-%d")
        _date_text.value = _cal_state["date_str"]
        _date_text.color = "#333333"
        _cal_dialog.open = False
        e.page.update()
        pg = e.page
        _refresh_seq["n"] += 1
        pg.run_thread(lambda: (refresh(), pg.update()))

    def _prev_month(e):
        y, m = _cal_state["year"], _cal_state["month"]
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        _cal_state["year"], _cal_state["month"] = y, m
        _build_cal_grid()
        e.page.update()

    def _next_month(e):
        y, m = _cal_state["year"], _cal_state["month"]
        m += 1
        if m == 13:
            m, y = 1, y + 1
        _cal_state["year"], _cal_state["month"] = y, m
        _build_cal_grid()
        e.page.update()

    _build_cal_grid()

    _cal_dialog = ft.AlertDialog(
        modal=True,
        bgcolor="#ffffff",
        content_padding=ft.Padding.all(16),
        shape=ft.RoundedRectangleBorder(radius=10),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT,  icon_size=18, on_click=_prev_month),
                        ft.Container(content=cal_month_label, expand=True, alignment=ft.Alignment(0, 0)),
                        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=18, on_click=_next_month),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                cal_grid,
            ],
            tight=True, spacing=6, width=256,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: _close_cal(e)),
        ],
        actions_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
    )

    def _open_cal(e):
        if _cal_dialog not in e.page.overlay:
            e.page.overlay.append(_cal_dialog)
        _build_cal_grid()
        _cal_dialog.open = True
        e.page.update()

    def _close_cal(e):
        _cal_dialog.open = False
        e.page.update()

    def _clear_date(e):
        _cal_state["selected"] = None
        _cal_state["date_str"] = ""
        _date_text.value = "YYYY-MM-DD"
        _date_text.color = "#aaaaaa"
        pg = e.page
        _refresh_seq["n"] += 1
        pg.run_thread(lambda: (refresh(), pg.update()))

    filter_date_row = ft.Row(
        [
            filter_date,
            ft.IconButton(icon=ft.Icons.CLEAR, icon_size=16, tooltip="ล้างวันที่",
                          on_click=_clear_date),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    PAGE_SIZE = 30

    # ── Pagination state ──────────────────────────────────────────────────────
    _view = {"seen": [], "groups": {}, "page": 0}

    # ── Card list ─────────────────────────────────────────────────────────────
    card_list = ft.ListView(spacing=10, expand=True, padding=ft.Padding.only(bottom=8))

    no_data = ft.Container(
        content=ft.Text("No data — run a test to see results here.",
                        size=14, color=theme.TEXT_SECONDARY, italic=True),
        expand=True, alignment=ft.Alignment(0, 0),
    )

    page_label = ft.Text("", size=12, color=theme.TEXT_SECONDARY)
    btn_prev   = ft.IconButton(icon=ft.Icons.CHEVRON_LEFT,  icon_size=18, disabled=True)
    btn_next   = ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=18, disabled=True)

    pagination_row = ft.Row(
        [btn_prev, page_label, btn_next],
        spacing=4,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def _show_page():
        seen   = _view["seen"]
        groups = _view["groups"]
        n      = len(seen)
        pg_n   = _view["page"]
        total_pages = max(1, (n + PAGE_SIZE - 1) // PAGE_SIZE)
        pg_n   = max(0, min(pg_n, total_pages - 1))
        _view["page"] = pg_n

        start = pg_n * PAGE_SIZE
        end   = start + PAGE_SIZE
        card_list.controls = [_build_card(groups[k]) for k in seen[start:end]]
        card_list.visible  = (n > 0)
        no_data.visible    = (n == 0)

        page_label.value   = f"{pg_n + 1} / {total_pages}" if n > 0 else ""
        btn_prev.disabled  = (pg_n == 0)
        btn_next.disabled  = (pg_n >= total_pages - 1)
        pagination_row.visible = (n > 0)

    def _go_prev(e):
        _view["page"] -= 1
        _show_page()
        e.page.update()

    def _go_next(e):
        _view["page"] += 1
        _show_page()
        e.page.update()

    btn_prev.on_click = _go_prev
    btn_next.on_click = _go_next

    def refresh(rows=None):
        nonlocal all_rows
        my_seq = _refresh_seq["n"]

        date_str = _cal_state.get("date_str", "").strip()
        if rows is None:
            rows = _read_csv(date_str or None)

        mdl = filter_model.value or "All"
        res = filter_result.value or "All"

        filtered = [
            r for r in rows
            if (mdl == "All" or r.get("model") == mdl)
            and (res == "All" or r.get("overall_result") == res)
        ]

        # Group by result_image_id — latest first
        seen, groups = [], {}
        for r in reversed(filtered):
            key = r.get("result_image_id", "")
            if key not in groups:
                groups[key] = []
                seen.append(key)
            groups[key].append(r)

        n_total = len(seen)
        n_pass  = sum(1 for k in seen if groups[k][0].get("overall_result") == "PASS")
        n_fail  = n_total - n_pass
        pct     = f"{n_pass / n_total * 100:.1f}%" if n_total else "–"
        all_models = sorted({r["model"] for r in rows})

        if my_seq != _refresh_seq["n"]:
            return

        all_rows = rows
        _view["seen"]   = seen
        _view["groups"] = groups
        _view["page"]   = 0

        stat_total.value = str(n_total)
        stat_pass.value  = str(n_pass)
        stat_fail.value  = str(n_fail)
        stat_rate.value  = pct
        filter_model.options = [ft.dropdown.Option("All")] + [
            ft.dropdown.Option(m) for m in all_models
        ]
        _show_page()

    refresh()

    def on_filter_change(e):
        pg = e.page
        _refresh_seq["n"] += 1
        pg.run_thread(lambda: (refresh(), pg.update()))

    def on_refresh_clicked(e):
        pg = e.page
        _refresh_seq["n"] += 1
        pg.run_thread(lambda: (refresh(), pg.update()))

    filter_model.on_change  = on_filter_change
    filter_result.on_change = on_filter_change

    if page is not None:
        def _on_report_update(_topic, _data):
            _refresh_seq["n"] += 1
            refresh()
            try:
                page.update()
            except Exception:
                pass
        page.pubsub.unsubscribe_topic("report_update")
        page.pubsub.subscribe_topic("report_update", _on_report_update)


    # ── Full-page layout ──────────────────────────────────────────────────────
    return ft.Container(
        content=ft.Column(
            [
                # Header
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("REPORT", size=22, weight=ft.FontWeight.BOLD,
                                    color=theme.TEXT_PRIMARY),
                            ft.Container(expand=True),
                            ft.Button("Refresh", height=36,
                                style=ft.ButtonStyle(
                                    bgcolor={"": theme.ACCENT_BLUE}, color={"": "#ffffff"},
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                                on_click=on_refresh_clicked,
                            ),
                        ], height=48, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Divider(color=ft.Colors.GREY_300, height=1, thickness=1),
                    ], spacing=4),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),

                # Stat cards
                ft.Container(content=stat_row,
                             padding=ft.Padding.only(left=16, right=16, bottom=10)),

                # Filter bar
                ft.Container(
                    content=ft.Row([
                        ft.Text("Filter:", size=13, weight=ft.FontWeight.BOLD,
                                color=theme.TEXT_PRIMARY),
                        filter_model, filter_result, filter_date_row,
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor="#f5f5f5", border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    margin=ft.Margin(left=16, right=16, top=0, bottom=10),
                ),

                # Cards / empty state
                ft.Container(
                    content=ft.Stack([card_list, no_data]),
                    expand=True,
                    padding=ft.Padding.only(left=16, right=16, bottom=0),
                ),

                # Pagination
                ft.Container(
                    content=pagination_row,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                ),
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )
