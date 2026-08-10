#!/usr/bin/env zsh

# agent — Start/reuse ssh-agent and load SSH keys

setopt NO_UNSET

SSH_AGENT_ENV="$HOME/.ssh-agent-env"

# ── 0. Enforce Git configuration files ────────────────────────────────────

cat > "$HOME/.gitconfig" <<'GITCONFIG'
[core]
    autocrlf = input
[pull]
    rebase = true
[init]
    defaultBranch = main

[includeIf "gitdir/i:*work*/"]
    path = ~/.gitconfig-work
[includeIf "gitdir/i:*personal*/"]
    path = ~/.gitconfig-personal
GITCONFIG

cat > "$HOME/.gitconfig-work" <<'EOF'
[user]
    name = Pro Name
    email = pro.mail@domain.com
EOF

cat > "$HOME/.gitconfig-personal" <<'EOF'
[user]
    name = Per Name
    email = per.mail@domain.com
EOF

echo "==> Git config files written"

# ── 1. Start / reuse ssh-agent ────────────────────────────────────────────

echo "==> Checking ssh-agent..."

if [[ -f "$SSH_AGENT_ENV" ]]; then
    source "$SSH_AGENT_ENV" >/dev/null 2>&1 || true
fi

if ! ssh-add -l >/dev/null 2>&1; then
    echo "==> Launching new ssh-agent..."
    ssh-agent -s | grep '^SSH_' > "$SSH_AGENT_ENV"
    source "$SSH_AGENT_ENV" >/dev/null
fi

# ── 2. Load SSH keys ──────────────────────────────────────────────────────

load_key() {
    local LABEL="$1"
    local KEY="$2"

    if [[ ! -f "$KEY" ]]; then
        echo "==> Warning: key not found for $LABEL: $KEY" >&2
        return
    fi

    local FINGERPRINT
    FINGERPRINT=$(ssh-keygen -lf "$KEY" 2>/dev/null | awk '{print $2}')

    if [[ -n "$FINGERPRINT" ]] &&
       ! ssh-add -l 2>/dev/null | grep -qF "$FINGERPRINT"
    then
        echo "==> Loading key for $LABEL ($KEY, expires in 4h)..."
        ssh-add -t 36000 "$KEY"
    else
        echo "==> Key already loaded for $LABEL"
    fi
}

load_key "github.com (personal)" "$HOME/.ssh/id_per"
load_key "github.com-e (work)" "$HOME/.ssh/id_pro"

# ── 3. Git repo actions ───────────────────────────────────────────────────

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "==> Not in a Git repo — skipping remote check."
    echo "==> Done."
    return 0
fi

REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)

if [[ -z "$REMOTE_URL" ]]; then
    echo "==> No 'origin' remote configured."
    echo "==> Done."
    return 0
fi

# ── 4. Fix MP-Trabalho remotes ────────────────────────────────────────────

if [[ "$REMOTE_URL" == git@github.com:SOME-Org/* ]]; then
    FIXED_URL="${REMOTE_URL/git@github.com:SOME-Org\//git@github.com-e:SOME-Org/}"

    echo "==> Fixing remote URL:"
    echo "    $REMOTE_URL"
    echo " -> $FIXED_URL"

    git remote set-url origin "$FIXED_URL"
    REMOTE_URL="$FIXED_URL"
fi

# ── 5. Show Git identity ──────────────────────────────────────────────────

GIT_USER=$(git config user.name 2>/dev/null || echo unknown)
GIT_EMAIL=$(git config user.email 2>/dev/null || echo unknown)

echo "==> Git identity: $GIT_USER <$GIT_EMAIL>"

# ── 6. Optional pull ──────────────────────────────────────────────────────

if [[ "${1:-}" == "pull" ]]; then
    echo "==> Pulling latest main branch..."
    git pull origin main
fi

echo "==> Done."
