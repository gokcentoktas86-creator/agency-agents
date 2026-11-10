#!/usr/bin/env python3
"""
Phone Bridge — Master Agent System
====================================
Receives commands from phone (Telegram/WhatsApp/Flutter app) via HTTP,
routes them to the right sub-agent, executes on the computer, and returns
results. After every task, updates the skills database, department records,
and daily memory — so the system gets smarter with every interaction.

Architecture:
    Phone (Telegram/WhatsApp/Flutter)
        → POST /command  {"command": "...", "channel": "phone"}
        → Master Agent routes to sub-agent
        → Sub-agent workflow executes on computer
        → Result returned to phone
        → skills.json + department-records.json + memory updated

Run:
    python3 phone-bridge.py [--port 8765] [--host 0.0.0.0]

Endpoints:
    GET  /                — Web UI (computer access)
    POST /command         — Main entry (phone commands)
    POST /telegram        — Telegram webhook
    POST /whatsapp        — WhatsApp webhook
    GET  /status          — System status
    GET  /skills          — Skills database
    GET  /departments     — Department records
    GET  /health          — Health check
"""

import json
import os
import re
import sys
import time
import argparse
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BRIDGE_DIR)  # agency-agents root

SKILLS_PATH = os.path.join(BRIDGE_DIR, "skills.json")
RECORDS_PATH = os.path.join(BRIDGE_DIR, "department-records.json")
MEMORY_DIR = os.path.join(REPO_ROOT, "strategy", "memory")
DATA_DIR = os.path.join(BRIDGE_DIR, "data")
OUTPUT_DIR = os.path.join(BRIDGE_DIR, "output")
USAGE_PATH = os.path.join(DATA_DIR, "usage.json")
KEYS_PATH = os.path.join(DATA_DIR, "api-keys.json")

# --------------------------------------------------------------------------
# Data access helpers
# --------------------------------------------------------------------------

def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        data_str = f.tell()
    return True

def today_str():
    return datetime.date.today().isoformat()

def now_str():
    return datetime.datetime.now().isoformat(timespec="seconds")

def load_skills():
    return load_json(SKILLS_PATH, {"skills": []})

def save_skills(data):
    data["updated"] = today_str()
    save_json(SKILLS_PATH, data)

def load_records():
    return load_json(RECORDS_PATH, {"departments": {}})

def save_records(data):
    data["updated"] = today_str()
    save_json(RECORDS_PATH, data)

def load_inbox():
    return load_json(os.path.join(DATA_DIR, "inbox.json"), {"inbox": []})

def load_appointments():
    return load_json(os.path.join(DATA_DIR, "appointments.json"), {"appointments": []})

def load_usage():
    return load_json(USAGE_PATH, {
        "version": "1.0",
        "free_tier": {"daily_limit": 1},
        "premium_tier": {"daily_limit": 999},
        "usage": {},
    })

def save_usage(data):
    data["updated"] = today_str()
    save_json(USAGE_PATH, data)

def load_api_keys():
    return load_json(KEYS_PATH, {"keys": {}})

def save_api_keys(data):
    data["updated"] = today_str()
    save_json(KEYS_PATH, data)

def get_client_ip(handler):
    """Extract client IP from request."""
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = handler.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    return handler.client_address[0] if handler.client_address else "unknown"

def check_daily_quota(ip, usage_data=None):
    """Check if IP has exceeded daily free quota. Returns (allowed, remaining, status)."""
    if usage_data is None:
        usage_data = load_usage()
    
    # Check if IP is premium — unlimited access
    if ip in usage_data.get("premium_ips", []):
        return (True, 999, "premium")
    
    today = today_str()
    key = f"{today}|{ip}"
    entry = usage_data.get("usage", {}).get(key, {})
    free_limit = usage_data.get("free_tier", {}).get("daily_limit", 1)
    task_count = entry.get("tasks", 0)
    
    if task_count >= free_limit:
        return (False, 0, "free_tier_exceeded")
    return (True, free_limit - task_count, "free_tier")

def increment_usage(ip, command, result_summary=""):
    """Increment task count for an IP."""
    usage_data = load_usage()
    today = today_str()
    key = f"{today}|{ip}"
    usage = usage_data.setdefault("usage", {})
    entry = usage.setdefault(key, {"tasks": 0, "first_task": None, "last_task": None})
    entry["tasks"] += 1
    now = now_str()
    if entry["first_task"] is None:
        entry["first_task"] = now
    entry["last_task"] = now
    entry["command"] = command[:100]
    entry["result"] = result_summary[:100]
    save_usage(usage_data)
    return entry["tasks"]

def load_companies():
    return load_json(os.path.join(DATA_DIR, "companies.json"), {"companies": []})

# --------------------------------------------------------------------------
# Skill & department tracking
# --------------------------------------------------------------------------

def update_skill(skill_id, success=True, improvement=None):
    skills = load_skills()
    for skill in skills.get("skills", []):
        if skill["id"] == skill_id:
            skill["success_count"] = skill.get("success_count", 0) + (1 if success else 0)
            if not success:
                skill["failure_count"] = skill.get("failure_count", 0) + 1
            skill["last_used"] = today_str()
            if improvement:
                skill.setdefault("improvements", []).append({
                    "date": today_str(),
                    "note": improvement,
                })
                skill["version"] = skill.get("version", 1) + 1
            break
    save_skills(skills)

def log_department_activity(dept_key, task, result):
    records = load_records()
    dept = records["departments"].get(dept_key)
    if dept:
        dept.setdefault("activity_log", []).append({
            "timestamp": now_str(),
            "task": task,
            "result": result,
        })
        dept["last_activity"] = now_str()
        dept.setdefault("metrics", {})["tasks_completed"] = dept.get("metrics", {}).get("tasks_completed", 0) + 1
        dept.setdefault("metrics", {})["skills_used"] = dept.get("metrics", {}).get("skills_used", 0) + 1
        save_records(records)

def update_memory(content):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    date = today_str()
    path = os.path.join(MEMORY_DIR, f"{date}.md")
    entry = f"\n## {now_str()} — {content}\n"
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(existing + entry)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Daily Memory — {date}\n\n## System Status\nLive.\n\n## Today's Work\n{entry}")

# --------------------------------------------------------------------------
# Sub-agent workflows (execute on computer)
# --------------------------------------------------------------------------

def workflow_email(command):
    """Email Ops — triage inbox, draft replies."""
    inbox = load_inbox()
    emails = inbox.get("inbox", [])
    unread = [e for e in emails if e.get("status") == "unread"]

    result = {"sub_agent": "email-ops", "action": "inbox_triage", "total": len(emails), "unread": len(unread)}

    # Classify and draft replies
    drafts = []
    for e in unread:
        if e["type"] == "pricing":
            drafts.append({
                "to": e["from"],
                "subject": f"Re: {e['subject']}",
                "body": "Merhaba,\n\nTeşekkür ederim. Fiyat teklifimizi aşağıda paylaşıyorum:\n\n- 50 adet ofis malzemesi: ₺12.500 + KDV\n- Teslimat: 5-7 iş günü\n\nDetaylı bilgi için iletişime geçmekten mutlu oluruz.\n\nSaygılarımla",
            })
        elif e["type"] == "urgent":
            drafts.append({
                "to": e["from"],
                "subject": f"Re: {e['subject']}",
                "body": "Merhaba,\n\nToplantı ertelenmesi konusunda sizden görüşlerinizi beklerim. En kısa sürede dönüş yapacağım.\n\nSaygılarımla",
            })
        elif e["type"] == "support":
            drafts.append({
                "to": e["from"],
                "subject": f"Re: {e['subject']}",
                "body": "Merhaba,\n\nSipariş numarası 12345 için takip numaranızı iletiyorum. Teslimat bu hafta içinde gerçekleşecektir.\n\nSaygılarımla",
            })
        elif e["type"] == "offer":
            drafts.append({
                "to": e["from"],
                "subject": f"Re: {e['subject']}",
                "body": "Merhaba,\n\nTeklifiniz alındı. Detaylı değerlendirme için ilgili departamento ile görüşüyorum. En kısa sürede dönüş yapacağım.\n\nSaygılarımla",
            })

    result["drafts"] = drafts
    result["draft_count"] = len(drafts)
    result["message"] = f"Inbox: {len(emails)} emails, {len(unread)} unread. {len(drafts)} draft replies prepared."
    return result

def workflow_pricing(command):
    """Email Ops — find price requesters, prepare price list."""
    inbox = load_inbox()
    emails = inbox.get("inbox", [])
    price_requests = [e for e in emails if e.get("type") == "pricing" and e.get("status") == "unread"]

    result = {"sub_agent": "email-ops", "action": "price_quote", "requesters": []}
    for e in price_requests:
        result["requesters"].append({
            "from": e["from"],
            "subject": e["subject"],
            "price": "₺12.500 + KDV (50 adet ofis malzemesi)",
            "delivery": "5-7 iş günü",
        })
    result["message"] = f"{len(price_requests)} price request(s) found. Price list prepared."
    return result

def workflow_offer(command):
    """Email Ops — receive and summarize offers."""
    inbox = load_inbox()
    emails = inbox.get("inbox", [])
    offers = [e for e in emails if e.get("type") == "offer" and e.get("status") == "unread"]

    result = {"sub_agent": "email-ops", "action": "offer_intake", "offers": []}
    for e in offers:
        result["offers"].append({
            "from": e["from"],
            "subject": e["subject"],
            "summary": "Tedarik zinciri hizmeti — Aylık 3.500 TL + KDV",
            "status": "received",
        })
    result["message"] = f"{len(offers)} offer(s) received and summarized."
    return result

def workflow_accounting(command):
    """Accounting Ops — check documents, prepare monthly statement."""
    result = {"sub_agent": "accounting-ops", "action": "accounting_check", "documents": []}

    # Simulate document check
    documents = [
        {"doc": "Fatura #1001 — Anadolu Lojistik", "amount": "₺12.500", "status": "verified"},
        {"doc": "Fatura #1002 — Ege Teknoloji", "amount": "₺8.200", "status": "verified"},
        {"doc": "Banka Girişi — Kasım 2026", "amount": "₺45.300", "status": "flagged", "reason": "Mismatch with ledger — needs review"},
    ]
    result["documents"] = documents
    result["checked"] = len(documents)
    result["flagged"] = len([d for d in documents if d["status"] == "flagged"])

    # Prepare monthly statement
    statement = f"""AYLIK MUHASEBE DÖKÜMÜ — {today_str()}

Gelirler:
  - Anadolu Lojistik (Fatura #1001): ₺12.500
  - Ege Teknoloji (Fatura #1002): ₺8.200
Toplam Gelir: ₺20.700

Giderler:
  - Tedarikçi ödemeleri: ₺15.000
  - Operating costs: ₺5.200
Toplam Gider: ₺20.200

Net: ₺500

Notlar:
  - Banka gleisi ile ledger arasında fark — inceleniyor
  - Tüm faturalar doğrulandı
"""
    out_path = os.path.join(OUTPUT_DIR, f"monthly-statement-{today_str()}.txt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(statement)

    result["statement_file"] = out_path
    result["message"] = f"{len(documents)} documents checked, {result['flagged']} flagged. Monthly statement prepared."
    return result

def workflow_sales(command):
    """Sales Ops — research companies in target area."""
    companies = load_companies()
    list_ = companies.get("companies", [])

    # Filter by area if mentioned
    import re as _re
    area_match = _re.search(r'(İzmir|Manisa|İstanbul|Ankara|Antalya|Bursa)', command, _re.IGNORECASE)
    filtered = list_
    if area_match:
        area = area_match.group(1)
        filtered = [c for c in list_ if c.get("location", "").lower() == area.lower() or area.lower() in c.get("location", "").lower()]

    result = {"sub_agent": "sales-ops", "action": "company_research", "companies": []}
    for c in filtered:
        result["companies"].append({
            "name": c["name"],
            "industry": c["industry"],
            "location": c["location"],
            "qualification": c["qualification"],
            "score": c["score"],
            "contact": c["contact_name"],
            "email": c["contact_email"],
        })
    result["count"] = len(result["companies"])
    result["message"] = f"{len(result['companies'])} company(ies) found. Qualification scores assigned."
    return result

def workflow_appointment(command):
    """Appointment Ops — check today's appointments."""
    appointments = load_appointments()
    list_ = appointments.get("appointments", [])
    today = today_str()
    todays = [a for a in list_ if a.get("date") == today]

    result = {"sub_agent": "appointment-ops", "action": "appointment_check", "today": today, "appointments": []}

    conflicts = []
    for a in todays:
        result["appointments"].append({
            "title": a["title"],
            "time": f"{a['start_time']} - {a['end_time']}",
            "location": a["location"],
            "status": a["status"],
            "notes": a.get("notes", ""),
        })
        if a["status"] == "tentative":
            conflicts.append(a["title"])

    result["conflict_count"] = len(conflicts)
    result["message"] = f"Today ({today}): {len(todays)} appointment(s). {len(conflicts)} tentative need confirmation."
    return result

def workflow_presentation(command):
    """Presentation Ops — prepare presentation file."""
    # Generate a simple HTML presentation
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Sunum — {today_str()}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 40px; }}
.slide {{ border-bottom: 1px solid #ccc; padding: 20px 0; }}
h1 {{ color: #333; }}
h2 {{ color: #555; }}
.data {{ background: #f5f5f5; padding: 10px; border-left: 4px solid #4CAF50; }}
</style>
</head>
<body>
<h1>İş Durumu Raporu — {today_str()}</h1>

<div class="slide">
<h2>1. Bugünün Randevular</h2>
<div class="data">
• 14:00 — Ahmet Yılmaz (Fiyat görüşme)<br>
• 15:30 — Fatma Demir (Tedarik zinciri)<br>
• 10:00 — Mehmet Oktar (Toplantı — ERTELENMİŞ)<br>
</div>
</div>

<div class="slide">
<h2>2. E-posta Durumu</h2>
<div class="data">
• 5 e-posta — 3 acil<br>
• 2 fiyat isteği — reply drafted<br>
• 1 teklif alındı<br>
</div>
</div>

<div class="slide">
<h2>3. Sales Pipeline</h2>
<div class="data">
• 4 potansiyel müşteri — 2 hot, 2 warm<br>
• En yüksek puan: Anadolu Lojistik (92)<br>
</div>
</div>

<div class="slide">
<h2>4. Muhasebe</h2>
<div class="data">
• Aylık döküm hazır<br>
• Net: ₺500<br>
• 1 flagged document — inceleniyor<br>
</div>
</div>

<div class="slide">
<h2>5. Next Steps</h2>
<div class="data">
• Tente appointment confirm<br>
• Follow up with hot leads<br>
• Review flagged bank document<br>
</div>
</div>
</body>
</html>"""
    out_path = os.path.join(OUTPUT_DIR, f"presentation-{today_str()}.html")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    result = {"sub_agent": "presentation-ops", "action": "presentation_prep", "file": out_path}
    result["message"] = f"Presentation prepared: {out_path}"
    return result

# --------------------------------------------------------------------------
# Profession workflows
# --------------------------------------------------------------------------

PROFESSIONS_PATH = os.path.join(BRIDGE_DIR, "professions.json")

def load_professions():
    return load_json(PROFESSIONS_PATH, {"categories": {}})

def workflow_profession(command, category_hint=None):
    """Route a command to a profession category master agent.
    
    If category_hint is provided (from the matched route's sub_agent),
    use it to directly select the category without re-scoring.
    """
    cmd_lower = command.lower()
    prof_data = load_professions()
    categories = prof_data.get("categories", {})
    
    # Map from sub_agent name to category key
    sub_agent_to_cat = {
        "it-master": "it-software",
        "finance-master": "finance-accounting",
        "healthcare-master": "healthcare-medical",
        "legal-master": "legal-justice",
        "education-master": "education-training",
        "media-master": "media-creative",
        "business-master": "business-management",
        "engineering-master": "engineering-technical",
        "research-master": "research-science",
        "design-master": "design-architecture",
    }
    
    # If we have a hint from the route, use it directly
    if category_hint and category_hint in sub_agent_to_cat:
        best_cat = sub_agent_to_cat[category_hint]
    else:
        # Build keyword map: category -> list of keywords from labels + professions + ROUTES
        cat_keywords = {}
        for cat_key, cat_data in categories.items():
            keywords = set()
            # From category label
            cat_label = cat_data.get("label", "").lower()
            for kw in cat_label.split():
                if len(kw) > 3:
                    keywords.add(kw)
            # From profession names — extract root words
            for prof in cat_data.get("professions", []):
                prof_name = prof.get("name", "").lower()
                prof_name = re.sub(r'\d+', '', prof_name)
                for kw in prof_name.split():
                    kw = kw.strip()
                    if len(kw) > 3:
                        keywords.add(kw)
                    for suffix in ['cısı', 'ıcı', 'ından', 'lığı', 'cis', 'ci', 'lik']:
                        if kw.endswith(suffix) and len(kw) > len(suffix) + 2:
                            keywords.add(kw[:-len(suffix)])
            # From ROUTES dict keywords for this category
            for route_key, route in ROUTES.items():
                if route.get("sub_agent") == sub_agent_to_cat.get(cat_key, "").replace("-master", "-master"):
                    pass
                # Match by checking if any profession route keyword belongs to this category
            # Add explicit keywords from professions.json tasks
            for prof in cat_data.get("professions", []):
                for task in prof.get("tasks", []):
                    for kw in task.split():
                        kw = kw.strip().lower()
                        if len(kw) > 3 and kw not in ['bir', 've', 'ile', 'olarak', 'için', 'ile', 'olarak', 'olarak']:
                            keywords.add(kw)
            cat_keywords[cat_key] = (cat_data, keywords)
        
        # Score each category by matching keywords
        best_cat = None
        best_score = 0
        for cat_key, (cat_data, keywords) in cat_keywords.items():
            score = 0
            for kw in keywords:
                if kw.lower() in cmd_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_cat = cat_key
    
    if not best_cat:
        return {
            "sub_agent": "master-agent",
            "action": "profession_route",
            "message": f"Command does not match any profession category. Available categories: {', '.join(cat.get('label', k) for k, cat in categories.items())}",
        }
    
    matched = categories[best_cat]
    cat_label = matched.get("label", best_cat)
    master_pattern = matched.get("master_pattern", "")
    helpers = matched.get("helpers", [])
    helper_names = ", ".join([h.get("role", "") for h in helpers])
    
    result = {
        "sub_agent": f"{cat_label.lower().replace(' ', '-')}-master",
        "action": "profession_task",
        "category": cat_label,
        "category_key": best_cat,
        "master_pattern": master_pattern,
        "helpers": [{"role": h.get("role"), "handles": h.get("handles")} for h in helpers],
        "professions_in_category": len(matched.get("professions", [])),
        "message": f"Routed to {cat_label} Master. 5 helper agents available: {helper_names}. {master_pattern}",
    }
    return result


# --------------------------------------------------------------------------
# Command routing
# --------------------------------------------------------------------------

ROUTES = {
    "email": {
        "keywords": ["mail", "e-posta", "gelen", "inbox", "cevapla", "yanıtla", "mailleri"],
        "sub_agent": "email-ops",
        "workflow": workflow_email,
        "skill_id": "email-reply",
        "dept": "operations",
    },
    "pricing": {
        "keywords": ["fiyat", "price", "quote", "fiyatlandır", "fiyat verme", "fiyat istediği"],
        "sub_agent": "email-ops",
        "workflow": workflow_pricing,
        "skill_id": "price-quote",
        "dept": "operations",
    },
    "offer": {
        "keywords": ["teklif", "offer", "proposal", "teklif al", "teklifleri"],
        "sub_agent": "email-ops",
        "workflow": workflow_offer,
        "skill_id": "offer-intake",
        "dept": "operations",
    },
    "accounting": {
        "keywords": ["muhasebe", "accounting", "belge", "fatura", "döküm", "aylık", "financial"],
        "sub_agent": "accounting-ops",
        "workflow": workflow_accounting,
        "skill_id": "monthly-statement",
        "dept": "operations",
    },
    "sales": {
        "keywords": ["şirket", "company", "prospect", "potansiyel", "bul", "satış", "sales", "müşteri avı"],
        "sub_agent": "sales-ops",
        "workflow": workflow_sales,
        "skill_id": "company-research",
        "dept": "operations",
    },
    "appointment": {
        "keywords": ["randevu", "appointment", "calendar", "takvim", "görüşme", "schedule", "bugünkü", "bugün neler"],
        "sub_agent": "appointment-ops",
        "workflow": workflow_appointment,
        "skill_id": "appointment-check",
        "dept": "operations",
    },
    "presentation": {
        "keywords": ["sunum", "presentation", "slide", "deck", "gösterim", "sunum-hazirla"],
        "sub_agent": "presentation-ops",
        "workflow": workflow_presentation,
        "skill_id": "presentation-prep",
        "dept": "operations",
    },
    "profession-it": {
        "keywords": ["program", "kod", "software", "yazılım", "bilgisayar", "it", "sistem", "veritabanı", "network", "ağ", "code", "develop"],
        "sub_agent": "it-master",
        "workflow": workflow_profession,
        "skill_id": "profession-it-software",
        "dept": "operations",
    },
    "profession-finance": {
        "keywords": ["muhasebe", "fatura", "finance", "finans", "vergi", "banka", "bankacı", "ekonometr", "yatırım", "borsa", "sigorta"],
        "sub_agent": "finance-master",
        "workflow": workflow_profession,
        "skill_id": "profession-finance-accounting",
        "dept": "operations",
    },
    "profession-healthcare": {
        "keywords": ["doktor", "sağlık", "hasta", "medikal", "ecza", "eczacı", "diş", "radyoloji", "laboratuvar", "hemşire", "tıp", "diyetisyen", "fizyoterapist"],
        "sub_agent": "healthcare-master",
        "workflow": workflow_profession,
        "skill_id": "profession-healthcare-medical",
        "dept": "operations",
    },
    "profession-legal": {
        "keywords": ["avukat", "hukuk", "davaa", "mahkeme", "hakim", "savcı", "adli", "bildirim", "yasal", "hukuki", "büro"],
        "sub_agent": "legal-master",
        "workflow": workflow_profession,
        "skill_id": "profession-legal-justice",
        "dept": "operations",
    },
    "profession-education": {
        "keywords": ["öğretmen", "eğitim", "eğitmen", "ders", "mürebbiye", "okutman", "akademisyen", "profesör", "universite", "okul", "öğrenci", "ders planı"],
        "sub_agent": "education-master",
        "workflow": workflow_profession,
        "skill_id": "profession-education-training",
        "dept": "operations",
    },
    "profession-media": {
        "keywords": ["gazeteci", "haber", "yazar", "editör", "yayın", "medya", "reklam", "tv", "video", "audio", "ses", "créatif", "sanatçı", "dizi"],
        "sub_agent": "media-master",
        "workflow": workflow_profession,
        "skill_id": "profession-media-creative",
        "dept": "operations",
    },
    "profession-business": {
        "keywords": ["işletme", "menajer", "yönetici", "sirket", "şirket", "business", "strateji", "hr", "personel", "satış", "müşteri", "lobi", "iş planı", "iş", "plan"],
        "sub_agent": "business-master",
        "workflow": workflow_profession,
        "skill_id": "profession-business-management",
        "dept": "operations",
    },
    "profession-engineering": {
        "keywords": ["mühendis", "engineering", "teknik", "tasarım", "çizim", "ise", "elektrik", "makine", "kimya", "inşaat", "endustri", "jeoloji", "teknik çizim"],
        "sub_agent": "engineering-master",
        "workflow": workflow_profession,
        "skill_id": "profession-engineering-technical",
        "dept": "operations",
    },
    "profession-research": {
        "keywords": ["araştırma", "research", "akademik", "bilim", "tez", "yayın", "grant", "fon", "verim", "istatistik", "laboratuvar", "evrim"],
        "sub_agent": "research-master",
        "workflow": workflow_profession,
        "skill_id": "profession-research-science",
        "dept": "operations",
    },
    "profession-design": {
        "keywords": ["tasarım", "design", "mimar", "graphics", "grafik", "3d", "animasyon", "animasyon", "afiş", "logo", "ux", "ui", "dizayn"],
        "sub_agent": "design-master",
        "workflow": workflow_profession,
        "skill_id": "profession-design-architecture",
        "dept": "operations",
    },
}

def route_command(command):
    """Route a command to the right sub-agent workflow."""
    cmd_lower = command.lower()
    for route_key, route in ROUTES.items():
        for keyword in route["keywords"]:
            if keyword.lower() in cmd_lower:
                return route
    return None

# --------------------------------------------------------------------------
# Bridge server
# --------------------------------------------------------------------------

class BridgeHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress default logging, use our own
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_web_ui()
        elif path == "/status":
            self._send_json(self._get_status())
        elif path == "/skills":
            self._send_json(load_skills())
        elif path == "/departments":
            self._send_json(load_records())
        elif path == "/health":
            self._send_json({"status": "ok", "time": now_str()})
        elif path == "/upgrade":
            self._serve_upgrade_page()
        elif path == "/usage":
            client_ip = get_client_ip(self)
            usage_data = load_usage()
            today = today_str()
            key = f"{today}|{client_ip}"
            entry = usage_data.get("usage", {}).get(key, {})
            free_limit = usage_data.get("free_tier", {}).get("daily_limit", 1)
            is_premium = client_ip in usage_data.get("premium_ips", [])
            self._send_json({
                "ip": client_ip,
                "date": today,
                "tier": "premium" if is_premium else "free",
                "tasks_today": entry.get("tasks", 0),
                "daily_limit": 999 if is_premium else free_limit,
                "remaining": (999 if is_premium else max(0, free_limit - entry.get("tasks", 0))),
            })
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        body = self._read_body()
        client_ip = get_client_ip(self)

        if path == "/command":
            command = body.get("command", "")
            channel = body.get("channel", "computer")
            if not command:
                self._send_json({"error": "no command provided"}, status=400)
                return
            result = self._process_command(command, channel, client_ip)
            self._send_json(result)
        elif path == "/telegram":
            command = body.get("command", body.get("text", ""))
            result = self._process_command(command, "telegram", client_ip)
            self._send_json(result)
        elif path == "/whatsapp":
            command = body.get("command", body.get("text", ""))
            result = self._process_command(command, "whatsapp", client_ip)
            self._send_json(result)
        elif path == "/upgrade":
            # Mark this IP as premium
            usage_data = load_usage()
            usage_data.setdefault("premium_ips", [])
            if client_ip not in usage_data["premium_ips"]:
                usage_data["premium_ips"].append(client_ip)
            save_usage(usage_data)
            self._send_json({"status": "upgraded", "ip": client_ip, "tier": "premium"})
        elif path == "/api-key":
            # Store an API key for this IP (BYOK — Bring Your Own Key)
            key_name = body.get("name", "default")
            key_value = body.get("key", "")
            if not key_value:
                self._send_json({"error": "no key provided"}, status=400)
                return
            keys_data = load_api_keys()
            keys_data.setdefault("keys", {})
            keys_data["keys"][client_ip] = {
                "name": key_name,
                "key": key_value,
                "added": now_str(),
            }
            save_api_keys(keys_data)
            self._send_json({"status": "key_stored", "ip": client_ip, "name": key_name})
        else:
            self._send_json({"error": "not found"}, status=404)

    def _get_status(self):
        skills = load_skills()
        records = load_records()
        prof_data = load_professions()
        categories = prof_data.get("categories", {})
        return {
            "status": "online",
            "time": now_str(),
            "master_agent": "👑 Master Agent",
            "sub_agents": list(ROUTES.keys()),
            "skills_total": len(skills.get("skills", [])),
            "skills_used": sum(s.get("success_count", 0) for s in skills.get("skills", [])),
            "departments_tracked": len(records.get("departments", {})),
            "tasks_completed": sum(
                d.get("metrics", {}).get("tasks_completed", 0)
                for d in records.get("departments", {}).values()
            ),
            "profession_system": {
                "total_professions": prof_data.get("total_professions", 0),
                "computer_based": prof_data.get("computer_based_professions", 0),
                "categories": len(categories),
                "category_list": [
                    {
                        "key": k,
                        "label": v.get("label", k),
                        "professions": len(v.get("professions", [])),
                        "master": f"{v.get('label', k).lower().replace(' ', '-')}-master",
                        "helpers": len(v.get("helpers", [])),
                    }
                    for k, v in categories.items()
                ],
            },
        }

    def _process_command(self, command, channel, client_ip=None):
        """Process a command: route, execute, track, respond.
        
        Checks daily quota for the client IP before processing.
        """
        # Determine client IP
        if client_ip is None:
            client_ip = get_client_ip(self)
        
        # Check daily quota
        allowed, remaining, status = check_daily_quota(client_ip)
        
        if not allowed and status == "free_tier_exceeded":
            result = {
                "status": "quota_exceeded",
                "master_agent": "👑 Master Agent",
                "free_tier_used": True,
                "daily_limit": 1,
                "message": "Bugünkü ücretsiz görev limitiniz doldu. Premium üye olarak sınırsız görev kullanın.",
                "upgrade_url": "/upgrade",
                "upgrade_info": {
                    "tier": "premium",
                    "price": "₺99/ay",
                    "benefits": ["Sınırsız görev", "Öncelikli erişim", "Tüm meslek kategorileri", "Priority processing"],
                },
            }
            update_memory(f"Quota exceeded for IP: {client_ip} — upgrade prompt shown")
            return result
        
        route = route_command(command)

        if route is None:
            result = {
                "status": "routed",
                "master_agent": "👑 Master Agent",
                "route": "master",
                "command": command,
                "message": "Command received. No matching sub-agent — Master Agent handling directly.",
                "suggestion": "Try: 'gelen mailleimi kontrol et', 'bugünkü randevularıma bak', 'sunum dosyası hazırla', 'bu alanda şirketler bul'",
            }
            log_department_activity("operations", command, "routed to master")
            update_memory(f"Command routed to master: '{command}' (channel: {channel})")
            return result

        # Execute workflow
        try:
            # Pass route info to profession workflow for better matching
            if route.get("workflow") == workflow_profession:
                result = route["workflow"](command, category_hint=route.get("sub_agent"))
            else:
                result = route["workflow"](command)
        except Exception as e:
            result = {
                "status": "error",
                "sub_agent": route["sub_agent"],
                "message": f"Workflow execution failed: {str(e)}",
            }
            update_skill(route["skill_id"], success=False, improvement=f"Execution error: {e}")
        else:
            result["status"] = "completed"
            result["command"] = command
            result["channel"] = channel
            update_skill(route["skill_id"], success=True)

        # Log activity
        log_department_activity(route["dept"], command, result.get("message", "completed"))
        update_memory(f"Command: '{command}' → {route['sub_agent']} — {result.get('message', 'done')}")

        # Increment usage count
        usage_data = load_usage()
        is_premium = client_ip in usage_data.get("premium_ips", [])
        daily_limit = 999 if is_premium else 1
        task_count = increment_usage(client_ip, command, result.get("message", ""))
        result["usage"] = {
            "tasks_today": task_count,
            "daily_limit": daily_limit,
            "remaining": 999 if is_premium else max(0, 1 - task_count),
            "tier": "premium" if is_premium else "free",
        }

        return result

    def _serve_upgrade_page(self):
        html = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Premium Üyelik — Master Agent</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.card { background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 40px; max-width: 500px; width: 90%; }
h1 { font-size: 28px; margin-bottom: 8px; background: linear-gradient(135deg, #ffd700, #ffaa00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.subtitle { color: #888; margin-bottom: 30px; }
.price { font-size: 48px; font-weight: 700; margin-bottom: 8px; }
.price span { font-size: 16px; color: #888; }
.benefits { list-style: none; margin: 20px 0; }
.benefits li { padding: 8px 0; color: #ccc; display: flex; align-items: center; gap: 10px; }
.benefits li::before { content: "✨"; }
.btn { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #1a1a2e; border: none; padding: 14px 30px; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; width: 100%; margin-top: 10px; transition: transform 0.2s; }
.btn:hover { transform: scale(1.02); }
.free-note { text-align: center; color: #666; margin-top: 20px; font-size: 13px; }
.back-link { text-align: center; margin-top: 15px; }
.back-link a { color: #666; text-decoration: none; font-size: 13px; }
.back-link a:hover { color: #999; }
</style>
</head>
<body>
<div class="card">
<h1>👑 Premium Üyelik</h1>
<div class="subtitle">Sınırsız görev, öncelikli erişim</div>
<div class="price">₺99<span>/ay</span></div>
<ul class="benefits">
<li>Sınırsız görev günde</li>
<li>Öncelikli işlem</li>
<li>Tüm meslek kategorileri</li>
<li>Priority processing</li>
<li>7/24 destek</li>
</ul>
<button class="btn" onclick="confirmUpgrade()">Premium'a geç</button>
<div class="free-note">Bugün ücretsiz görevinizi kullandınız. Premium ile sınırsız devam edin.</div>
<div class="back-link"><a href="/">← Geri dön</a></div>
</div>
<script>
async function confirmUpgrade() {
    const res = await fetch('/upgrade', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'upgraded') {
        alert('Premium üyeliğiniz aktif! Sınırsız görev kullanın.');
        window.location.href = '/';
    }
}
</script>
</body>
</html>"""
        self._send_html(html)
        self._send_html(html)

    def _serve_web_ui(self):
        html = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Master Agent — AI Assistant</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
.header { padding: 12px 20px; border-bottom: 1px solid #2a2a2a; display: flex; align-items: center; justify-content: space-between; background: #1a1a1a; }
.header-left { display: flex; align-items: center; gap: 12px; }
.header-icon { width: 36px; height: 36px; border-radius: 8px; background: linear-gradient(135deg, #ffd700, #ffaa00); display: flex; align-items: center; justify-content: center; font-size: 20px; }
.header-title { font-size: 16px; font-weight: 600; }
.header-subtitle { font-size: 12px; color: #666; }
.usage-badge { background: #2a2a2a; padding: 4px 12px; border-radius: 12px; font-size: 12px; color: #aaa; }
.usage-badge.premium { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #1a1a1a; font-weight: 600; }
.chat-area { flex: 1; overflow-y: auto; padding: 20px; max-width: 800px; width: 100%; margin: 0 auto; }
.message { margin-bottom: 16px; animation: fadeIn 0.3s; }
.message.user { display: flex; justify-content: flex-end; }
.message.user .bubble { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #1a1a1a; }
.message.bot { display: flex; justify-content: flex-start; }
.message.bot .bubble { background: #2a2a2a; color: #e0e0e0; }
.bubble { padding: 12px 16px; border-radius: 12px; max-width: 80%; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
.message.user .bubble { border-bottom-right-radius: 4px; }
.message.bot .bubble { border-bottom-left-radius: 4px; }
.suggestions { padding: 8px 20px; display: flex; gap: 8px; flex-wrap: wrap; max-width: 800px; width: 100%; margin: 0 auto; }
.suggestion { background: #1a1a1a; border: 1px solid #2a2a2a; color: #888; padding: 6px 14px; border-radius: 16px; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.suggestion:hover { background: #2a2a2a; color: #e0e0e0; border-color: #3a3a3a; }
.input-area { padding: 16px 20px 20px; border-top: 1px solid #2a2a2a; background: #1a1a1a; }
.input-wrapper { max-width: 800px; margin: 0 auto; display: flex; gap: 10px; align-items: flex-end; }
.input-box { flex: 1; background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 12px; padding: 12px 16px; color: #e0e0e0; font-size: 14px; resize: none; min-height: 44px; max-height: 120px; outline: none; transition: border-color 0.2s; }
.input-box:focus { border-color: #ffd700; }
.send-btn { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #1a1a1a; border: none; width: 44px; height: 44px; border-radius: 12px; cursor: pointer; font-size: 18px; display: flex; align-items: center; justify-content: center; transition: transform 0.2s; }
.send-btn:hover { transform: scale(1.05); }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.quota-exceeded { background: #2a1a1a; border: 1px solid #4a2a2a; padding: 16px; border-radius: 12px; margin-bottom: 16px; }
.quota-exceeded h3 { color: #ff6b6b; margin-bottom: 8px; }
.quota-exceeded p { color: #aaa; margin-bottom: 12px; }
.upgrade-btn { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #1a1a1a; border: none; padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>
</head>
<body>
<div class="header">
<div class="header-left">
<div class="header-icon">👑</div>
<div>
<div class="header-title">Master Agent</div>
<div class="header-subtitle">AI Assistant — 10 Meslek Kategori</div>
</div>
</div>
<div class="usage-badge" id="usage-badge">Loading...</div>
</div>
<div class="chat-area" id="chat">
<div class="message bot"><div class="bubble">Merhaba! Ben Master Agent. 764 mesleğe uyumlu sistem hazır. Bir görev ver — ben yetişeceğim. 💻💰⚕️⚖️📚🎬🏢🔧🔬🎨</div></div>
</div>
<div class="suggestions">
<span class="suggestion" onclick="sendCmd('gelen mailleimi kontrol et')">📧 Gelen mailini kontrol et</span>
<span class="suggestion" onclick="sendCmd('bugünkü randevularıma bak')">📅 Bugünkü randevular</span>
<span class="suggestion" onclick="sendCmd('sunum dosyası hazırla')">📊 Sunum hazırla</span>
<span class="suggestion" onclick="sendCmd('program yaz')">💻 Program yaz</span>
<span class="suggestion" onclick="sendCmd('haber yaz')">🎬 Haber yaz</span>
<span class="suggestion" onclick="sendCmd('avukat danış')">⚖️ Avukat danış</span>
</div>
<div class="input-area">
<div class="input-wrapper">
<textarea class="input-box" id="input" placeholder="Bir görev yazın... (Örn: 'fatura hazırla')" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendCmd(document.getElementById('input').value)}"></textarea>
<button class="send-btn" onclick="sendCmd(document.getElementById('input').value)">➤</button>
</div>
</div>
<script>
async function loadUsage() {
    const res = await fetch('/usage');
    const data = await res.json();
    const badge = document.getElementById('usage-badge');
    if (data.tier === 'premium') {
        badge.className = 'usage-badge premium';
        badge.textContent = '✨ Premium';
    } else {
        badge.textContent = data.remaining + ' ücretsiz görev remaining';
    }
}
function addMessage(text, isUser) {
    const chat = document.getElementById('chat');
    const msg = document.createElement('div');
    msg.className = 'message ' + (isUser ? 'user' : 'bot');
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    msg.appendChild(bubble);
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
}
async function sendCmd(cmd) {
    if (!cmd.trim()) return;
    addMessage(cmd, true);
    document.getElementById('input').value = '';
    const sendBtn = document.querySelector('.send-btn');
    sendBtn.disabled = true;
    try {
        const res = await fetch('/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: cmd, channel: 'web'})
        });
        const data = await res.json();
        if (data.status === 'quota_exceeded') {
            addMessage('Bugünkü ücretsiz görev limitiniz doldu. Premium üye olarak sınırsız görev kullanın.', false);
            const upgradeDiv = document.createElement('div');
            upgradeDiv.className = 'quota-exceeded';
            upgradeDiv.innerHTML = '<h3>⚠️ Ücretsiz Limiti Doldu</h3><p>Bugün 1 ücretsiz görev kullandınız. Premium ile sınırsız görev kullanın.</p><a href="/upgrade"><button class="upgrade-btn">✨ Premium Geç</button></a>';
            document.getElementById('chat').appendChild(upgradeDiv);
        } else {
            const msg = data.message || 'Görev tamamlandı.';
            addMessage(msg, false);
            if (data.usage) {
                addMessage('Kullanim: ' + data.usage.tasks_today + '/' + data.usage.daily_limit + ' bugün', false);
            }
        }
    } catch(e) {
        addMessage('Sunucu hatası. Tekrar deneyin.', false);
    }
    sendBtn.disabled = false;
    loadUsage();
}
loadUsage();
</script>
</body>
</html>"""
        self._send_html(html)

def main():
    parser = argparse.ArgumentParser(description="Master Agent — Phone Bridge")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(MEMORY_DIR, exist_ok=True)

    server = HTTPServer((args.host, args.port), BridgeHandler)
    print(f"👑 Master Agent — Phone Bridge")
    print(f"   Listening on http://{args.host}:{args.port}")
    print(f"   Web UI: http://{args.host}:{args.port}/")
    print(f"   Commands: POST /command, /telegram, /whatsapp")
    print(f"   Data: skills.json, department-records.json, memory/")
    print(f"   Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
