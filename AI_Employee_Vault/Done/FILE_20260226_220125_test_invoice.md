---
type: file_drop
source_name: test_invoice.txt
inbox_path: 20260226_220125_test_invoice.txt
size: 120 bytes
extension: .txt
received: 2026-02-26T22:01:25.682748
priority: high
status: pending_approval
---

## New File Received

A file has been dropped into the watch folder and is ready for processing.

| Field     | Value                |
|-----------|----------------------|
| Name      | `test_invoice.txt`      |
| Size      | 120 bytes               |
| Type      | `.txt` |
| Received  | 2026-02-26 22:01:25 |
| Inbox     | `Inbox/20260226_220125_test_invoice.txt` |

## File Preview

```
Client: Acme Corp
Invoice #: INV-2026-001
Amount: $1500
Due Date: 2026-03-05
Services: AI consulting February 2026
```

## Suggested Actions
- [ ] Review the file contents
- [ ] Determine action required
- [ ] Move to /Done when complete

## Notes
_Add any notes about this file here._

## AI Review [2026-02-26T22:10:00Z]
- **Decision:** PENDING_APPROVAL
- **Reason:** Financial amount $1,500 detected — handbook §2 requires human approval (> $500)
- **Action required:** Review invoice and move this file to `/Approved/` to proceed, or `/Rejected/` to decline.
