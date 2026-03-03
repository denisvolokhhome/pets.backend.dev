#!/bin/bash

# Script to run the pet_images table migration
# This adds support for multiple images per pet

echo "Running pet_images table migration..."

cd "$(dirname "$0")/.." || exit 1

# Run the migration
alembic upgrade head

echo "Migration completed!"
echo ""
echo "The pet_images table has been created."
echo "Existing pet images have been migrated to the new table."
echo "You can now upload multiple images per pet (max 5)."
