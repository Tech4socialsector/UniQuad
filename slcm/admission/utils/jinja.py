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
