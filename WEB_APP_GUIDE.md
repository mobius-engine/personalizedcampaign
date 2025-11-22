# LinkedIn Leads Admin Panel - User Guide

## 🌐 Overview

The LinkedIn Leads Admin Panel is a web-based application for managing your LinkedIn leads database. It provides an intuitive interface for uploading CSV files, viewing leads, and tracking upload history.

## ✨ Features

- **📊 Dashboard**: View statistics including total leads, uploads, and unique companies
- **📤 CSV Upload**: 
  - Single file upload
  - Bulk upload (multiple files at once)
  - Drag-and-drop interface
  - Automatic deduplication after each upload
- **👥 Leads Management**: Browse all leads with pagination
- **📈 Upload History**: Track all CSV uploads with detailed statistics
- **🔄 Auto-Deduplication**: Automatically removes duplicates based on LinkedIn profile URL

## 🚀 Getting Started

### Local Development

1. **Set Database Password**:
   ```bash
   export DB_PASSWORD="your_database_password"
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application**:
   ```bash
   python3 main.py
   ```

4. **Access the Application**:
   Open your browser and navigate to: `http://localhost:8080`

### Production Deployment (Cloud Run)

The application is configured to deploy to Google Cloud Run automatically via GitHub Actions.

**Required Environment Variables**:
- `DB_HOST`: Cloud SQL instance IP address
- `DB_NAME`: Database name (default: `linkedin_leads_data`)
- `DB_USER`: Database user (default: `postgres`)
- `DB_PASSWORD`: Database password (store in Secret Manager)
- `SECRET_KEY`: Flask secret key for sessions

**Deploy via GitHub**:
1. Push changes to the `master` branch
2. GitHub Actions will automatically build and deploy to Cloud Run
3. Access your application at the Cloud Run URL

## 📋 Using the Admin Panel

### Dashboard

The dashboard provides an overview of your leads database:
- **Total Leads**: Number of unique leads in the database
- **Total Uploads**: Number of CSV files uploaded
- **Unique Companies**: Number of distinct companies
- **Recent Uploads**: List of the 10 most recent uploads with statistics

### Uploading CSV Files

#### Single File Upload
1. Navigate to **Upload CSV** from the menu
2. Click **Select Files** or drag and drop a CSV file
3. Click **Upload Files**
4. View the upload results with statistics

#### Bulk Upload
1. Navigate to **Upload CSV** from the menu
2. Select multiple CSV files at once (Ctrl/Cmd + Click)
3. Or drag and drop multiple files into the upload area
4. Click **Upload Files**
5. View results for each file

#### CSV Format Requirements

Your CSV file must include these columns:
- **Profile URL** (required) - LinkedIn profile URL (used for deduplication)
- First Name
- Last Name
- Headline
- Location
- Current Title
- Current Company
- Email Address
- Phone Number
- Active Project
- Notes
- Feedback

**Example CSV**:
```csv
First Name,Last Name,Profile URL,Email Address,Current Company
John,Doe,https://linkedin.com/in/johndoe,john@example.com,Acme Corp
```

### Viewing Leads

1. Navigate to **View Leads** from the menu
2. Browse leads with pagination (50 per page)
3. Click on email addresses to send emails
4. Click on "View" to open LinkedIn profiles

### Deduplication

Deduplication happens automatically after every CSV upload:
- **Unique Key**: LinkedIn Profile URL
- **Merge Strategy**: 
  - Keeps the oldest record (first inserted)
  - Preserves non-empty email, phone, notes, and feedback from duplicates
  - Updates other fields with latest data
- **Result**: You'll see a message like "Deduplication complete: Found 0 duplicates, removed 0 records"

## 🛠️ Database Schema

### `leads` Table
- `id`: Primary key
- `first_name`, `last_name`: Contact name
- `headline`: LinkedIn headline
- `location`: Geographic location
- `current_title`: Job title
- `current_company`: Company name
- `email_address`: Email (preserved during deduplication)
- `phone_number`: Phone (preserved during deduplication)
- `profile_url`: LinkedIn URL (unique constraint)
- `active_project`: Project assignment
- `notes`: Custom notes (preserved during deduplication)
- `feedback`: Feedback (preserved during deduplication)
- `created_at`: Record creation timestamp
- `updated_at`: Last update timestamp

### `upload_history` Table
- `id`: Primary key
- `filename`: Uploaded file name
- `upload_date`: Upload timestamp
- `rows_inserted`: Number of new records
- `rows_updated`: Number of updated records
- `rows_failed`: Number of failed records
- `status`: Upload status (success/partial/failed)
- `error_message`: Error details if any

## 🔧 Utilities

### Manual Deduplication
```bash
python3 run_dedupe.py <password>
```

### Verify Data
```bash
python3 verify_data.py <password>
```

### Upload from Google Drive
```bash
# List available CSVs
python3 csv_uploader.py --list

# Upload specific file
python3 csv_uploader.py --file-id <file_id> --password <password>

# Upload all CSVs
python3 upload_all_csvs.py <password>
```

## 🔒 Security Notes

- Always use strong passwords for database access
- Store `DB_PASSWORD` in Google Secret Manager for production
- Use HTTPS in production (Cloud Run provides this automatically)
- Consider adding authentication to the admin panel for production use

## 📞 Support

For issues or questions, contact the development team or check the repository documentation.

