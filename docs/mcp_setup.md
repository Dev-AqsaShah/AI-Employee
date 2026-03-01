# MCP Server Setup Guide

## Email MCP Server

### 1. Install MCP SDK

```bash
uv pip install mcp
```

### 2. Configure Gmail App Password

1. Enable 2-Factor Authentication on your Google account
2. Go to: https://myaccount.google.com/apppasswords
3. Create an App Password for "Mail"
4. Copy the 16-character password

### 3. Set Environment Variables

Add to your `.env` file:
```
EMAIL_FROM=your.email@gmail.com
EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
DRY_RUN=false
```

### 4. Register in Claude Code

Add to `~/.claude.json` (or `%APPDATA%\Claude\claude.json` on Windows):

```json
{
  "mcpServers": {
    "email": {
      "command": "python",
      "args": ["D:\\AI-Employee\\mcp_server\\email_mcp.py"],
      "env": {
        "VAULT_PATH": "D:\\AI-Employee\\AI_Employee_Vault",
        "EMAIL_FROM": "your.email@gmail.com",
        "EMAIL_APP_PASSWORD": "your-app-password",
        "DRY_RUN": "false"
      }
    }
  }
}
```

### 5. Test the MCP Server

```bash
python mcp_server/email_mcp.py
```

Then in Claude Code, you can ask:
> "Draft an email to client@example.com about the January invoice"

Claude will call `draft_email` and save it to `AI_Employee_Vault/Drafts/`.

## Security Notes

- NEVER set `DRY_RUN=false` until you've tested with `DRY_RUN=true`
- App Passwords give full email send access — treat them like passwords
- All sent emails are logged to `AI_Employee_Vault/Logs/`
- The MCP server only sends emails after you've moved the approval file to `/Approved/`
