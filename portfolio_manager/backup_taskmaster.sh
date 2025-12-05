#!/bin/bash
# TaskMaster Backup Script
# Backs up .taskmaster directory to a git-tracked location
# Since .taskmaster is gitignored, this ensures task data is preserved

set -e  # Exit on error

# Configuration
TASKMASTER_DIR=".taskmaster"
BACKUP_DIR="taskmaster_backup"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_WITH_TIMESTAMP="${BACKUP_DIR}/backup_${TIMESTAMP}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}TaskMaster Backup Script${NC}"
echo "================================"

# Check if .taskmaster exists
if [ ! -d "$TASKMASTER_DIR" ]; then
    echo -e "${RED}Error: $TASKMASTER_DIR directory not found${NC}"
    exit 1
fi

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Create timestamped backup
echo -e "${YELLOW}Creating backup...${NC}"
cp -r "$TASKMASTER_DIR" "$BACKUP_WITH_TIMESTAMP"
echo -e "${GREEN}✓ Timestamped backup created: $BACKUP_WITH_TIMESTAMP${NC}"

# Create/update latest backup (symlink or copy)
if [ -L "${BACKUP_DIR}/latest" ] || [ -d "${BACKUP_DIR}/latest" ]; then
    rm -rf "${BACKUP_DIR}/latest"
fi
cp -r "$TASKMASTER_DIR" "${BACKUP_DIR}/latest"
echo -e "${GREEN}✓ Latest backup updated: ${BACKUP_DIR}/latest${NC}"

# Show backup contents
echo ""
echo "Backup contains:"
ls -lh "$BACKUP_WITH_TIMESTAMP"

# Get task stats from tasks.json
if [ -f "${TASKMASTER_DIR}/tasks/tasks.json" ]; then
    TOTAL_TASKS=$(jq '[.master.tasks[] | select(.id != null)] | length' "${TASKMASTER_DIR}/tasks/tasks.json" 2>/dev/null || echo "unknown")
    echo -e "\n${GREEN}Total tasks backed up: $TOTAL_TASKS${NC}"
fi

# Add to git if in a git repository
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo ""
    echo -e "${YELLOW}Adding backup to git...${NC}"
    git add "$BACKUP_DIR"
    echo -e "${GREEN}✓ Backup staged for commit${NC}"
    echo ""
    echo "Next steps:"
    echo "  git commit -m \"TaskMaster backup: ${TIMESTAMP}\""
    echo "  git push"
else
    echo -e "${YELLOW}Not in a git repository - backup created but not staged${NC}"
fi

echo ""
echo -e "${GREEN}Backup complete!${NC}"
echo "Backup location: $BACKUP_WITH_TIMESTAMP"
