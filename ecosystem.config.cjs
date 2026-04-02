// PM2 Ecosystem Configuration for ETF Quant Platform
// Usage: pm2 start ecosystem.config.cjs
// Docs:  https://pm2.keymetrics.io/docs/usage/application-declaration/

const UV = "/home/devops/.local/bin/uv";
const CWD = "/home/devops/etf-quant";

module.exports = {
  apps: [
    // ─── FastAPI Backend ────────────────────────────────
    {
      name: "etf-api",
      script: UV,
      args: "run uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2",
      cwd: CWD,
      interpreter: "none", // uv is a binary, not a Node script
      env: {
        UV_PROJECT_ENVIRONMENT: `${CWD}/.venv`,
        PYTHONPATH: CWD,
      },
      // Restart policy
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 3000,
      // Logging
      error_file: `${CWD}/logs/api-error.log`,
      out_file: `${CWD}/logs/api-out.log`,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      // Resource limits
      max_memory_restart: "512M",
    },

    // ─── Celery Worker (async tasks) ────────────────────
    {
      name: "etf-worker",
      script: UV,
      args: "run celery -A api.celery_app worker --loglevel=info --concurrency=2",
      cwd: CWD,
      interpreter: "none",
      env: {
        UV_PROJECT_ENVIRONMENT: `${CWD}/.venv`,
        PYTHONPATH: CWD,
      },
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 5000,
      error_file: `${CWD}/logs/worker-error.log`,
      out_file: `${CWD}/logs/worker-out.log`,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      max_memory_restart: "1G",
    },

    // ─── Celery Beat (scheduled data collection) ────────
    {
      name: "etf-scheduler",
      script: UV,
      args: "run celery -A api.celery_app beat --loglevel=info",
      cwd: CWD,
      interpreter: "none",
      env: {
        UV_PROJECT_ENVIRONMENT: `${CWD}/.venv`,
        PYTHONPATH: CWD,
      },
      max_restarts: 5,
      min_uptime: "10s",
      restart_delay: 5000,
      error_file: `${CWD}/logs/scheduler-error.log`,
      out_file: `${CWD}/logs/scheduler-out.log`,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      max_memory_restart: "256M",
    },

    // ─── Data Collection (daily at 15:35 CST via cron) ──
    {
      name: "etf-collect",
      script: UV,
      args: "run python scripts/collect_daily.py --resume --skip-spot",
      cwd: CWD,
      interpreter: "none",
      env: {
        UV_PROJECT_ENVIRONMENT: `${CWD}/.venv`,
        PYTHONPATH: CWD,
        TZ: "Asia/Shanghai",
      },
      // Run once daily at 15:35 Beijing time (after market close at 15:00)
      cron_restart: "35 15 * * 1-5",
      autorestart: false, // Don't restart after completion
      max_restarts: 0,
      error_file: `${CWD}/logs/collect-error.log`,
      out_file: `${CWD}/logs/collect-out.log`,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      max_memory_restart: "512M",
    },

    // ─── Signal Recording (daily at 15:40 CST, after data collection) ──
    {
      name: "etf-record",
      script: UV,
      args: "run python scripts/record_signals.py",
      cwd: CWD,
      interpreter: "none",
      env: {
        UV_PROJECT_ENVIRONMENT: `${CWD}/.venv`,
        PYTHONPATH: CWD,
        TZ: "Asia/Shanghai",
      },
      // Run 5 min after data collection (15:35 + 5 = 15:40)
      cron_restart: "40 15 * * 1-5",
      autorestart: false,
      max_restarts: 0,
      error_file: `${CWD}/logs/record-error.log`,
      out_file: `${CWD}/logs/record-out.log`,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      max_memory_restart: "512M",
    },

    // ─── Next.js Frontend ───────────────────────────────
    {
      name: "etf-web",
      script: "npm",
      args: "run start",
      cwd: `${CWD}/web`,
      interpreter: "none",
      env: {
        PORT: 3001,
        NODE_ENV: "production",
      },
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 3000,
      error_file: `${CWD}/logs/web-error.log`,
      out_file: `${CWD}/logs/web-out.log`,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      max_memory_restart: "512M",
    },
  ],
};
