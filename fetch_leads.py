import csv, json, os, smtplib, requests
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

FB_PAGE_TOKEN = os.environ["FB_PAGE_TOKEN"]
FB_PAGE_ID    = os.environ["FB_PAGE_ID"]
FB_APP_ID     = os.environ["FB_APP_ID"]
FB_APP_SECRET = os.environ["FB_APP_SECRET"]
FB_FORM_IDS   = os.environ["FB_FORM_IDS"].split(",")
GMAIL_USER    = os.environ["GMAIL_USER"]
GMAIL_PASS    = os.environ["GMAIL_PASS"]
EMAIL_TO      = os.environ["EMAIL_TO"]
BASE_URL      = "https://graph.facebook.com/v19.0"

def get_page_token():
    try:
        r = requests.get(f"{BASE_URL}/{FB_PAGE_ID}", params={"fields": "access_token", "access_token": FB_PAGE_TOKEN}, timeout=15)
        t = r.json().get("access_token")
        return t if t else FB_PAGE_TOKEN
    except Exception:
        return FB_PAGE_TOKEN

def get_yesterday_range():
    bkk = timezone(timedelta(hours=7))
    y = datetime.now(bkk) - timedelta(days=1)
    start = y.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = y.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(start.timestamp()), int(end.timestamp())

def fetch_leads(form_id, token, since, until):
    leads, url = [], f"{BASE_URL}/{form_id}/leads"
    params = {
        "access_token": token,
        "filtering": json.dumps([
            {"field": "time_created", "operator": "GREATER_THAN", "value": since},
            {"field": "time_created", "operator": "LESS_THAN",    "value": until}
        ]),
        "limit": 200,
        "fields": "id,created_time,field_data,ad_name,adset_name,campaign_name"
    }
    while url:
        data = requests.get(url, params=params, timeout=30).json()
        if "error" in data:
            print(f"API error: {data['error']}")
            return None
        for lead in data.get("data", []):
            row = {"lead_id": lead.get("id"), "created_time": lead.get("created_time"),
                   "ad_name": lead.get("ad_name",""), "adset_name": lead.get("adset_name",""),
                   "campaign_name": lead.get("campaign_name","")}
            for f in lead.get("field_data", []):
                row[f["name"]] = ", ".join(f.get("values", []))
            leads.append(row)
        url    = data.get("paging", {}).get("next")
        params = {}
    return leads

def save_csv(leads, date_str, form_id):
    path, keys = f"/tmp/{date_str}_{form_id}.csv", []
    for lead in leads:
        for k in lead:
            if k not in keys: keys.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(leads)
    return path

def send_email(files, date_str, total):
    msg = MIMEMultipart()
    msg["From"], msg["To"] = GMAIL_USER, EMAIL_TO
    msg["Subject"] = f"Facebook Leads Jaymart — {date_str} ({total} leads)"
    msg.attach(MIMEText(
        f"สวัสดีครับ\n\nรายงาน Facebook Lead Ads ประจำวัน {date_str}\n"
        f"ยอด Lead ทั้งหมด: {total} รายการ\nไฟล์แนบ: {len(files)} ไฟล์\n\n"
        f"ระบบส่งอัตโนมัติทุกเที่ยงคืน", "plain", "utf-8"))
    for path in files:
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(path)}")
        msg.attach(part)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.sendmail(GMAIL_USER, EMAIL_TO, msg.as_string())

def send_alert(error):
    try:
        msg = MIMEMultipart()
        msg["From"], msg["To"] = GMAIL_USER, GMAIL_USER
        msg["Subject"] = "[ALERT] Facebook Leads Script ล้มเหลว"
        msg.attach(MIMEText(f"เกิดข้อผิดพลาด:\n\n{error}\n\nกรุณา refresh token ใน Graph API Explorer", "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    except Exception as e:
        print(f"Alert failed: {e}")

def main():
    bkk       = timezone(timedelta(hours=7))
    yesterday = (datetime.now(bkk) - timedelta(days=1)).strftime("%Y-%m-%d")
    since, until = get_yesterday_range()
    print(f"Fetching leads for {yesterday}")
    token = get_page_token()
    files, total = [], 0
    for form_id in FB_FORM_IDS:
        leads = fetch_leads(form_id, token, since, until)
        if leads is None:
            send_alert(f"Token error on form {form_id}")
            return
        print(f"  Form {form_id}: {len(leads)} leads")
        total += len(leads)
        if leads:
            files.append(save_csv(leads, yesterday, form_id))
    if files:
        send_email(files, yesterday, total)
        print(f"Done — {total} leads sent to {EMAIL_TO}")
    else:
        print(f"No leads for {yesterday}")

main()
