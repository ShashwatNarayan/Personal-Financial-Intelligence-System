# Privacy Policy
**Personal Financial Intelligence System**
Last updated: June 2026

---

## 1. Who We Are

This Privacy Policy applies to the Personal Financial Intelligence System ("the Platform", "we", "us"), operated by **Shashwat Narayan**, an individual developer based in Jawahar Nagar, Shameerpet Mandal, Hyderabad, Telangana 500078, India.

Contact for privacy matters: **shashwatn2802@gmail.com**

---

## 2. What This Policy Covers

This policy explains what personal and financial data we collect, how we use it, who we share it with (including third-party AI services), how long we keep it, and your rights under India's Digital Personal Data Protection Act, 2023 ("DPDP Act") and the Information Technology Act, 2000.

By using this Platform, you consent to the practices described in this policy.

---

## 3. What Data We Collect

### 3a. Account Data
When you register, we collect:
- **Email address** — used to identify your account and for password reset
- **Password** — stored only as a one-way cryptographic hash (bcrypt/Werkzeug). Your plaintext password is never stored.
- **Account creation timestamp** and **last login timestamp**

We do not collect your name, phone number, address, date of birth, or any government ID.

### 3b. Financial Transaction Data
When you upload a bank statement, we extract and store the following from your statement:
- Transaction date
- Transaction description (truncated to 200 characters)
- Merchant / payee name (extracted from description)
- Transaction amount (INR)
- Transaction type (debit or credit)
- Assigned spending category (e.g. Food & Dining, Transport)
- Merchant type classification (merchant / person / platform)
- Confidence level of categorization
- Reimbursement status

We also store:
- A SHA-256 hash of the uploaded file (to prevent duplicate uploads)
- The original filename of your uploaded statement
- A record of any category corrections you make, including the old and new category

**This is sensitive financial data.** We treat it with the highest level of care.

### 3c. Usage Data (Logs)
Our server logs may capture:
- Aggregate financial summaries (total spend, monthly averages) for debugging
- Merchant names when you manually correct a transaction category
- Full error tracebacks if a processing error occurs (which may incidentally contain transaction data)
- Your uploaded statement filename (which may contain your bank account number)

These logs are stored on our hosting provider's infrastructure (Render) and are not shared externally.

### 3d. Session Data
We use a browser session cookie (named `session`) to keep you logged in. This cookie:
- Contains only your internal user ID and a session token — no financial data
- Is signed (tamper-proof) but not encrypted
- Expires when you close your browser (we do not use persistent "remember me" cookies)
- Is protected by CSRF tokens on all form submissions

---

## 4. How We Use Your Data

| Purpose | Data Used | Legal Basis |
|---|---|---|
| Providing the service (parsing, categorizing, displaying your transactions) | Financial transaction data | Consent (DPDP Act) |
| AI-powered query feature (answering natural language questions about your spending) | See Section 5 | Consent — explicit disclosure below |
| Preventing duplicate uploads | SHA-256 file hash | Legitimate interest |
| Security and fraud prevention | Session data, login timestamps | Legitimate interest |
| Debugging and error resolution | Server logs | Legitimate interest |
| Improving categorization accuracy per user | Entity memory (merchant→category mappings) | Consent |

We do **not** use your data for advertising, profiling for third parties, or any purpose not listed above.

---

## 5. AI Feature — What Gets Sent to Google

⚠️ **This section requires your careful attention before using the AI query feature.**

The Platform includes an AI assistant that lets you ask natural language questions about your spending (e.g. "How much did I spend on food last month?"). This feature uses **Google's Gemini API**.

**What is sent to Google, depending on your question type:**

| Question Type | Data Sent to Google | Example |
|---|---|---|
| Specific data queries ("how much did I spend on food?") | Your question + up to 20 actual transaction rows (merchant names, amounts, dates, categories) | "Food & Dining, Swiggy, ₹340, 2026-05-01" |
| Opinion/analysis questions ("what do you think of my spending?") | Your question + aggregated summary only (total spend, avg monthly, top 3 category totals — no individual transactions) | "Total: ₹4.4L, Avg monthly: ₹36k, Top: Transfer/P2P, Food, Shopping" |
| Subscription questions ("how much do I spend on subscriptions?") | **Nothing — processed entirely on our servers, no data sent to Google** | — |

**⚠️ Critical disclosure — Free Tier Terms:**
We currently use Google's free tier Gemini API. Under Google's free tier terms, prompts and responses submitted to the API **may be used by Google to improve their products and machine learning models**, and may be subject to human review by Google. This means transaction data included in AI queries (see table above) **may be seen or used by Google**.

If this is unacceptable to you, **do not use the AI query feature**. All other features of the Platform (categorization, charts, subscriptions, anomaly detection) operate entirely on our servers and do not send your data to Google.

We plan to upgrade to a paid Gemini API tier in the future, which eliminates Google's use of data for model training.

---

## 6. Third Parties We Share Data With

We do not sell your data. We share data only with the following infrastructure providers:

| Provider | Purpose | Data Shared | Location |
|---|---|---|---|
| **Neon** (PostgreSQL) | Database storage | All account and transaction data | Singapore (AWS ap-southeast-1) |
| **Render** | Application hosting | All data processed by the app | United States |
| **Google (Gemini API)** | AI query feature only | See Section 5 | United States / Global |
| **Google Fonts / CDN** | Font and UI loading in your browser | Your IP address and browser info (via browser request) | United States |
| **Plotly CDN, Bootstrap CDN, Tailwind CDN** | UI libraries loaded in your browser | Your IP address and browser info (via browser request) | Various |

### Cross-Border Data Transfers
Your data is stored on servers in **Singapore** (Neon) and processed on servers in the **United States** (Render, Google). By using this Platform, you consent to this cross-border transfer of your personal and financial data.

---

## 7. Data Retention

| Data Type | Retention Period |
|---|---|
| Account data (email, password hash) | Until you delete your account |
| Transaction data | Until you delete your account or request erasure |
| Entity memory (learned merchant categories) | Until you delete your account |
| Category correction history | Until you delete your account |
| Upload log (filename, file hash) | Until you delete your account |
| Server logs | As per Render's log retention policy (typically 7–30 days) |
| Uploaded bank statement file | Deleted immediately after parsing (within seconds). Not stored permanently. |

---

## 8. Your Rights Under DPDP Act 2023

As a data principal under India's DPDP Act, you have the right to:

- **Access** — request a copy of all personal data we hold about you
- **Correction** — request correction of inaccurate data
- **Erasure** — request deletion of all your data ("right to be forgotten")
- **Grievance redressal** — lodge a complaint with us directly
- **Withdraw consent** — withdraw consent for data processing at any time (this will prevent you from using the Platform)
- **Nominate** — nominate another person to exercise rights on your behalf in the event of death or incapacity

**To exercise any of these rights**, email us at **shashwatn2802@gmail.com** with the subject line "DPDP Data Request". We will respond within 30 days.

**Note on account deletion:** There is currently no self-service account deletion button in the app. To request full deletion of your account and all associated data, please email us at the address above. We will permanently delete all your data within 7 business days.

---

## 9. Data Security

We implement the following security measures:
- Passwords stored as cryptographic hashes only (never plaintext)
- Database connections encrypted in transit (TLS/SSL)
- Session cookies are CSRF-protected and signed
- Separate read-only database role used for AI queries (cannot modify your data)
- Deduplication fingerprints prevent duplicate data injection

**Known limitations:** Our session cookies are not currently flagged as `Secure` (HTTPS-only), meaning they could theoretically be transmitted over unencrypted HTTP connections. We recommend always accessing the Platform via HTTPS.

---

## 10. Children's Privacy

This Platform is not intended for individuals under the age of 18. We do not knowingly collect data from minors. If you believe a minor has created an account, please contact us and we will delete the account immediately.

---

## 11. Changes to This Policy

We may update this Privacy Policy as the Platform evolves. We will notify you of material changes by updating the "Last updated" date at the top of this document. Continued use of the Platform after changes constitutes acceptance of the updated policy.

---

## 12. Grievance Officer

In accordance with the Information Technology Act, 2000 and DPDP Act, 2023:

**Grievance Officer:** Shashwat Narayan
**Email:** shashwatn2802@gmail.com
**Address:** Jawahar Nagar, Shameerpet Mandal, Hyderabad, Telangana 500078, India
**Response time:** Within 30 days of receiving a complaint
