"""Check the toolbox from INSTALL-FOR-AI.md section 1 the way the bot would use it.
Run with tgpy (/opt/tgbox/venv/bin/python) after the cloud desktop is up. Prints one line per check."""
import subprocess, sys, tempfile, warnings
from pathlib import Path

T = Path(tempfile.mkdtemp())
FAIL = []
TEXT = "季度销售报告 Quarterly report"


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=T)


def check(name, ok, info=""):
    print(("ok  " if ok else "FAIL"), name, info if not ok else "")
    if not ok:
        FAIL.append(name)


# Word: write with python-docx -> read back with pandoc -> convert to PDF with LibreOffice -> pdftotext
import docx
d = docx.Document(); d.add_heading(TEXT, 1); d.add_paragraph("第二段：营收 120 万"); d.save(T / "r.docx")
r = sh("pandoc", "r.docx", "-t", "plain")
check("docx -> pandoc", "营收 120 万" in r.stdout, r.stderr[-300:])
r = sh("soffice", "--headless", "--convert-to", "pdf", "r.docx")
check("docx -> pdf (soffice)", (T / "r.pdf").exists(), r.stdout[-300:] + r.stderr[-300:])
r = sh("pdftotext", "-layout", "r.pdf", "-")
check("pdftotext", "季度销售报告" in r.stdout, r.stdout[-200:])
from pypdf import PdfReader
check("pypdf", "营收" in PdfReader(T / "r.pdf").pages[0].extract_text())

# Excel + PPT round trips
import openpyxl, pandas as pd
wb = openpyxl.Workbook(); ws = wb.active; ws.append(["月份", "销量"]); ws.append(["1月", 30]); ws.append(["2月", 45]); wb.save(T / "s.xlsx")
df = pd.read_excel(T / "s.xlsx")
check("xlsx (openpyxl + pandas)", int(df["销量"].sum()) == 75)
from pptx import Presentation
pr = Presentation(); sl = pr.slides.add_slide(pr.slide_layouts[1]); sl.shapes.title.text = TEXT; pr.save(T / "p.pptx")
check("pptx", Presentation(T / "p.pptx").slides[0].shapes.title.text == TEXT)

# Scanned page: render Chinese text to an image, OCR it back
from PIL import Image, ImageDraw, ImageFont
# (a page-like layout: margins and normal text size; one huge line with no margin OCRs to nothing)
font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 40)
img = Image.new("RGB", (1200, 300), "white"); dr = ImageDraw.Draw(img)
dr.text((60, 60), "季度销售报告", fill="black", font=font); dr.text((60, 140), "第二段：营收 120 万元", fill="black", font=font)
img.save(T / "scan.png")
r = sh("tesseract", "scan.png", "-", "-l", "chi_sim+eng")
check("tesseract chi_sim", "销售" in r.stdout.replace(" ", ""), repr(r.stdout) + r.stderr[-200:])
r = sh("convert", "scan.png", "-resize", "50%", "small.jpg")
check("imagemagick", (T / "small.jpg").exists(), r.stderr[-200:])

# Chart with Chinese labels and no missing-glyph warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Noto Sans CJK JP"
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    plt.bar(["1月", "2月"], [30, 45]); plt.title("销量"); plt.savefig(T / "chart.png"); plt.close()
glyph = [str(x.message) for x in w if "glyph" in str(x.message).lower() or "font" in str(x.message).lower()]
check("matplotlib 中文", (T / "chart.png").stat().st_size > 5000 and not glyph, glyph[:2])

# Browser: drive the cloud desktop's Chrome over CDP (no new browser)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0] if b.contexts else b.new_context()
    page = ctx.new_page()
    page.set_content("<h1 id=t>浏览器自动化 OK</h1>")
    ok = page.inner_text("#t") == "浏览器自动化 OK"
    page.screenshot(path=str(T / "page.png"))
    page.close()
check("playwright over CDP", ok and (T / "page.png").exists())

print("TOOLBOX FAIL: " + ", ".join(FAIL) if FAIL else "TOOLBOX OK")
sys.exit(1 if FAIL else 0)
