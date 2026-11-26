#!/usr/bin/env bash
# Scans every blob in every commit (all refs) plus the working tree for secret-like patterns.
# Prints only commit/file/line and the pattern NAME -- never the matched value.
set -u
declare -A PATS=(
  [aws_access_key_id]='(AKIA|ASIA)[0-9A-Z]{16}'
  [aws_secret_assignment]='(aws_secret_access_key|AWS_SECRET_ACCESS_KEY)["'"'"' ]*[:=][ "'"'"']*[A-Za-z0-9/+]{40}'
  [hex32_literal_possible_spotify_id_or_secret]='["'"'"'][0-9a-f]{32}["'"'"']'
  [bearer_or_basic_literal]='(Bearer|Basic) [A-Za-z0-9+/=_.-]{20,}'
  [private_key_block]='-----BEGIN [A-Z ]*PRIVATE KEY-----'
  [generic_secret_assignment]='(secret|password|passwd|token|api_key)["'"'"' ]*[:=][ ]*["'"'"'][^"'"'"' ]{8,}["'"'"']'
)
echo "== Commits scanned (all refs) =="
git rev-list --all
echo "== Files ever present in history =="
git log --all --format= --name-only | sort -u
echo "== Pattern hits in history (value suppressed) =="
hits=0
for c in $(git rev-list --all); do
  for name in "${!PATS[@]}"; do
    out=$(git grep -n -I -E -o "${PATS[$name]}" "$c" -- . 2>/dev/null | cut -d: -f1-3)
    if [ -n "$out" ]; then echo "$out" | sed "s/\$/  [$name]/"; hits=$((hits+1)); fi
  done
done
echo "history_pattern_groups_with_hits=$hits"
echo "== Pattern hits in working tree incl. untracked (value suppressed) =="
whits=0
for name in "${!PATS[@]}"; do
  out=$(grep -rn -I -E -o --exclude-dir=.git --exclude-dir=.venv --exclude=secret_scan.sh "${PATS[$name]}" . 2>/dev/null | cut -d: -f1-2)
  if [ -n "$out" ]; then echo "$out" | sed "s/\$/  [$name]/"; whits=$((whits+1)); fi
done
echo "worktree_pattern_groups_with_hits=$whits"
echo "== Credential-like filenames anywhere in history =="
git log --all --format= --name-only | grep -iE '(credentials|\.env|secret|\.pem|\.key|id_rsa)' || echo "none"
echo "== Credential-like files on disk (excluding .git) =="
find . -path ./.git -prune -o \( -iname 'credentials*' -o -iname '.env*' -o -iname '*.pem' -o -iname '*.key' \) -print | grep . || echo "none"
