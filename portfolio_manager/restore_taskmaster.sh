#!/bin/bash
# TaskMaster Restore Script
# Restores .taskmaster directory from backup

set -e  # Exit on error

# Configuration
TASKMASTER_DIR=".taskmaster"
BACKUP_DIR="taskmaster_backup"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}TaskMaster Restore Script${NC}"
echo "================================"

# Function to list available backups
list_backups() {
    echo "Available backups:"
    ls -1dt "${BACKUP_DIR}"/backup_* 2>/dev/null | head -10 || echo "No backups found"
    if [ -d "${BACKUP_DIR}/latest" ]; then
        echo ""
        echo "Latest backup:"
        echo "  ${BACKUP_DIR}/latest"
    fi
}

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: No backups found (${BACKUP_DIR} does not exist)${NC}"
    exit 1
fi

# Determine which backup to restore
if [ -z "$1" ]; then
    echo "Usage: $0 [backup_path|latest]"
    echo ""
    list_backups
    exit 1
fi

RESTORE_FROM="$1"

# Handle 'latest' keyword
if [ "$RESTORE_FROM" = "latest" ]; then
    RESTORE_FROM="${BACKUP_DIR}/latest"
fi

# Check if backup exists
if [ ! -d "$RESTORE_FROM" ]; then
    echo -e "${RED}Error: Backup not found: $RESTORE_FROM${NC}"
    echo ""
    list_backups
    exit 1
fi

# Confirm restore
echo -e "${YELLOW}WARNING: This will replace current .taskmaster directory${NC}"
if [ -d "$TASKMASTER_DIR" ]; then
    echo "Current .taskmaster will be backed up to .taskmaster.before_restore"
fi
echo ""
echo "Restoring from: $RESTORE_FROM"
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled"
    exit 0
fi

# Backup current .taskmaster if it exists
if [ -d "$TASKMASTER_DIR" ]; then
    echo -e "${YELLOW}Backing up current .taskmaster...${NC}"
    rm -rf "${TASKMASTER_DIR}.before_restore"
    mv "$TASKMASTER_DIR" "${TASKMASTER_DIR}.before_restore"
    echo -e "${GREEN}✓ Current .taskmaster backed up to .taskmaster.before_restore${NC}"
fi

# Restore from backup
echo -e "${YELLOW}Restoring from backup...${NC}"
cp -r "$RESTORE_FROM" "$TASKMASTER_DIR"
echo -e "${GREEN}✓ Restored from: $RESTORE_FROM${NC}"

# Show restored contents
echo ""
echo "Restored contents:"
ls -lh "$TASKMASTER_DIR"

# Get task stats
if [ -f "${TASKMASTER_DIR}/tasks/tasks.json" ]; then
    TOTAL_TASKS=$(jq '[.master.tasks[] | select(.id != null)] | length' "${TASKMASTER_DIR}/tasks/tasks.json" 2>/dev/null || echo "unknown")
    echo -e "\n${GREEN}Total tasks restored: $TOTAL_TASKS${NC}"
fi

echo ""
echo -e "${GREEN}Restore complete!${NC}"
echo ""
echo "If something went wrong, you can restore the previous state:"
echo "  rm -rf $TASKMASTER_DIR"
echo "  mv ${TASKMASTER_DIR}.before_restore $TASKMASTER_DIR"
