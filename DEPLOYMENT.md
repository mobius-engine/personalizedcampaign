# Cloud Run Deployment Setup

This document describes how to set up automatic deployment to Google Cloud Run using GitHub Actions.

## Prerequisites

1. A Google Cloud Platform (GCP) project
2. GitHub repository with appropriate permissions
3. GCP billing enabled

## GCP Setup

### 1. Enable Required APIs

```bash
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable iamcredentials.googleapis.com
```

### 2. Create Artifact Registry Repository

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export SERVICE_NAME="personalizedcampaign"

gcloud artifacts repositories create $SERVICE_NAME \
    --repository-format=docker \
    --location=$REGION \
    --project=$PROJECT_ID
```

### 3. Set Up Workload Identity Federation

Create a Workload Identity Pool:

```bash
gcloud iam workload-identity-pools create "github-pool" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --display-name="GitHub Actions Pool"
```

Create a Workload Identity Provider:

```bash
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --workload-identity-pool="github-pool" \
    --display-name="GitHub Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --issuer-uri="https://token.actions.githubusercontent.com"
```

### 4. Create Service Account

```bash
gcloud iam service-accounts create github-actions-sa \
    --display-name="GitHub Actions Service Account" \
    --project="${PROJECT_ID}"
```

### 5. Grant Permissions to Service Account

```bash
export SA_EMAIL="github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Cloud Run Admin
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.admin"

# Artifact Registry Writer
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.writer"

# Service Account User (to deploy as the service account)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser"
```

### 6. Allow GitHub Actions to Impersonate Service Account

```bash
export REPO="mobius-engine/personalizedcampaign"

gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

**Note:** Replace `PROJECT_NUMBER` with your actual GCP project number. Get it with:
```bash
gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
```

## GitHub Secrets Configuration

Add the following secrets to your GitHub repository:
(Settings → Secrets and variables → Actions → New repository secret)

### Required Secrets:

1. **GCP_PROJECT_ID**
   - Your GCP project ID
   - Example: `my-project-123456`

2. **WIF_PROVIDER**
   - Full resource name of the Workload Identity Provider
   - Format: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
   - Get it with:
     ```bash
     gcloud iam workload-identity-pools providers describe github-provider \
       --workload-identity-pool=github-pool \
       --location=global \
       --format="value(name)"
     ```

3. **WIF_SERVICE_ACCOUNT**
   - Email of the service account
   - Format: `github-actions-sa@PROJECT_ID.iam.gserviceaccount.com`

## Deployment

Once configured, the deployment will automatically trigger on:
- Push to `main` or `master` branch
- Manual workflow dispatch from GitHub Actions tab

## Verify Deployment

After deployment, get your service URL:

```bash
gcloud run services describe personalizedcampaign \
    --platform managed \
    --region us-central1 \
    --format 'value(status.url)'
```

## Troubleshooting

### Permission Denied Errors
- Verify service account has all required roles
- Check Workload Identity Federation is properly configured
- Ensure GitHub repository name matches exactly in the IAM binding

### Image Push Failures
- Verify Artifact Registry repository exists
- Check service account has `artifactregistry.writer` role

### Deployment Failures
- Check Cloud Run service logs in GCP Console
- Verify Dockerfile builds successfully locally
- Ensure PORT environment variable is set correctly (8080)

