#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5500}"
DEBUG="${DEBUG:-1}"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Ad123654}"

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-username)
      export ADMIN_USERNAME="$2"
      shift 2
      ;;
    --admin-password)
      export ADMIN_PASSWORD="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1"
      exit 1
      ;;
  esac
done

export DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
export UPLOAD_DIR="${UPLOAD_DIR:-$DATA_DIR/uploads}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$DATA_DIR/mpj.sqlite3}"
export FLASK_APP="${FLASK_APP:-run.py}"

echo "==> 项目目录: $ROOT_DIR"
echo "==> 数据库: $DATABASE_URL"
echo "==> 管理员账号: $ADMIN_USERNAME"

if [ ! -d "$VENV_DIR" ]; then
  echo "==> 创建 Python 虚拟环境: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> Python: $(python --version)"

if [ "$SKIP_PIP_INSTALL" != "1" ]; then
  echo "==> 安装/检查依赖"
  if ! python -m pip install -r requirements.txt; then
    echo "依赖安装失败。请检查网络，或先手动安装依赖后使用 SKIP_PIP_INSTALL=1 ./start.sh"
    exit 1
  fi
else
  echo "==> 已跳过依赖安装: SKIP_PIP_INSTALL=1"
fi

mkdir -p "$DATA_DIR" "$UPLOAD_DIR"

echo "==> 初始化数据库"
python - <<'PY'
import os
from app.db import init_db

init_db(os.environ["DATABASE_URL"])
print("数据库初始化完成")
PY

python - <<'PY'
try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    raise SystemExit("缺少 Flask 依赖。请执行: source .venv/bin/activate && python -m pip install -r requirements.txt")
PY

echo "==> 启动服务: http://$HOST:$PORT"
python - <<PY
from app import create_app

app = create_app()
app.run(host="$HOST", port=int("$PORT"), debug=bool(int("$DEBUG")), use_reloader=False)
PY
