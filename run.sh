#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_NAME="${IMAGE_NAME:-mpj:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-mpj}"
HOST_PORT="${HOST_PORT:-5500}"
CONTAINER_PORT="${CONTAINER_PORT:-5500}"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Ad123654}"
BUILD_IMAGE=1
DETACH=1
ENV_FILE=""

usage() {
  cat <<'EOF'
用法:
  ./run.sh [选项]

选项:
  --image NAME            镜像名，默认 mpj:latest
  --name NAME             容器名，默认 mpj
  --port PORT             宿主机端口，默认 5500
  --data-dir PATH         宿主机 data 目录，默认 当前项目/data
  --admin-username NAME   管理员用户名，默认 admin
  --admin-password PASS   管理员密码，默认 Ad123654
  --env-file PATH         传入额外 docker env-file
  --no-build              不重新构建镜像，直接启动
  --foreground            前台运行容器
  -h, --help              显示帮助

也可通过环境变量覆盖:
  IMAGE_NAME, CONTAINER_NAME, HOST_PORT, DATA_DIR, ADMIN_USERNAME, ADMIN_PASSWORD
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --image)
      IMAGE_NAME="$2"
      shift 2
      ;;
    --name)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --port)
      HOST_PORT="$2"
      shift 2
      ;;
    --data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    --admin-username)
      ADMIN_USERNAME="$2"
      shift 2
      ;;
    --admin-password)
      ADMIN_PASSWORD="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --no-build)
      BUILD_IMAGE=0
      shift
      ;;
    --foreground)
      DETACH=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1"
      usage
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker 命令，请先安装并启动 Docker。"
  exit 1
fi

mkdir -p "$DATA_DIR"

if [ "$BUILD_IMAGE" = "1" ]; then
  echo "==> 构建镜像: $IMAGE_NAME"
  docker build -t "$IMAGE_NAME" "$ROOT_DIR"
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  echo "==> 删除已有容器: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

RUN_ARGS=(
  --name "$CONTAINER_NAME"
  -p "$HOST_PORT:$CONTAINER_PORT"
  -v "$DATA_DIR:/app/data"
  -e HOST=0.0.0.0
  -e PORT="$CONTAINER_PORT"
  -e DEBUG=0
  -e DATA_DIR=/app/data
  -e UPLOAD_DIR=/app/data/uploads
  -e DATABASE_URL=sqlite:////app/data/mpj.sqlite3
  -e ADMIN_USERNAME="$ADMIN_USERNAME"
  -e ADMIN_PASSWORD="$ADMIN_PASSWORD"
)

if [ -n "$ENV_FILE" ]; then
  RUN_ARGS+=(--env-file "$ENV_FILE")
fi

if [ "$DETACH" = "1" ]; then
  RUN_ARGS=(-d "${RUN_ARGS[@]}")
else
  RUN_ARGS=(--rm "${RUN_ARGS[@]}")
fi

echo "==> 启动容器: $CONTAINER_NAME"
echo "==> 数据目录: $DATA_DIR -> /app/data"
echo "==> 访问地址: http://127.0.0.1:$HOST_PORT"
docker run "${RUN_ARGS[@]}" "$IMAGE_NAME"
