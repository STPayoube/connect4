# Connect 4 — WeakC4 Web Application

A full-stack Connect 4 web application powered by `backend/weakc4.py`, featuring a **FastAPI** backend with multi-session management, a **real-time Admin Control Panel** (SSE), a **Svelte 5 + Tailwind CSS** component frontend, and automated **GitHub Actions** deployment to a Linux VPS.

## Features

- **4 AI Difficulty Levels** (replacing raw depth 1–4):
  - **Easy**: Relaxed WeakC4 heuristic + depth-1 Tree.
  - **Medium**: Classic WeakC4 heuristic + depth-2 Minimax Tree fallback.
  - **Hard**: True lookahead Alpha-Beta Minimax (sees forks and open threats).
  - **Impossible**: Deep Alpha-Beta Minimax with center ordering and tactical pruning.
- **3 Game Modes**:
  - **Human vs AI** (play as Player 1 or Player 2, choose starter or Random Start).
  - **Player vs Player** (local 2-player pass-and-play with custom names for both players).
  - **AI vs AI** (manual Step AI Move or Auto-Play / Pause watch mode with speed control).
- **Random Start**: One-click **Random Start** button (plus Random coin toss option in Settings).
- **Usernames & Real-Time Admin Control Panel (`/admin`)**:
  - Players enter a username before playing (saved locally and editable anytime).
  - Admins authenticate at `/admin` using `ADMIN_PASSWORD` to view **all active and finished user games simultaneously in real time** via Server-Sent Events (`/api/admin/stream`), including live mini-boards, search/filtering, and a full-screen **Spectate Live** modal.
- **Automated VPS Deployment**: `.github/workflows/deploy.yml` builds `frontend/dist`, syncs files via `rsync` over SSH, updates Python dependencies, and restarts the backend service on every push to `main`.

---

## Local Development

### 1. Backend (FastAPI + Uvicorn)

```bash
cd backend
python -m venv .venv

# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Optional: set a custom Admin password (defaults to "admin123" locally)
# export ADMIN_PASSWORD="your-strong-password"
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend (Vite + Svelte 5 + Tailwind CSS)

```bash
cd frontend
npm install
npm run dev
```

- Game UI: `http://localhost:5173`
- Admin Control Panel: `http://localhost:5173/admin`

### 3. Single-Process Production Preview

```bash
cd frontend && npm run build
cd ../backend
SERVE_STATIC=true ADMIN_PASSWORD="your-strong-password" .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

### 4. Backend Tests

```bash
cd backend
.venv/bin/pytest -v       # Linux / macOS
# .venv\Scripts\pytest -v # Windows
```

---

## Automatic VPS Deployment (GitHub Actions)

The workflow at `.github/workflows/deploy.yml` deploys automatically on every push to `main` (and supports manual triggers via **Actions → Deploy Connect4 → Run workflow**).

### 1. Add GitHub Repository Secrets

Go to **GitHub Repo → Settings → Secrets and variables → Actions**:

| Type | Name | Value |
| --- | --- | --- |
| Secret | `VPS_HOST` | Your VPS IP or hostname |
| Secret | `VPS_USER` | SSH user (same as SyncEDT) |
| Secret | `VPS_SSH_KEY` | Private SSH key authorized on the VPS |
| Secret | `ADMIN_PASSWORD` | Strong password for `/admin` Control Panel |
| Variable *(optional)* | `VPS_DEPLOY_PATH` | Target directory on VPS (default: `/var/www/html/connect4`) |
| Variable *(optional)* | `CORS_ORIGINS` | Allowed origin(s), e.g. `https://connect4.yourdomain.com` |

### 2. One-Time VPS Setup (Systemd + Nginx)

After the first workflow run syncs files into `/var/www/html/connect4`:

```bash
# Install and enable the backend systemd service
sudo cp /var/www/html/connect4/deploy/connect4.service /etc/systemd/system/connect4.service
# Edit User/Group if your deploy user is not www-data
sudo nano /etc/systemd/system/connect4.service
sudo systemctl daemon-reload
sudo systemctl enable --now connect4

# Allow the deploy SSH user to restart connect4 without a password prompt (optional, for CI restarts):
# echo "<VPS_USER> ALL=(ALL) NOPASSWD: /bin/systemctl restart connect4, /bin/systemctl is-active --quiet connect4" | sudo tee /etc/sudoers.d/connect4

# Configure Nginx reverse proxy (+ SSE support for /api/admin/stream)
sudo cp /var/www/html/connect4/deploy/nginx.conf.example /etc/nginx/sites-available/connect4
# Update server_name and root path in /etc/nginx/sites-available/connect4
sudo nano /etc/nginx/sites-available/connect4
sudo ln -s /etc/nginx/sites-available/connect4 /etc/nginx/sites-enabled/connect4
sudo nginx -t && sudo systemctl reload nginx

# Optional HTTPS with Certbot
sudo certbot --nginx -d connect4.example.com
```

*(Prefer PM2 instead of systemd? Run `pm2 start /var/www/html/connect4/deploy/ecosystem.config.cjs && pm2 save`—the GitHub Actions workflow detects and restarts `pm2` automatically if systemd is not installed.)*
