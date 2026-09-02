#!/bin/bash
# اسکریپت نصب/آپدیت خودکار بات فروش کانفیگ V2Ray
#
# استفاده (ریپازیتوری ثابت و عمومی خودت):
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/alirezasj7/s-ui-bot/main/install.sh)
#
# این اسکریپت هم برای نصب اولیه کار می‌کند و هم برای آپدیت‌های بعدی (idempotent است).

set -e

# جلوگیری از گیر کردن apt پشت پنجره‌های تعاملی (مثل پرسش needrestart برای ری‌استارت سرویس‌ها)
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export NEEDRESTART_SUSPEND=1

# ============================================================================
# This installer always pulls the S-UI-X-only release from the owner's public
# archive.  It intentionally does not use git clone, so GitHub never prompts
# for a username/password on the VPS.
# ============================================================================
PROJECT_ARCHIVE_URL="https://github.com/alirezasj7/s-ui-bot/archive/refs/heads/main.tar.gz"
INSTALL_DIR="$HOME/v2ray_bot"
SERVICE_NAME="v2raybot"

echo "🚀 شروع نصب/آپدیت بات فروش کانفیگ V2Ray"
echo "──────────────────────────────────────────"

# ----------------------------------------------------------------------------
# ۱. گرفتن اطلاعات BotFather پیش از نصب
# ----------------------------------------------------------------------------
# BotFather issues the bot token, not the owner's Telegram ID.  The ID must be
# entered once (for example from @userinfobot); accepting arbitrary text here
# would make the bot fail during startup.
ENV_ALREADY_EXISTS=0
if [ -f "$INSTALL_DIR/.env" ]; then
    ENV_ALREADY_EXISTS=1
    echo "✅ فایل .env از قبل موجود است؛ اطلاعات BotFather دست‌نخورده می‌ماند."
else
    echo ""
    echo "🔑 ابتدا اطلاعات بات را از BotFather آماده کن:"
    read -rsp "توکن بات (از BotFather): " BOT_TOKEN_INPUT
    echo ""
    read -rp "آیدی عددی مالک (از @userinfobot): " OWNER_ID_INPUT
    if [ -z "$BOT_TOKEN_INPUT" ]; then
        echo "⛔️ توکن بات نمی‌تواند خالی باشد."
        exit 1
    fi
    if ! [[ "$OWNER_ID_INPUT" =~ ^-?[0-9]+$ ]]; then
        echo "⛔️ آیدی مالک باید فقط عدد باشد."
        exit 1
    fi
fi

# ----------------------------------------------------------------------------
# ۲. نصب پیش‌نیازهای سیستمی (بدون git)
# ----------------------------------------------------------------------------
echo "📦 بررسی و نصب پیش‌نیازها (curl, python3, pip, venv)..."
sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1 apt-get update -qq
timeout 120 sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1 apt-get install -y -qq curl ca-certificates tar python3 python3-pip python3-venv > /dev/null

# ----------------------------------------------------------------------------
# ۳. دریافت کد از آرشیو عمومی گیت‌هاب (بدون clone/احراز هویت)
# ----------------------------------------------------------------------------
echo "📥 دریافت بستهٔ عمومی پروژه..."
TMP_PROJECT_DIR=$(mktemp -d)
cleanup_tmp_project() { rm -rf "$TMP_PROJECT_DIR"; }
trap cleanup_tmp_project EXIT
curl --fail --location --silent --show-error --retry 3 "$PROJECT_ARCHIVE_URL" \
    -o "$TMP_PROJECT_DIR/project.tar.gz"
tar -xzf "$TMP_PROJECT_DIR/project.tar.gz" -C "$TMP_PROJECT_DIR"
EXTRACTED_PROJECT=$(find "$TMP_PROJECT_DIR" -mindepth 1 -maxdepth 1 -type d -name 's-ui-bot-*' -print -quit)
if [ -z "$EXTRACTED_PROJECT" ]; then
    echo "⛔️ ساختار بستهٔ پروژه معتبر نیست."
    exit 1
fi

mkdir -p "$INSTALL_DIR"
STATE_DIR=$(mktemp -d)
if [ -f "$INSTALL_DIR/.env" ]; then mv "$INSTALL_DIR/.env" "$STATE_DIR/.env"; fi
if [ -d "$INSTALL_DIR/venv" ]; then mv "$INSTALL_DIR/venv" "$STATE_DIR/venv"; fi
if [ -f "$INSTALL_DIR/bot_database.db" ]; then mv "$INSTALL_DIR/bot_database.db" "$STATE_DIR/bot_database.db"; fi
if [ -d "$INSTALL_DIR/reseller_dbs" ]; then mv "$INSTALL_DIR/reseller_dbs" "$STATE_DIR/reseller_dbs"; fi
find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$EXTRACTED_PROJECT/." "$INSTALL_DIR/"
for state_item in .env venv bot_database.db reseller_dbs; do
    if [ -e "$STATE_DIR/$state_item" ]; then mv "$STATE_DIR/$state_item" "$INSTALL_DIR/$state_item"; fi
done
rm -rf "$STATE_DIR"
cd "$INSTALL_DIR"

# ----------------------------------------------------------------------------
# ۴. ساخت virtual environment و نصب پکیج‌ها
# ----------------------------------------------------------------------------
echo "🐍 آماده‌سازی محیط پایتون..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt --quiet
deactivate

# ----------------------------------------------------------------------------
# ۵. تنظیم فایل .env (فقط دفعه اول)
# ----------------------------------------------------------------------------
if [ "$ENV_ALREADY_EXISTS" -eq 0 ]; then
    cat > "$INSTALL_DIR/.env" <<EOF
BOT_TOKEN=$BOT_TOKEN_INPUT
OWNER_ID=$OWNER_ID_INPUT
EOF
    echo "✅ فایل .env ساخته شد."
else
    echo "✅ فایل .env از قبل موجود است، دست‌نخورده باقی می‌ماند."
fi

# ----------------------------------------------------------------------------
# ۵. ساخت systemd service برای اجرای دائمی و خودکار بعد از ری‌بوت سرور
# ----------------------------------------------------------------------------
echo "⚙️ تنظیم سرویس systemd برای اجرای همیشگی بات..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=V2Ray Telegram Sales Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=5
User=$(whoami)

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" > /dev/null 2>&1
sudo systemctl restart "$SERVICE_NAME"

sleep 2

echo ""
echo "──────────────────────────────────────────"
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ بات با موفقیت نصب/آپدیت شد و در حال اجراست."
else
    echo "⚠️ بات اجرا نشد. برای دیدن جزئیات خطا:"
    echo "   sudo journalctl -u $SERVICE_NAME -n 50 --no-pager"
fi
echo ""
echo "دستورات مفید:"
echo "  وضعیت بات:    sudo systemctl status $SERVICE_NAME"
echo "  لاگ زنده:      sudo journalctl -u $SERVICE_NAME -f"
echo "  ری‌استارت:     sudo systemctl restart $SERVICE_NAME"
echo "  متوقف کردن:    sudo systemctl stop $SERVICE_NAME"
echo "──────────────────────────────────────────"
