#!/bin/bash
# ==========================================================================
# curl_cffi TLS 修复 (Arch Linux OpenSSL 3.6)
#
# 根因: PyPI 发布的 curl_cffi wheel 把 libcurl + OpenSSL 静态编译进了
#       _wrapper.abi3.so。该静态 OpenSSL 与 Arch 系统的 OpenSSL 3.6 冲突，
#       导致所有 curl_cffi 发出的 HTTPS 请求报:
#       "TLS connect error: OPENSSL_internal:invalid library (0)"
#
# 解决: 用 Arch 官方仓库的 curl-impersonate + python-curl_cffi,
#       这两个包使用系统 OpenSSL 3.6 动态编译, 不会冲突。
# ==========================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "============================================"
echo " curl_cffi TLS 修复 (Arch Linux)"
echo "============================================"
echo ""

# ── 方案 A: 检查系统包是否已安装 ──
if ldconfig -p 2>/dev/null | grep -q libcurl-impersonate; then
    echo "[方案A] 系统已有 curl-impersonate 动态库"
    echo "  已找到:"
    ldconfig -p | grep libcurl-impersonate | head -5
    echo ""
    echo "  请用 yay 安装 python-curl-cffi-git (AUR):"
    echo "    yay -S python-curl-cffi-git"
    echo ""
    echo "  这会让 venv 使用系统的动态 libcurl-impersonate,"
    echo "  不再有 OpenSSL 静态冲突。"
    exit 0
fi

# ── 方案 B: 需要管理员安装 ──
echo "[方案B] 系统还未安装 curl-impersonate"
echo ""
echo "  需要管理员运行以下命令 (一次性的):"
echo ""
echo "    sudo pacman -S curl-impersonate python-curl_cffi"
echo ""
echo "  这两个包来自 Arch 的 [extra] 官方仓库, 使用系统 OpenSSL 3.6 编译。"
echo "  安装后所有依赖 curl_cffi 的项目都会自动修复。"
echo ""

# ── 备选: 手动下载 libcurl-impersonate.so ──
echo "  或者手动下载动态库 (免 sudo):"
echo ""
echo "    1. 下载 libcurl-impersonate 动态库"
echo "    2. 设置 LD_PRELOAD=/path/to/libcurl-impersonate-chrome.so"
echo ""
echo "  更多信息: https://github.com/lexiforest/curl-impersonate"

echo ""
echo "============================================"
echo " 临时方案 (本项目): backend_api.py 已改为使用"
echo " 标准 requests 库进行配额刷新, 不受此问题影响。"
echo " 仅注册机的 sentinel/PoW 流程才需要 curl_cffi。"
echo "============================================"
