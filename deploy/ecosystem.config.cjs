// PM2 ecosystem configuration for running the Connect 4 FastAPI backend
// Start with: pm2 start deploy/ecosystem.config.cjs && pm2 save

module.exports = {
  apps: [
    {
      name: 'connect4-api',
      cwd: '/var/www/html/connect4/backend',
      script: '/var/www/html/connect4/backend/.venv/bin/uvicorn',
      args: 'main:app --host 127.0.0.1 --port 8000 --workers 1',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      max_memory_restart: '512M',
      env: {
        MAX_AI_DEPTH: '4',
      },
    },
  ],
};
