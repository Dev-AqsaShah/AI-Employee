# Gmail API Setup Guide

## Step 1: Create a Google Cloud Project

1. Go to https://console.cloud.google.com
2. Click **New Project** → name it `AI-Employee`
3. Select the project

## Step 2: Enable the Gmail API

1. Go to **APIs & Services → Library**
2. Search for **Gmail API**
3. Click **Enable**

## Step 3: Create OAuth Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth Client ID**
3. Application type: **Desktop app**
4. Name: `AI Employee`
5. Click **Create**
6. Download the JSON file
7. Save it as `credentials/gmail_credentials.json` in the project root

## Step 4: Configure OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. User Type: **External** (for personal Gmail)
3. Fill in app name: `AI Employee`
4. Add your Gmail address as a test user
5. Scopes: add `https://www.googleapis.com/auth/gmail.readonly`

## Step 5: Install Dependencies

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

Or with uv:
```bash
uv pip install google-auth google-auth-oauthlib google-api-python-client
```

## Step 6: Run the Watcher (First Time Auth)

```bash
python watchers/gmail_watcher.py
```

A browser window will open for OAuth consent. After approving, the token is saved to `credentials/gmail_token.json` and subsequent runs won't need the browser.

## Security Notes

- `credentials/` is in `.gitignore` — never commit credentials
- `gmail_token.json` gives read-only Gmail access
- To revoke access: go to https://myaccount.google.com/permissions
