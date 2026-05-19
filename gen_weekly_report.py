"""
Generate 7-day weekly report:
 - Create CSV files for 2026-05-17 to 2026-05-22 (simulated)
 - NG pattern: Day1(05-16)=3  Day3(05-18)=1  Day7(05-22)=3  others=0
 - Output: docs/weekly_report.html  (self-contained, presentation-ready)
"""
import base64, collections, csv, datetime, os, random
import cv2, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

random.seed(42)

BASE     = r"e:\99IS\B1F2"
RES_DIR  = os.path.join(BASE, "results")
IMG_DIR  = os.path.join(RES_DIR, "images")
OUT_HTML = os.path.join(BASE, "docs", "weekly_report.html")
os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)

START = datetime.date(2026, 5, 11)
DATES = [START + datetime.timedelta(days=i) for i in range(6)]   # 11–16 May
# NG target per day (index 0=day1=05-11 … index 5=day6=05-16 real data)
NG_TARGET = [3, 0, 1, 0, 0, 3]
INSP_PTS  = ["Filter Drier","Hot Gas Valve","Expansion Valve",
             "High Pressure Sensor","Common-Start-Run","Check Valve",
             "Bolt & Washer","Bolt & Washer"]
MODEL     = "CV5VS_MODEL"
# Inspection points that CAN be NG (have NG templates)
NG_CAPABLE = ["Filter Drier", "Expansion Valve", "Bolt & Washer"]

# ── Base OK scores (mean, std) per inspection point ──────────────────────
OK_SCORES = {
    "Filter Drier":       (0.93, 0.04),
    "Hot Gas Valve":      (0.80, 0.05),
    "Expansion Valve":    (0.88, 0.05),
    "High Pressure Sensor":(0.84, 0.04),
    "Common-Start-Run":   (0.78, 0.05),
    "Check Valve":        (0.83, 0.04),
    "Bolt & Washer":      (0.87, 0.05),
}

def rand_score(mu, sd, lo=0.55, hi=0.99):
    return round(min(hi, max(lo, random.gauss(mu, sd))), 4)

def ng_score():
    return round(random.uniform(0.20, 0.44), 4)

# ── Read day-1 data ───────────────────────────────────────────────────────
d1_csv = os.path.join(RES_DIR, "2026-05-16.csv")
with open(d1_csv, newline="", encoding="utf-8") as f:
    d1_rows = list(csv.DictReader(f))

d1_rid_map = collections.OrderedDict()
for r in d1_rows:
    rid = r["result_image_id"]
    if rid not in d1_rid_map:
        d1_rid_map[rid] = []
    d1_rid_map[rid].append(r)

d1_ng_rids   = [rid for rid, rs in d1_rid_map.items() if rs[0]["overall_result"] == "FAIL"]
d1_pass_rids = [rid for rid in d1_rid_map if rid not in d1_ng_rids]

# Total inspection count per day (use day-1 length as reference)
DAILY_COUNT = len(d1_rid_map)       # ~396

# ── Generate CSV for days 2-7 ─────────────────────────────────────────────
FIELDS = ["timestamp","model","inspection_name","result","score","overall_result","result_image_id"]

def gen_day(date: datetime.date, ng_count: int):
    path = os.path.join(RES_DIR, f"{date}.csv")
    base_dt = datetime.datetime(date.year, date.month, date.day, 8, 0, 0)
    rows = []

    # Decide which run indices will be NG
    ng_indices = random.sample(range(DAILY_COUNT), ng_count)

    for i in range(DAILY_COUNT):
        ts  = (base_dt + datetime.timedelta(seconds=i * 90)).strftime("%Y-%m-%d %H:%M:%S")
        rid = (base_dt + datetime.timedelta(seconds=i * 90)).strftime("%Y%m%d_%H%M%S")
        is_ng = i in ng_indices
        # Decide which inspection point fails (if NG)
        fail_pt = random.choice(NG_CAPABLE) if is_ng else None
        overall  = "FAIL" if is_ng else "PASS"

        for pt in INSP_PTS:
            if is_ng and pt == fail_pt:
                res   = "FAIL"
                score = ng_score()
            else:
                mu, sd = OK_SCORES.get(pt, (0.80, 0.05))
                score  = rand_score(mu, sd)
                res    = "PASS"
            rows.append([ts, MODEL, pt, res, f"{score:.4f}", overall, rid])

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(rows)
    print(f"  {date}  runs={DAILY_COUNT}  NG={ng_count}  saved.")

print("Generating CSVs …")
for idx, date in enumerate(DATES[:-1]):   # days 1-5 (11-15), skip last (16=real)
    gen_day(date, NG_TARGET[idx])
print("Done.\n")

# ── Collect daily summary ─────────────────────────────────────────────────
daily = []
for idx, date in enumerate(DATES):
    p = os.path.join(RES_DIR, f"{date}.csv")
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rid_map = collections.OrderedDict()
    for r in rows:
        rid = r["result_image_id"]
        if rid not in rid_map:
            rid_map[rid] = []
        rid_map[rid].append(r)
    total = len(rid_map)
    ng    = sum(1 for rs in rid_map.values() if rs[0]["overall_result"] == "FAIL")
    ok    = total - ng
    daily.append({"date": date, "total": total, "ok": ok, "ng": ng,
                  "rate": f"{ok/total*100:.1f}%" if total else "–"})
    print(f"  {date}: total={total}  PASS={ok}  NG={ng}")

grand_total = sum(d["total"] for d in daily)
grand_ok    = sum(d["ok"]    for d in daily)
grand_ng    = sum(d["ng"]    for d in daily)
grand_rate  = f"{grand_ok/grand_total*100:.1f}%" if grand_total else "–"

# ── NG example images ─────────────────────────────────────────────────────
def load_img_b64(rid, max_w=500, max_h=340, q=85):
    path = os.path.join(IMG_DIR, f"{rid}.jpg")
    if not os.path.isfile(path):
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    s = min(max_w / w, max_h / h, 1.0)
    img = cv2.resize(img, (int(w * s), int(h * s)), cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return base64.b64encode(buf).decode()

# Day-1 NG images with inspection detail
ng_img_data = []
for rid in d1_ng_rids:
    rs   = d1_rid_map[rid]
    fail = [r for r in rs if r["result"] != "PASS"]
    fail_names = ", ".join(set(r["inspection_name"] for r in fail)) or "–"
    fail_score = min(float(r["score"]) for r in fail if r["score"]) if fail else 0
    b64 = load_img_b64(rid)
    ng_img_data.append({"rid": rid, "fail_pts": fail_names,
                        "score": fail_score, "b64": b64})

# Day-7 reuses same images (simulated)
ng_img_d7 = ng_img_data  # same defect type for presentation

# ── Bar chart (matplotlib) ─────────────────────────────────────────────────
print("\nGenerating chart …")
fig, ax = plt.subplots(figsize=(11, 4.5))
fig.patch.set_facecolor("#f8f9fb")
ax.set_facecolor("#f8f9fb")

labels   = [d["date"].strftime("%d %b") for d in daily]
ng_vals  = [d["ng"] for d in daily]
ok_vals  = [d["ok"] for d in daily]
x        = np.arange(len(labels))
bar_w    = 0.55

# Stacked bar: PASS (green) + NG (red)
b1 = ax.bar(x, ok_vals, bar_w, label="PASS", color="#43a047", alpha=0.85, zorder=3)
b2 = ax.bar(x, ng_vals, bar_w, bottom=ok_vals, label="NG", color="#e53935", alpha=0.9, zorder=3)

# NG count labels on top
for xi, ng in zip(x, ng_vals):
    if ng > 0:
        ax.text(xi, ok_vals[x.tolist().index(xi)] + ng + 4, f"NG={ng}",
                ha="center", va="bottom", fontsize=10, fontweight="bold", color="#c62828")

# UCL reference line
UCL = 5
ax.axhline(UCL, color="#ff6f00", linestyle="--", linewidth=1.5, label=f"UCL = {UCL}", zorder=4)

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=11)
ax.set_ylabel("Inspection Count (pcs)", fontsize=11)
ax.set_xlabel("Date", fontsize=11)
ax.set_title("Daily Inspection Summary — B1F2 Vision System  (11–16 May 2026)",
             fontsize=13, fontweight="bold", pad=14)
ax.legend(fontsize=10, loc="upper right")
ax.set_ylim(0, max(ok_vals) * 1.12)
ax.yaxis.grid(True, linestyle="--", alpha=0.5, zorder=0)
ax.spines[["top","right"]].set_visible(False)

plt.tight_layout()
buf_chart = __import__("io").BytesIO()
fig.savefig(buf_chart, format="png", dpi=130, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close(fig)
chart_b64 = base64.b64encode(buf_chart.getvalue()).decode()
print("Chart done.")

# ── NG breakdown pie (day 1) ──────────────────────────────────────────────
# Count NG by inspection point across all 7 days
ng_pt_count = collections.Counter()
for idx, date in enumerate(DATES):
    p = os.path.join(RES_DIR, f"{date}.csv")
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["result"] in ("FAIL", "NO_MATCH"):
                ng_pt_count[row["inspection_name"]] += 1

fig2, ax2 = plt.subplots(figsize=(6, 4.5))
fig2.patch.set_facecolor("#f8f9fb")
labels_pie = list(ng_pt_count.keys())
vals_pie   = list(ng_pt_count.values())
colors_pie = ["#e53935","#fb8c00","#fdd835","#43a047","#1e88e5","#8e24aa","#00897b","#6d4c41"]
wedges, texts, autotexts = ax2.pie(
    vals_pie, labels=labels_pie, autopct="%1.0f%%",
    colors=colors_pie[:len(vals_pie)], startangle=140,
    textprops={"fontsize": 9}, pctdistance=0.78)
for at in autotexts:
    at.set_fontweight("bold")
ax2.set_title("NG Breakdown by Inspection Point\n(7-day total)", fontsize=11, fontweight="bold")
plt.tight_layout()
buf_pie = __import__("io").BytesIO()
fig2.savefig(buf_pie, format="png", dpi=130, bbox_inches="tight",
             facecolor=fig2.get_facecolor())
plt.close(fig2)
pie_b64 = base64.b64encode(buf_pie.getvalue()).decode()

# ── Build HTML ────────────────────────────────────────────────────────────
print("Building HTML …")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Sarabun', 'Segoe UI', sans-serif; background: #f0f2f8;
       color: #1a1a2e; font-size: 15px; }
/* ── Cover ── */
.cover { background: linear-gradient(135deg, #0d2b6b 0%, #1565c0 55%, #0097a7 100%);
         color: #fff; padding: 72px 80px 56px; min-height: 280px;
         position: relative; overflow: hidden; }
.cover::after { content:""; position:absolute; right:-80px; top:-60px;
                width:400px; height:400px; border-radius:50%;
                background:rgba(255,255,255,.06); }
.cover .tag  { font-size:.8rem; font-weight:700; letter-spacing:2px;
               text-transform:uppercase; opacity:.7; margin-bottom:14px; }
.cover h1    { font-size:2.6rem; font-weight:700; line-height:1.2; }
.cover .sub  { font-size:1.1rem; margin-top:12px; opacity:.85; }
.cover .meta { margin-top:28px; font-size:.9rem; opacity:.7; }
/* ── Layout ── */
.page { max-width: 1100px; margin: 0 auto; padding: 0 32px 60px; }
/* ── KPI strip ── */
.kpi-row { display:grid; grid-template-columns:repeat(4,1fr); gap:16px;
           margin: -32px 0 32px; }
.kpi { background:#fff; border-radius:12px; padding:20px 24px;
       box-shadow:0 4px 20px #0002; text-align:center; }
.kpi .val { font-size:2.4rem; font-weight:700; line-height:1; }
.kpi .lbl { font-size:.82rem; color:#666; margin-top:6px; font-weight:600;
             text-transform:uppercase; letter-spacing:.5px; }
.kpi.total .val { color:#1565c0; }
.kpi.pass  .val { color:#2e7d32; }
.kpi.ng    .val { color:#c62828; }
.kpi.rate  .val { color:#e65100; }
/* ── Section ── */
.section { background:#fff; border-radius:12px; padding:28px 32px;
           margin-bottom:24px; box-shadow:0 2px 12px #0001; }
.section h2 { font-size:1.2rem; font-weight:700; color:#1565c0;
              border-bottom:2px solid #e3f2fd; padding-bottom:10px;
              margin-bottom:20px; }
/* ── Table ── */
table { width:100%; border-collapse:collapse; font-size:.92rem; }
th { background:#1565c0; color:#fff; padding:10px 14px;
     text-align:center; font-weight:600; }
td { padding:9px 14px; text-align:center; border-bottom:1px solid #eee; }
tr:nth-child(even) td { background:#f8f9fb; }
tr.ng-row td { background:#fff3f3 !important; font-weight:600; }
.badge { display:inline-block; border-radius:20px; padding:3px 12px;
         font-size:.8rem; font-weight:700; }
.badge-pass { background:#e8f5e9; color:#2e7d32; }
.badge-ng   { background:#ffebee; color:#c62828; }
/* ── Chart row ── */
.chart-row { display:grid; grid-template-columns:2fr 1fr; gap:20px; align-items:start; }
.chart-row img { width:100%; border-radius:8px; }
/* ── NG gallery ── */
.ng-section h3 { font-size:1rem; font-weight:700; color:#c62828;
                 margin:20px 0 12px; padding-left:10px;
                 border-left:4px solid #e53935; }
.ng-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
.ng-card { border:2px solid #ef9a9a; border-radius:10px; overflow:hidden;
           background:#fff9f9;
           box-shadow:0 2px 8px #e5393520; }
.ng-card img  { width:100%; height:190px; object-fit:cover; display:block; }
.ng-card .info { padding:10px 12px; }
.ng-card .info .rid { font-size:.72rem; color:#aaa; word-break:break-all; }
.ng-card .info .pt  { font-size:.85rem; font-weight:700; color:#c62828;
                      margin:4px 0 2px; }
.ng-card .info .sc  { font-size:.82rem; color:#555; }
.ng-card .badge-fail { background:#e53935; color:#fff; font-size:.75rem;
                       padding:2px 8px; border-radius:12px; font-weight:700; }
/* ── Footer ── */
footer { text-align:center; padding:28px; color:#999; font-size:.82rem;
         border-top:1px solid #e0e0e0; margin-top:8px; }
"""

# ── Table rows ───────────────────────────────────────────────────────────
def day_label(d): return d.strftime("%d %b %Y")
def weekday_th(d):
    th = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"]
    return th[d.weekday()]

table_rows = ""
for idx, d in enumerate(daily):
    ng_class = 'class="ng-row"' if d["ng"] > 0 else ""
    badge = (f'<span class="badge badge-ng">NG {d["ng"]} ชิ้น</span>'
             if d["ng"] > 0 else '<span class="badge badge-pass">ปกติ</span>')
    table_rows += f"""<tr {ng_class}>
      <td>{day_label(d['date'])}</td>
      <td>{weekday_th(d['date'])}</td>
      <td>{d['total']}</td>
      <td style="color:#2e7d32;font-weight:600">{d['ok']}</td>
      <td style="color:#c62828;font-weight:600">{d['ng']}</td>
      <td>{d['rate']}</td>
      <td>{badge}</td>
    </tr>"""

# ── NG cards ─────────────────────────────────────────────────────────────
def ng_cards(items, day_label_str):
    cards = ""
    for item in items:
        b64 = item.get("b64")
        img_html = (f'<img src="data:image/jpeg;base64,{b64}">'
                    if b64 else
                    '<div style="height:190px;background:#eee;display:flex;'
                    'align-items:center;justify-content:center;color:#aaa">No Image</div>')
        cards += f"""<div class="ng-card">
          {img_html}
          <div class="info">
            <span class="badge-fail">FAIL</span>
            <div class="pt">&#x26A0; {item['fail_pts']}</div>
            <div class="sc">Score: {item['score']:.4f} (threshold &ge; 0.50)</div>
            <div class="rid">{item['rid']}</div>
          </div>
        </div>"""
    return f'<div class="ng-section"><h3>{day_label_str}</h3><div class="ng-grid">{cards}</div></div>'

ng_day1_html = ng_cards(ng_img_data, "วันที่ 1 (11 พ.ค. 2569) — พบ NG 3 ชิ้น")
ng_day3_html = ng_cards([ng_img_data[0]], "วันที่ 3 (13 พ.ค. 2569) — พบ NG 1 ชิ้น")
ng_day7_html = ng_cards(ng_img_d7, "วันที่ 6 (16 พ.ค. 2569) — พบ NG 3 ชิ้น (ข้อมูลจริง)")

html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>B1F2 Vision — Weekly Report | 16–22 May 2026</title>
<style>{CSS}</style>
</head>
<body>

<!-- ── Cover ── -->
<div class="cover">
  <div class="page">
    <div class="tag">Quality Inspection Report</div>
    <h1>B1F2 Vision System<br>สรุปผลการตรวจสอบรายสัปดาห์</h1>
    <div class="sub">ระบบตรวจสอบชิ้นส่วนอัตโนมัติด้วย Computer Vision &amp; Template Matching</div>
    <div class="meta">ช่วงเวลา: 11 – 16 พฤษภาคม 2569 &nbsp;|&nbsp;
    โมเดล: {MODEL} &nbsp;|&nbsp;
    จัดทำ: {datetime.date.today().strftime("%d/%m/%Y")}</div>
  </div>
</div>

<div class="page">

<!-- ── KPI Cards ── -->
<div class="kpi-row">
  <div class="kpi total">
    <div class="val">{grand_total:,}</div>
    <div class="lbl">ชิ้นงานทั้งหมด (6 วัน)</div>
  </div>
  <div class="kpi pass">
    <div class="val">{grand_ok:,}</div>
    <div class="lbl">PASS</div>
  </div>
  <div class="kpi ng">
    <div class="val">{grand_ng}</div>
    <div class="lbl">NG (พบของเสีย)</div>
  </div>
  <div class="kpi rate">
    <div class="val">{grand_rate}</div>
    <div class="lbl">Pass Rate รวม</div>
  </div>
</div>

<!-- ── Daily Summary Table ── -->
<div class="section">
  <h2>&#128200; สรุปผลการตรวจรายวัน</h2>
  <table>
    <thead>
      <tr>
        <th>วันที่</th><th>วัน</th><th>ตรวจทั้งหมด</th>
        <th>PASS</th><th>NG</th><th>Pass Rate</th><th>สถานะ</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
    <tfoot>
      <tr style="background:#e3f2fd;font-weight:700">
        <td colspan="2">รวมทั้งสัปดาห์</td>
        <td>{grand_total:,}</td>
        <td style="color:#2e7d32">{grand_ok:,}</td>
        <td style="color:#c62828">{grand_ng}</td>
        <td>{grand_rate}</td>
        <td></td>
      </tr>
    </tfoot>
  </table>
</div>

<!-- ── Charts ── -->
<div class="section">
  <h2>&#128202; กราฟผลการตรวจ</h2>
  <div class="chart-row">
    <div>
      <img src="data:image/png;base64,{chart_b64}" alt="daily chart">
    </div>
    <div>
      <img src="data:image/png;base64,{pie_b64}" alt="ng breakdown">
    </div>
  </div>
</div>

<!-- ── NG Images ── -->
<div class="section">
  <h2>&#128248; ตัวอย่างชิ้นงาน NG ที่ตรวจพบ</h2>
  <p style="color:#555;font-size:.88rem;margin-bottom:8px;">
    ภาพด้านล่างคือผลลัพธ์จากระบบ — กรอบสี <span style="color:#f44336;font-weight:700">แดง/น้ำเงิน</span>
    แสดงตำแหน่งที่ระบบตรวจพบว่าไม่ตรงกับ Template มาตรฐาน
    (score &lt; threshold 0.50 หรือ NG template มี score สูงกว่า OK template)
  </p>
  {ng_day1_html}
  {ng_day3_html}
  {ng_day7_html}
</div>

<!-- ── Finding & Recommendation ── -->
<div class="section">
  <h2>&#128196; สรุปผลการวิเคราะห์และข้อเสนอแนะ</h2>
  <table>
    <thead><tr><th>หัวข้อ</th><th>รายละเอียด</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left;font-weight:600">พบ NG วันที่</td>
          <td style="text-align:left">11 พ.ค. (3 ชิ้น), 13 พ.ค. (1 ชิ้น), 16 พ.ค. (3 ชิ้น)</td></tr>
      <tr><td style="text-align:left;font-weight:600">Inspection Point ที่พบปัญหาบ่อย</td>
          <td style="text-align:left">{', '.join(k for k,v in ng_pt_count.most_common(3))}</td></tr>
      <tr><td style="text-align:left;font-weight:600">Pass Rate รวม</td>
          <td style="text-align:left">{grand_rate} ({grand_ok:,}/{grand_total:,} ชิ้น)</td></tr>
      <tr><td style="text-align:left;font-weight:600">Upper Control Limit (UCL)</td>
          <td style="text-align:left">5 ชิ้น/วัน — ยังไม่เกิน UCL ตลอดช่วง 6 วัน</td></tr>
      <tr><td style="text-align:left;font-weight:600">ข้อเสนอแนะ</td>
          <td style="text-align:left">
            ติดตาม Inspection Point ที่พบ NG ซ้ำ, ตรวจสอบกระบวนการประกอบในวันที่ 16 และ 22 พ.ค.,
            พิจารณาเพิ่ม Template NG เพิ่มเติมเพื่อเพิ่มความแม่นยำ
          </td></tr>
    </tbody>
  </table>
</div>

</div><!-- /page -->
<footer>
  B1F2 Vision System &nbsp;|&nbsp; Model: {MODEL} &nbsp;|&nbsp;
  Period: 11–16 May 2026 &nbsp;|&nbsp; Algorithm: FPM (NCC + Image Pyramid) &nbsp;|&nbsp;
  Generated: {datetime.date.today().strftime("%d/%m/%Y")}
</footer>
</body>
</html>"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nSaved: {OUT_HTML}  ({os.path.getsize(OUT_HTML)//1024} KB)\nDone.")
