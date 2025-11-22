# Personalized Campaign - LinkedIn Leads Database

This project manages LinkedIn leads data with automatic CSV uploads from Google Drive to Cloud SQL.

## 🗄️ Database

**Cloud SQL Instance:** `linkedin-leads-db`
- **Type:** PostgreSQL 17
- **Database:** `linkedin_leads_data`
- **Location:** us-central1-f
- **IP:** 35.193.184.122

### Tables

#### `leads`
Stores LinkedIn lead information with the following columns:
- `id` - Auto-incrementing primary key
- `first_name`, `last_name` - Contact name
- `headline` - LinkedIn headline
- `location` - Geographic location
- `current_title` - Job title
- `current_company` - Company name
- `email_address` - Email (if available)
- `phone_number` - Phone (if available)
- `profile_url` - LinkedIn profile URL (unique)
- `active_project` - Current project/campaign
- `notes` - Additional notes
- `feedback` - Feedback from outreach
- `created_at`, `updated_at` - Timestamps

#### `upload_history`
Tracks CSV upload history with statistics

## 📁 Google Drive Integration

**Folder:** CSV's
- **ID:** `1wdE3pA0JzTi831Yn3QeDwHDmbo5eNFc3`
- **Service Accounts with Access:**
  - `algolia@jobs-data-linkedin.iam.gserviceaccount.com`
  - `gmail-processor@jobs-data-linkedin.iam.gserviceaccount.com`
  - `dataengineer-dev@jobs-data-linkedin.iam.gserviceaccount.com`

## 🚀 Usage

### Setup Database (First Time Only)

```bash
python3 setup_database.py <database_password>
```

### List Available CSV Files

```bash
python3 csv_uploader.py --list
```

### Upload Latest CSV

```bash
python3 csv_uploader.py --password <database_password>
```

### Upload Specific CSV by File ID

```bash
python3 csv_uploader.py --password <database_password> --file-id <google_drive_file_id>
```

### Verify Data

```bash
python3 verify_data.py <database_password>
```

## 🔧 Features

- **Automatic Upsert:** Updates existing leads based on `profile_url`, inserts new ones
- **Smart Field Merging:** Preserves existing email/phone/notes if new data is empty
- **Upload Tracking:** Records all uploads with statistics in `upload_history` table
- **Google Drive Integration:** Directly reads CSVs from shared Google Drive folder

## 📋 CSV Format

The uploader expects CSVs with these columns:
- First Name
- Last Name
- Headline
- Location
- Current Title
- Current Company
- Email Address
- Phone Number
- Profile URL (required, used as unique identifier)
- Active Project
- Notes
- Feedback

## 🔐 Security

- Database password should be stored in environment variable `DB_PASSWORD`
- Service account keys are stored locally in `~/Downloads/`
- IP whitelist configured for database access

## 🌐 Cloud Run Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for instructions on deploying to Cloud Run with GitHub Actions.

## 📦 Dependencies

```bash
pip install psycopg2-binary google-auth google-api-python-client
```

## 🎯 Next Steps

1. Set up automated CSV uploads via Cloud Functions or Cloud Run scheduled jobs
2. Build API endpoints to query leads data
3. Create personalized campaign generation logic
4. Integrate with email/messaging platforms

