# This script is for Windows PowerShell. It resets the local database and migrations.

# Stop on any error
$ErrorActionPreference = "Stop"

# Delete the old migrations folder and database file, ignoring errors if they don't exist
Remove-Item -Recurse -Force -Path "migrations" -ErrorAction SilentlyContinue
Remove-Item -Force -Path "testimonials.db" -ErrorAction SilentlyContinue

# Create new, clean migration instructions
flask db init
flask db migrate -m "Recreate initial migration for production"
flask db upgrade

# Upload the new instructions to GitHub
git add .
git commit -m "Recreate initial migration for production"
git push

Write-Host "SUCCESS! Local database reset and fix has been pushed to GitHub."

