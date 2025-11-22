#!/bin/bash

echo "🤖 Установка AI-TERMINAL с Gemini AI..."

# URL для скачивания
GITHUB_RAW_URL="https://raw.githubusercontent.com/hairpin01/ai-terminal/refs/heads/main/ai-terminal-gemini"
SCRIPT_NAME="ai-terminal-gemini"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="$HOME/.config"

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 не установлен"; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "❌ pip3 не установлен"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "❌ curl не установлен"; exit 1; }

# Установка google-generativeai
echo "📦 Установка Python пакетов..."
pip3 install google-generativeai >/dev/null 2>&1

# Скачивание скрипта
echo "📥 Скачивание AI-ассистента Gemini..."
TEMP_DIR=$(mktemp -d)
SCRIPT_PATH="$TEMP_DIR/$SCRIPT_NAME"

if curl -s -L "$GITHUB_RAW_URL" -o "$SCRIPT_PATH"; then
    echo "✅ Скрипт успешно скачан"
else
    echo "❌ Ошибка при скачивании скрипта"
    exit 1
fi

# Установка
echo "🔧 Установка скрипта..."
chmod +x "$SCRIPT_PATH"
sudo cp "$SCRIPT_PATH" "$INSTALL_DIR/"

# Создаем симлинк
sudo ln -sf "$INSTALL_DIR/$SCRIPT_NAME" "$INSTALL_DIR/ai-terminal"
echo "✅ Симлинк ai-terminal создан"

# Создание конфига
echo "⚙️ Создание конфигурации..."
mkdir -p "$CONFIG_DIR"
CONFIG_FILE="$CONFIG_DIR/ai-terminal.conf"

if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" << 'EOF'
[api]
provider = gemini
api_key = YOUR_GEMINI_API_KEY_HERE
model_name = gemini-1.5-flash

[settings]
system_prompt = You are a helpful AI assistant. Provide clear and concise answers in Russian. Be friendly and professional.
temperature = 0.7
max_tokens = 1024
memory_depth = 5
typing_effect = true
typing_speed = 0.01
EOF
    echo "✅ Конфиг создан: $CONFIG_FILE"
fi

echo ""
echo "🎉 Установка завершена!"
echo ""
echo "📝 Использование:"
echo "  ai-terminal-gemini 'ваш вопрос'"
echo "  ai-terminal 'ваш вопрос' (симлинк)"
echo ""
echo "🔑 Получите API ключ на: https://aistudio.google.com/"
echo "   и установите его в ~/.config/ai-terminal.conf"
