# TaskMaster Backup and Restore Guide

**Created:** November 30, 2025
**Purpose:** Prevent TaskMaster data loss (.taskmaster directory is gitignored)

---

## Problem

The `.taskmaster` directory is gitignored by default, which means:
- Task data is NOT committed to git
- Task data is NOT pushed to remote repository
- If `.taskmaster` is deleted or corrupted, all task history is lost

---

## Solution

Created automated backup scripts that copy `.taskmaster` to a git-tracked directory.

---

## Backup Script Usage

### Automatic Backup

```bash
# Run backup script
./backup_taskmaster.sh
```

**What it does:**
1. Creates timestamped backup in `taskmaster_backup/backup_YYYYMMDD_HHMMSS/`
2. Creates/updates `taskmaster_backup/latest/` (always points to most recent)
3. Stages backup in git (ready for commit)
4. Shows task count and backup location

**Example output:**
```
TaskMaster Backup Script
================================
Creating backup...
✓ Timestamped backup created: taskmaster_backup/backup_20251130_032500
✓ Latest backup updated: taskmaster_backup/latest

Backup contains:
total 16
drwxr-xr-x  config.json
drwxr-xr-x  reports/
drwxr-xr-x  state.json
drwxr-xr-x  tasks/

Total tasks backed up: 18

Adding backup to git...
✓ Backup staged for commit

Next steps:
  git commit -m "TaskMaster backup: 20251130_032500"
  git push

Backup complete!
Backup location: taskmaster_backup/backup_20251130_032500
```

### Commit and Push

```bash
# Commit backup
git commit -m "TaskMaster backup: $(date +%Y%m%d)"

# Push to remote
git push
```

---

## Restore Script Usage

### List Available Backups

```bash
# Show all backups
./restore_taskmaster.sh
```

### Restore from Latest Backup

```bash
# Restore from most recent backup
./restore_taskmaster.sh latest
```

### Restore from Specific Backup

```bash
# List backups first
ls -1dt taskmaster_backup/backup_*

# Restore from specific backup
./restore_taskmaster.sh taskmaster_backup/backup_20251130_032500
```

**What it does:**
1. Backs up current `.taskmaster` to `.taskmaster.before_restore` (safety)
2. Copies backup to `.taskmaster`
3. Shows restored task count
4. Provides rollback instructions if needed

---

## Backup Schedule Recommendations

### Manual Backups

Run backup after:
- ✅ Completing major milestones
- ✅ Adding/updating many tasks
- ✅ Before major refactoring
- ✅ End of each day/week

### Automated Backups (Optional)

Add to git hooks or cron:

**Git Hook (.git/hooks/pre-commit):**
```bash
#!/bin/bash
# Auto-backup TaskMaster before each commit
cd portfolio_manager
./backup_taskmaster.sh > /dev/null 2>&1
```

**Cron (Daily at 6 PM):**
```bash
0 18 * * * cd /path/to/portfolio_manager && ./backup_taskmaster.sh
```

---

## Backup Location

**Directory:** `taskmaster_backup/` (git-tracked)

**Structure:**
```
taskmaster_backup/
├── backup_20251130_101500/  # Timestamped backup #1
│   ├── config.json
│   ├── state.json
│   ├── tasks/
│   │   └── tasks.json
│   └── reports/
├── backup_20251130_143000/  # Timestamped backup #2
│   └── ...
├── backup_20251130_180000/  # Timestamped backup #3
│   └── ...
└── latest/                    # Symlink/copy to most recent
    └── ...
```

---

## Recovery Scenarios

### Scenario 1: Accidental Task Deletion

**Problem:** Deleted tasks in TaskMaster accidentally
**Solution:**
```bash
./restore_taskmaster.sh latest
```

### Scenario 2: Corrupted .taskmaster Directory

**Problem:** .taskmaster/tasks/tasks.json is corrupted
**Solution:**
```bash
./restore_taskmaster.sh latest
```

### Scenario 3: Need Older Backup

**Problem:** Recent backup has issues, need to go back further
**Solution:**
```bash
# List all backups
ls -1dt taskmaster_backup/backup_*

# Restore from specific backup
./restore_taskmaster.sh taskmaster_backup/backup_20251129_120000
```

### Scenario 4: Restore After System Crash

**Problem:** Entire system reinstalled, need to restore TaskMaster
**Solution:**
```bash
# Clone repository
git clone <repo-url>
cd portfolio_manager

# Restore from latest backup in repo
./restore_taskmaster.sh latest
```

---

## Verification

### After Backup

```bash
# Check backup was created
ls -lh taskmaster_backup/latest/

# Verify task count matches
jq '[.master.tasks[] | select(.id != null)] | length' .taskmaster/tasks/tasks.json
jq '[.master.tasks[] | select(.id != null)] | length' taskmaster_backup/latest/tasks/tasks.json
```

### After Restore

```bash
# Verify TaskMaster works
cd ..  # Go to parent directory
task-master get-tasks

# Check task count
jq '[.master.tasks[] | select(.id != null)] | length' portfolio_manager/.taskmaster/tasks/tasks.json
```

---

## Best Practices

1. **Backup Frequently**
   - After major task updates
   - Before major changes
   - End of each work session

2. **Commit Backups to Git**
   - Always commit after backup
   - Push to remote repository
   - This is your safety net

3. **Keep Multiple Backups**
   - Don't delete old backups immediately
   - Keep at least last 5-10 backups
   - Disk space is cheap, data loss is expensive

4. **Test Restore Periodically**
   - Verify restore works
   - Practice recovery procedure
   - Don't wait for emergency

5. **Monitor Backup Size**
   - TaskMaster data is small (<1 MB typically)
   - If backups grow large, investigate
   - Clean up old reports if needed

---

## Cleanup Old Backups (Optional)

Keep only last 10 backups:

```bash
cd taskmaster_backup
ls -1dt backup_* | tail -n +11 | xargs rm -rf
```

---

## Troubleshooting

### Backup Script Fails

**Error:** "jq: command not found"
**Solution:** Install jq: `brew install jq` (macOS) or `apt-get install jq` (Linux)

**Error:** ".taskmaster directory not found"
**Solution:** You're not in the correct directory. Run from `portfolio_manager/`

### Restore Script Fails

**Error:** "No backups found"
**Solution:** Run backup script first: `./backup_taskmaster.sh`

**Error:** "Backup not found"
**Solution:** Check backup path exists: `ls -l taskmaster_backup/`

---

## Integration with Git

### Add .taskmaster to .gitignore (Already Done)

```gitignore
# .gitignore
.taskmaster/
```

### Track taskmaster_backup in Git

```bash
# Add to git
git add taskmaster_backup/

# Commit
git commit -m "Add TaskMaster backup"

# Push
git push
```

---

## Summary

- ✅ `.taskmaster` is gitignored (local only)
- ✅ `taskmaster_backup/` is git-tracked (backed up to remote)
- ✅ Run `./backup_taskmaster.sh` to backup
- ✅ Run `./restore_taskmaster.sh latest` to restore
- ✅ Commit and push backups regularly

**Remember:** Your TaskMaster data is only as safe as your last backup!

---

**Last Updated:** November 30, 2025
