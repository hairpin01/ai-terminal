#!/bin/bash

# Упрощенная версия без цветов
echo "🤖 Установка AI-TERMINAL..."

# URL для скачивания
GITHUB_RAW_URL="https://raw.githubusercontent.com/hairpin01/ai-terminal/refs/heads/main/ai-terminal"
SCRIPT_NAME="ai-terminal"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="$HOME/.config"

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 не установлен"; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "❌ pip3 не установлен"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "❌ curl не установлен"; exit 1; }

# Установка openai
echo "📦 Установка Python пакетов..."
pip3 install openai >/dev/null 2>&1

# Скачивание скрипта
echo "📥 Скачивание AI-ассистента..."
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
rm -rf "$TEMP_DIR"

# Создание конфига
echo "⚙️ Создание конфигурации..."
mkdir -p "$CONFIG_DIR"
CONFIG_FILE="$CONFIG_DIR/ai-terminal.conf"

if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" << 'EOF'
[api]
base_url = https://api.intelligence.io.solutions/api/v1/
api_key = YOUR_API_KEY_HERE
model_name = meta-llama/Llama-3.3-70B-Instruct

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

echo "🎉 Установка завершена!"
echo "📝 Использование: ai-terminal 'ваш вопрос'"
