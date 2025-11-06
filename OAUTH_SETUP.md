# OAuth 2.0 Setup Guide for Google Slides API

This guide will help you set up OAuth 2.0 authentication to use your personal Google account for slide generation.

## Step 1: Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to **APIs & Services** → **Credentials**
4. Click **+ CREATE CREDENTIALS** → **OAuth client ID**
5. If prompted, configure the OAuth consent screen:
   - User Type: **External** (for personal Gmail accounts)
   - App name: "STI Slides Generator"
   - User support email: Your email
   - Developer contact: Your email
   - Click **Save and Continue**
   - Skip Scopes (we'll add them programmatically)
   - Add test users if needed (your email)
   - Click **Save and Continue**
6. Create OAuth client:
   - Application type: **Desktop app**
   - Name: "STI Slides Generator Desktop"
   - Click **Create**
7. **Copy the Client ID and Client Secret**

## Step 2: Configure in config.py

Open `config.py` and set:

```python
GOOGLE_OAUTH_CLIENT_ID = "YOUR_CLIENT_ID_HERE"
GOOGLE_OAUTH_CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"
GOOGLE_USE_OAUTH = True  # Already set
```

## Step 3: First-Time Authorization

When you run slide generation for the first time:

1. A browser window will open automatically
2. Sign in with your Google account (`has.dhia@gmail.com`)
3. Review and approve the permissions:
   - View and manage Google Slides presentations
   - View and manage files in Google Drive
4. Authorization is complete!
5. The token is saved to `.google_token.json` for future use

## Step 4: Test It!

Run a report generation - the first time will prompt for authorization, then it will work automatically.

## Notes

- The OAuth token is saved locally in `.google_token.json` (already in `.gitignore`)
- You only need to authorize once - the token will refresh automatically
- If you see permission errors, make sure:
  - Google Slides API is enabled in your project
  - Google Drive API is enabled in your project
  - Your OAuth client has the correct redirect URI: `http://localhost:8080/`

## Troubleshooting

**"OAuth credentials not configured"**
- Make sure `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` are set in `config.py`

**"The redirect URI does not match"**
- Make sure your OAuth client has redirect URI: `http://localhost:8080/`

**Token refresh errors**
- Delete `.google_token.json` and re-authorize

