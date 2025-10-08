
rm -rf migrations
rm -f testimonials.db

flask db init

flask db migrate -m "Recreate initial migration for production"

flask db upgrade

git add .
git commit -m "Fix database migration"
git push
