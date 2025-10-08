# This script is for Windows PowerShell. It resets the local database and migrations.

# Stop on any error
$ErrorActionPreference = "Stop"

Write-Host "Step 1 & 2: Deleting old local database and migrations folder..."
# Delete the old migrations folder and database file, ignoring errors if they don't exist
Remove-Item -Recurse -Force -Path "migrations" -ErrorAction SilentlyContinue
Remove-Item -Force -Path "testimonials.db" -ErrorAction SilentlyContinue
Write-Host "-> Old files removed."

Write-Host "Step 3: Creating new, clean migration instructions..."
# Initialize a new, empty migrations folder
flask db init
# Create the master instructions to build the database
flask db migrate -m "Recreate initial migration for production"
# Run the instructions and build a new local test database
flask db upgrade
Write-Host "-> New migration created and applied locally."

Write-Host "Step 4: Uploading new instructions to GitHub..."
# Add all files to staging
git add .
# Commit the changes with a standard message
git commit -m "1.0.0"
# Push the commit to the 'main' branch on GitHub
git push
Write-Host "-> Changes pushed to GitHub."

Write-Host "-------------------------------------------"
Write-Host "SUCCESS! Your local database is reset and the fix has been pushed to GitHub."
Write-Host "You can now redeploy on Render."
Write-Host "-------------------------------------------"
```

    

