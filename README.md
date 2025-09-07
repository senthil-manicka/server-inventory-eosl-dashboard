# Server Inventory — EOSL Dashboard (MVP)

📋 A lightweight Streamlit app to track **End-of-Service-Life (EOSL)** servers, hardware, and operating systems.  
Built for IT operations teams to quickly identify risk, highlight missing firmware/microcode, and take **actions** such as contacting owners or marking items as intimated.

---

## ✨ Features
- Upload server inventory CSV or use included sample
- Highlight EOSL status:
  - **EXPIRED** (EOSL date < today)
  - **NEARING** (within configurable X days, default 90)
  - **SUPPORTED**
- Flag missing firmware or microcode
- KPI cards for total, expired, nearing, and missing items
- Filters by vendor, OS, environment, owner/team
- Row detail view with:
  - **Contact owner** (prefilled mailto)
  - **Mark intimated** (logs to `change_log.csv`)
  - **Create ticket export** (CSV line for ticketing systems)
- Bulk actions:
  - Export filtered inventory
  - Export owner contact list
  - Bulk mark items as intimated
- Change-log (`change_log.csv`) for audit trail
- Quick charts (top hardware models, environment distribution)

---

## 📂 Repository Structure
