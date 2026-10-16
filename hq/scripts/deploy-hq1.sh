#!/bin/sh
# Build HQ for silenthelp.org/hq1 and copy it into the Flask app's static folder.
# Old asset files are KEPT (no delete) so tabs opened before a deploy can still
# load the chunks they reference; only index.html is replaced.
set -e
cd "$(dirname "$0")/.."
HQ_BASE=/hq1/ VITE_DEMO_MODE=false \
VITE_SUPABASE_URL=https://tqdguunpyjmpptsqrwrd.supabase.co \
VITE_SUPABASE_ANON_KEY=sb_publishable_KFeDURTbsI0mAbegKeMt8g_ZtIUaezP \
npm run build
mkdir -p ../static/hq1/assets
rsync -a frontend/dist/assets/ ../static/hq1/assets/
cp frontend/dist/index.html frontend/dist/favicon.svg ../static/hq1/
echo "Deployed build to static/hq1 (old assets kept)."
