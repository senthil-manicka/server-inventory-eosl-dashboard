# server_inventory.py
# Streamlit Server Inventory MVP — EOSL detection + contact/intimate actions
# Usage: streamlit run server_inventory.py

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import os
import io
import csv
import urllib.parse

st.set_page_config(page_title="Server Inventory — EOSL Dashboard", layout="wide")

### ---------- Utility functions ----------

SAMPLE_CSV_NAME = "sample_inventory.csv"
CHANGE_LOG = "change_log.csv"

REQUIRED_COLUMNS = [
    "hostname","asset_tag","environment","owner","team","location",
    "hardware_vendor","hardware_model","serial","os_name","os_version",
    "end_of_service_date","microcode_version","firmware_version",
    "last_audit","notes","owner_email"
]

VENDOR_PICKLIST = ["HPE","DELL","IBM","ORACLE","SUN","LENOVO","CISCO","OTHER"]

OS_FAMILIES = ["RHEL","SUSE","Ubuntu","Solaris","AIX","Windows Server","CentOS","Other"]

def ensure_sample_exists():
    if os.path.exists(SAMPLE_CSV_NAME):
        return
    sample = """hostname,asset_tag,environment,owner,team,location,hardware_vendor,hardware_model,serial,os_name,os_version,end_of_service_date,microcode_version,firmware_version,last_audit,notes,owner_email
web-01,AT-1001,prod,alice,web,dc1,HPE,DL560 Gen9,SN1001,Windows Server,2016,2028-12-31,2.45,FW1.2.3,2025-08-01,web app,alice@example.com
db-01,AT-1002,prod,bob,db,dc1,HPE,DL380 Gen10,SN1002,RHEL,7.9,2024-11-30,1.12,FW2.0.1,2025-07-01,urgent upgrade,bob@example.com
app-qa-03,AT-2001,qa,charlie,app,dc2,Custom,Custom-2U,SN1003,Ubuntu,18.04,2028-05-15,3.01,FW3.1.0,2025-09-01,scheduled,charlie@example.com
backup-01,AT-3001,prod,david,backup,dc2,HPE,DL360 Gen9,SN1004,CentOS,7.6,2023-06-30,,FW2.2.0,2024-12-01,missing microcode,david@example.com
edge-01,AT-4001,edge,eva,edge,site1,CISCO,XR-5000,SN1005,RouterOS,6.47,2025-10-01,4.0,FW4.0.1,2025-01-10,-,eva@example.com
oracle-db,AT-5001,prod,frank,db,dc3,ORACLE,Sun-X8,SN2001,Solaris,11.3,2024-10-15,1.0,FW1.0.0,2024-09-01,legacy,frank@example.com
aix-01,AT-6001,prod,grace,infra,dc1,IBM,P770,SN3001,AIX,7.1,2025-08-15,2.0,FW2.5,2025-02-10,planning migration,grace@example.com
old-win,AT-7001,prod,harry,app,dc1,DELL,R740,SN4001,Windows Server,2012,2023-01-01,1.1,FW1.1,2023-01-01,very old,harry@example.com
"""
    with open(SAMPLE_CSV_NAME, "w", newline="") as f:
        f.write(sample)

def parse_date_safe(s):
    if pd.isna(s) or str(s).strip()=="":
        return None
    for fmt in ("%Y-%m-%d","%d-%m-%Y","%Y/%m/%d","%d/%b/%Y","%b %d %Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except Exception:
            continue
    # Last resort try pandas
    try:
        return pd.to_datetime(s, errors="coerce").date()
    except Exception:
        return None

def load_inventory_from_file(filelike):
    df = pd.read_csv(filelike, dtype=str).fillna("")
    # Ensure required cols exist (add missing as blanks)
    for c in REQUIRED_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    # Normalize vendor names
    df["hardware_vendor"] = df["hardware_vendor"].str.upper().replace({"SUN":"ORACLE","ORACLE/SUN":"ORACLE"})
    # Parse EOSL date
    df["_end_of_service_date_parsed"] = df["end_of_service_date"].apply(parse_date_safe)
    return df

def compute_eosl_status(df, nearing_days=90):
    today = date.today()
    def status(row):
        d = row["_end_of_service_date_parsed"]
        if d is None:
            return "UNKNOWN"
        if d < today:
            return "EXPIRED"
        if d <= today + timedelta(days=nearing_days):
            return "NEARING"
        return "SUPPORTED"
    df["_EOSL_STATUS"] = df.apply(status, axis=1)
    return df

def flag_missing_firmware(df):
    df["_MISSING_FIRMWARE"] = df["firmware_version"].astype(str).str.strip()=="" 
    df["_MISSING_MICROCODE"] = df["microcode_version"].astype(str).str.strip()==""
    return df

def summarize_kpis(df):
    total = len(df)
    expired = (df["_EOSL_STATUS"]=="EXPIRED").sum()
    nearing = (df["_EOSL_STATUS"]=="NEARING").sum()
    missing_fw = (df["_MISSING_FIRMWARE"] | df["_MISSING_MICROCODE"]).sum()
    pct_expired = round((expired/total*100),1) if total>0 else 0
    return {"total":total,"expired":int(expired),"nearing":int(nearing),"missing_fw":int(missing_fw),"pct_expired":pct_expired}

def append_change_log(entry:dict):
    header = not os.path.exists(CHANGE_LOG)
    with open(CHANGE_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(entry.keys()))
        if header:
            writer.writeheader()
        writer.writerow(entry)

def get_last_action_for_host(hostname):
    if not os.path.exists(CHANGE_LOG):
        return None
    try:
        df = pd.read_csv(CHANGE_LOG, dtype=str)
        df = df[df["hostname"]==hostname]
        if df.empty: return None
        last = df.sort_values("timestamp", ascending=False).iloc[0]
        return dict(last)
    except Exception:
        return None

def make_mailto(owner_email, subject, body):
    if not owner_email:
        return None
    params = {"subject": subject, "body": body}
    return f"mailto:{owner_email}?{urllib.parse.urlencode(params)}"

### ---------- App State & Load ----------

ensure_sample_exists()

if "inventory_df" not in st.session_state:
    # initial load sample
    with open(SAMPLE_CSV_NAME, "r", encoding="utf-8") as f:
        st.session_state.inventory_df = load_inventory_from_file(f)
    st.session_state.inventory_df = compute_eosl_status(st.session_state.inventory_df, nearing_days=90)
    st.session_state.inventory_df = flag_missing_firmware(st.session_state.inventory_df)

### ---------- Sidebar: Controls ----------

st.sidebar.title("Server Inventory — Controls")
st.sidebar.markdown("Upload CSV or use sample. Adjust EOSL window and filters.")

uploaded = st.sidebar.file_uploader("Upload inventory CSV", type=["csv","txt"])
if uploaded is not None:
    try:
        st.session_state.inventory_df = load_inventory_from_file(uploaded)
        st.success("Inventory CSV loaded.")
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")

if st.sidebar.button("Reload sample inventory"):
    with open(SAMPLE_CSV_NAME, "r", encoding="utf-8") as f:
        st.session_state.inventory_df = load_inventory_from_file(f)
    st.info("Sample inventory loaded.")

# Parameters
near_days = st.sidebar.number_input("Nearing-EOSL days", min_value=7, max_value=365, value=90, step=7)
apply_btn = st.sidebar.button("Apply EOSL rules")

if apply_btn:
    st.session_state.inventory_df = compute_eosl_status(st.session_state.inventory_df, nearing_days=near_days)
    st.session_state.inventory_df = flag_missing_firmware(st.session_state.inventory_df)
    st.sidebar.success("Recomputed EOSL statuses.")

# Filters
st.sidebar.markdown("---")
st.sidebar.subheader("Filters")
vendors = st.sidebar.multiselect("Vendor", options=sorted(list(set(st.session_state.inventory_df["hardware_vendor"].str.upper().unique()) | set(VENDOR_PICKLIST))), default=[])
os_filter = st.sidebar.multiselect("OS family", options=OS_FAMILIES, default=[])
envs = st.sidebar.multiselect("Environment", options=sorted(st.session_state.inventory_df["environment"].unique()), default=[])
eosl_filter = st.sidebar.selectbox("EOSL status", options=["All","EXPIRED","NEARING","SUPPORTED","UNKNOWN"], index=0)
owner_search = st.sidebar.text_input("Owner / team contains")
missing_fw_only = st.sidebar.checkbox("Only show missing firmware/microcode", value=False)

st.sidebar.markdown("---")
st.sidebar.subheader("Bulk actions")
if st.sidebar.button("Export filtered CSV"):
    st.session_state.to_export = True
else:
    st.session_state.to_export = False

if st.sidebar.button("Bulk: export contact list (CSV)"):
    st.session_state.export_contacts = True
else:
    st.session_state.export_contacts = False

if st.sidebar.button("Bulk: mark ETH intimated (filtered)"):
    st.session_state.bulk_intimate = True
else:
    st.session_state.bulk_intimate = False

st.sidebar.markdown("---")
st.sidebar.caption("Change-log is appended to change_log.csv when you mark items as intimated.")

### ---------- Main layout ----------

st.title("📋 Server Inventory — EOSL Dashboard")
st.markdown("Detect EXPIRED/NEARING assets, check firmware/microcode gaps, and take actions (Contact owner / Mark intimated).")

df = st.session_state.inventory_df.copy()

# Apply computed fields to df if missing
if "_EOSL_STATUS" not in df.columns:
    df = compute_eosl_status(df, nearing_days=near_days)
if "_MISSING_FIRMWARE" not in df.columns:
    df = flag_missing_firmware(df)

# Apply filters
def apply_filters(df):
    q = df
    if vendors:
        q = q[q["hardware_vendor"].isin([v.upper() for v in vendors])]
    if os_filter:
        q = q[q["os_name"].str.contains("|".join([x for x in os_filter if x!="Other"]), case=False, na=False) | (q["os_name"].str.strip()=="" and "Other" in os_filter)]
    if envs:
        q = q[q["environment"].isin(envs)]
    if eosl_filter and eosl_filter!="All":
        q = q[q["_EOSL_STATUS"]==eosl_filter]
    if owner_search:
        q = q[q["owner"].str.contains(owner_search, case=False, na=False) | q["team"].str.contains(owner_search, case=False, na=False)]
    if missing_fw_only:
        q = q[(q["_MISSING_FIRMWARE"]) | (q["_MISSING_MICROCODE"])]
    return q

filtered = apply_filters(df)

# KPIs row
kpis = summarize_kpis(df)
col1, col2, col3, col4, col5 = st.columns([1,1,1,1,1])
col1.metric("Total servers", kpis["total"])
col2.metric("EXPIRED", kpis["expired"])
col3.metric("NEARING", kpis["nearing"])
col4.metric("Missing firmware/microcode", kpis["missing_fw"])
col5.metric("% Expired", f"{kpis['pct_expired']}%")

st.markdown("---")

# Export filtered if requested
if st.session_state.get("to_export", False):
    to_download = filtered.copy()
    to_download = to_download.drop(columns=[c for c in to_download.columns if c.startswith("_")], errors="ignore")
    csv_bytes = to_download.to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered CSV", data=csv_bytes, file_name="filtered_inventory.csv", mime="text/csv")

# Export contacts (bulk)
if st.session_state.get("export_contacts", False):
    contacts = filtered[["hostname","owner","owner_email","_EOSL_STATUS"]].copy()
    contacts["owner_email"] = contacts["owner_email"].fillna("")
    csvb = contacts.to_csv(index=False).encode("utf-8")
    st.download_button("Download contact list (CSV)", data=csvb, file_name="contacts_filtered.csv", mime="text/csv")
    st.success("Contact list ready for download.")
    st.session_state.export_contacts = False

# Bulk intimate action
if st.session_state.get("bulk_intimate", False):
    count = 0
    actor = st.text_input("Your name for audit log (actor)", value="operator")
    if st.button("Confirm bulk mark intimated for filtered rows"):
        for _, row in filtered.iterrows():
            entry = {
                "timestamp": datetime.now().isoformat(),
                "hostname": row["hostname"],
                "action": "INTIMATED",
                "actor": actor,
                "details": f"Bulk intimated via UI. EOSL status: {row.get('_EOSL_STATUS','')}"
            }
            append_change_log(entry)
            count += 1
        st.success(f"{count} rows appended to change_log.csv")
    st.session_state.bulk_intimate = False

# Show filtered table with highlights
st.subheader(f"Inventory ({len(filtered)} rows shown)")

def color_row(r):
    stl = ""
    if r["_EOSL_STATUS"]=="EXPIRED":
        stl = "background-color: #ffcccc"  # light red
    elif r["_EOSL_STATUS"]=="NEARING":
        stl = "background-color: #ffe5cc"  # light orange
    elif r["_MISSING_FIRMWARE"] or r["_MISSING_MICROCODE"]:
        stl = "background-color: #fff7cc"  # pale yellow
    return [stl]*len(r)

display_cols = ["hostname","hardware_vendor","hardware_model","os_name","os_version","end_of_service_date","_EOSL_STATUS","owner","owner_email","firmware_version","microcode_version","last_audit","notes"]
# Prepare display df
disp = filtered.copy()
# Ensure col order exists
for c in display_cols:
    if c not in disp.columns:
        disp[c] = ""
disp_show = disp[display_cols].reset_index(drop=True)

# show styled table
try:
    styled = disp_show.style.apply(color_row, axis=1)
    st.dataframe(styled, use_container_width=True)
except Exception:
    st.dataframe(disp_show, use_container_width=True)

# Row detail & actions
st.markdown("---")
st.subheader("Row detail & Actions")
selected_host = st.text_input("Enter hostname to view details (or pick from table above)", "")
if selected_host:
    row = df[df["hostname"]==selected_host]
    if row.empty:
        st.warning("Hostname not found in inventory.")
    else:
        r = row.iloc[0].to_dict()
        # display fields
        st.markdown("### Server details")
        left, right = st.columns(2)
        with left:
            st.write("**Hostname**", r.get("hostname",""))
            st.write("**Asset tag**", r.get("asset_tag",""))
            st.write("**Environment**", r.get("environment",""))
            st.write("**Owner / Team**", f"{r.get('owner','')} / {r.get('team','')}")
            st.write("**Location**", r.get("location",""))
            st.write("**Vendor / Model**", f"{r.get('hardware_vendor','')} / {r.get('hardware_model','')}")
            st.write("**Serial**", r.get("serial",""))
        with right:
            st.write("**OS**", f"{r.get('os_name','')} {r.get('os_version','')}")
            st.write("**EOSL Date**", r.get("end_of_service_date",""))
            st.write("**EOSL Status**", r.get("_EOSL_STATUS",""))
            st.write("**Firmware**", r.get("firmware_version",""))
            st.write("**Microcode**", r.get("microcode_version",""))
            st.write("**Last audit**", r.get("last_audit",""))
            st.write("**Notes**", r.get("notes",""))
        st.markdown("---")
        # Show last action
        last_act = get_last_action_for_host(selected_host)
        if last_act:
            st.info(f"Last action: {last_act.get('action')} by {last_act.get('actor')} at {last_act.get('timestamp')}")
            st.write("Details:", last_act.get("details",""))
        else:
            st.write("No prior actions recorded for this host.")

        st.markdown("### Actions")
        actor_name = st.text_input("Your name (for audit entries)", value="operator_name", key=f"actor_{selected_host}")
        # Contact owner: prepare mailto
        owner_email = r.get("owner_email","")
        subj = f"Action required: {selected_host} — EOSL {r.get('_EOSL_STATUS','')}"
        body = f"""Hi {r.get('owner','')},

This message is regarding server {selected_host} (asset {r.get('asset_tag','')}):

- Vendor/Model: {r.get('hardware_vendor','')} {r.get('hardware_model','')}
- OS: {r.get('os_name','')} {r.get('os_version','')}
- EOSL / End-of-Service-Date: {r.get('end_of_service_date','')} (Status: {r.get('_EOSL_STATUS','')})
- Firmware: {r.get('firmware_version','') or 'MISSING'}
- Microcode: {r.get('microcode_version','') or 'MISSING'}

Recommended actions:
1) Validate workloads and schedule replacement/upgrade.
2) If already actioned, update inventory and notify ops.

Regards,
{actor_name}
"""
        mailto = make_mailto(owner_email, subj, body)
        if owner_email:
            if st.button("Contact Owner (open mail client)"):
                if mailto:
                    st.markdown(f"[Open mail client]({mailto})")
                else:
                    st.error("Failed to form mailto link.")
        else:
            st.warning("Owner email missing — cannot open mail client. Consider exporting contact list and following up manually.")

        # Mark intimated
        if st.button("Mark intimated (append audit)"):
            entry = {
                "timestamp": datetime.now().isoformat(),
                "hostname": selected_host,
                "action": "INTIMATED",
                "actor": actor_name,
                "details": f"Intimated owner {r.get('owner_email','')} via UI. EOSL status: {r.get('_EOSL_STATUS','')}"
            }
            append_change_log(entry)
            st.success("Appended to change_log.csv")

        # Create ticket (PoC -> export small ticket CSV)
        if st.button("Create ticket export (CSV line)"):
            ticket = {
                "hostname": selected_host,
                "summary": f"Replace / upgrade {selected_host} — EOSL {r.get('_EOSL_STATUS','')}",
                "description": body,
                "owner": r.get("owner",""),
                "owner_email": r.get("owner_email",""),
                "priority": "High" if r.get("_EOSL_STATUS","")=="EXPIRED" else "Medium"
            }
            # prepare single-row csv for download
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=list(ticket.keys()))
            writer.writeheader()
            writer.writerow(ticket)
            st.download_button("Download ticket CSV", data=out.getvalue().encode("utf-8"), file_name=f"ticket_{selected_host}.csv")

# Change-log viewer
st.markdown("---")
st.subheader("Change log (recent actions)")
if os.path.exists(CHANGE_LOG):
    try:
        cl = pd.read_csv(CHANGE_LOG, dtype=str)
        st.dataframe(cl.sort_values("timestamp", ascending=False).head(200), use_container_width=True)
    except Exception as e:
        st.error(f"Could not read change log: {e}")
else:
    st.write("No change_log.csv found yet. Actions will append rows here.")

# Simple charts
st.markdown("---")
st.subheader("Quick Charts")
chart_df = df.copy()
try:
    top_models = chart_df["hardware_model"].value_counts().head(10).reset_index()
    top_models.columns = ["model","count"]
    st.bar_chart(top_models.set_index("model")["count"])
except Exception:
    st.write("Not enough data for model chart.")

try:
    env_pie = chart_df["environment"].value_counts()
    st.write("Environment distribution")
    st.dataframe(env_pie.reset_index().rename(columns={"index":"environment", "environment":"count"}))
except Exception:
    pass

st.markdown("---")
st.caption("Local PoC — no external email sent. Mailto links open your default mail client. Change log appended to change_log.csv.")
