from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

old = '''    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "jobs": rows,
            "stats": stats,
        }
    )'''

new = '''    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "app_name": APP_NAME,
            "jobs": rows,
            "stats": stats,
        }
    )'''

if old not in text:
    raise SystemExit("Could not find old TemplateResponse block. Open main.py and patch manually.")

text = text.replace(old, new)
path.write_text(text, encoding="utf-8")

print("? Fixed TemplateResponse call in main.py")
