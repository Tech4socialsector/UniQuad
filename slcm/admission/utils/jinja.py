import frappe
import base64
import os

def get_file_b64(file_url):
    """
    Returns base64 encoded string of a file.
    Used in Jinja templates for PDF generation to avoid external HTTP requests.
    """
    if not file_url or not isinstance(file_url, str):
        return ""
    
    try:
        # If it's already a data URI, just return the base64 part
        if file_url.startswith("data:") and ";base64," in file_url:
            return file_url.split(";base64,")[1]

        # Resolve local path if it starts with /files/ or /private/files/
        if file_url.startswith("/files/") or file_url.startswith("/private/files/"):
            is_pub = file_url.startswith("/files/")
            path = frappe.get_site_path("public" if is_pub else "", file_url.lstrip("/"))
            candidates = [path]
            if "." in path:
                ext_dot = path.rfind(".")
                candidates.append(path[:ext_dot] + " (Copy)" + path[ext_dot:])

            # Alternate path (if stored in private instead of public or vice versa)
            rel_sub = file_url[len("/files/"):] if is_pub else file_url[len("/private/files/"):]
            alt_path = frappe.get_site_path("" if is_pub else "public", ("private/files/" if is_pub else "files/") + rel_sub)
            candidates.append(alt_path)
            if "." in alt_path:
                ext_dot = alt_path.rfind(".")
                candidates.append(alt_path[:ext_dot] + " (Copy)" + alt_path[ext_dot:])

            for p in candidates:
                if os.path.exists(p) and os.path.isfile(p):
                    with open(p, "rb") as f:
                        return base64.b64encode(f.read()).decode()

        # Fallback: Try to get via File DocType by exact file_url
        file_docs = frappe.get_all("File", filters={"file_url": file_url}, fields=["name"], limit=1)
        if file_docs:
            fdoc = frappe.get_doc("File", file_docs[0].name)
            content = fdoc.get_content()
            if content:
                if isinstance(content, str):
                    content = content.encode("utf-8")
                return base64.b64encode(content).decode()
            
    except Exception:
        pass

    return ""


_MERRIWEATHER_FACES = (
    # (file in slcm/public/fonts, font-weight, font-style)
    ("Merriweather-Regular.ttf", "400", "normal"),
    ("Merriweather-Bold.ttf", "700", "normal"),
    ("Merriweather-Italic.ttf", "400", "italic"),
)
_merriweather_css_cache = None


def get_merriweather_font_css():
    """CSS that embeds the app's bundled Merriweather TTFs (base64) and makes every element use it.

    Use inside a print format's <style> block: {{ get_merriweather_font_css() }}
    Works offline in wkhtmltopdf / Chrome PDF — no Google Fonts request needed.
    """
    global _merriweather_css_cache
    if _merriweather_css_cache is not None:
        return _merriweather_css_cache

    faces = []
    for filename, weight, style in _MERRIWEATHER_FACES:
        path = frappe.get_app_path("slcm", "public", "fonts", filename)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        # "src:/**/url(" — the empty comment stops frappe's expand_relative_urls (run on every
        # server-side PDF) from matching ":url(" and appending " !important" after the url(),
        # which turns this into an invalid src and wkhtmltopdf silently drops the font.
        faces.append(
            "@font-face{font-family:'Merriweather';"
            f"src:/**/url(data:font/ttf;base64,{data}) format('truetype');"
            f"font-weight:{weight};font-style:{style};}}"
        )
    css = ""
    if faces:
        css = "".join(faces) + "html,body,body *{font-family:'Merriweather',serif !important;}"
    _merriweather_css_cache = css
    return css


def embed_merriweather_for_pdf(html):
    """For server-side PDFs: if the HTML wants Merriweather, drop the Google Fonts link/import
    (unreachable for wkhtmltopdf on the server) and embed the bundled font instead."""
    import re

    if not html or "merriweather" not in html.lower() or "@font-face{font-family:'Merriweather'" in html:
        return html
    html = re.sub(r"<link[^>]*fonts\.googleapis\.com[^>]*>", "", html)
    html = re.sub(r"@import\s+url\([^)]*fonts\.googleapis\.com[^)]*\);?", "", html)
    css = get_merriweather_font_css()
    if not css:
        return html
    style = f"<style>{css}</style>"
    if re.search(r"<head[^>]*>", html, re.I):
        return re.sub(r"<head[^>]*>", lambda m: m.group(0) + style, html, count=1, flags=re.I)
    return style + html
