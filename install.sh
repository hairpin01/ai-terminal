#!/bin/bash

# Цвета для красивого вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Функции для красивого вывода
print_header() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║                🤖 AI-TERMINAL                   ║"
    echo "║           ИИ-ассистент для терминала            ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️ $1${NC}"
}

print_step() {
    echo -e "${CYAN}📦 $1${NC}"
}

# URL для скачивания
GITHUB_RAW_URL="https://raw.githubusercontent.com/hairpin01/ai-terminal/refs/heads/main/ai-terminal"
SCRIPT_NAME="ai-terminal"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="$HOME/.config"
CONFIG_FILE="$CONFIG_DIR/ai-terminal.conf"

# Проверка прав
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        print_warning "Запуск с правами root"
    fi
}

# Проверка зависимостей
check_dependencies() {
    print_step "Проверка зависимостей..."
    
    # Проверяем Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 не установлен"
        echo -e "${YELLOW}Установите Python3:"
        echo "  Ubuntu/Debian: sudo apt install python3"
        echo "  CentOS/RHEL: sudo yum install python3"
        echo "  macOS: brew install python3${NC}"
        exit 1
    else
        print_success "Python3 установлен"
    fi
    
    # Проверяем pip
    if ! command -v pip3 &> /dev/null; then
        print_warning "pip3 не установлен, устанавливаю..."
        if command -v apt &> /dev/null; then
            sudo apt update && sudo apt install -y python3-pip
        elif command -v yum &> /dev/null; then
            sudo yum install -y python3-pip
        elif command -v brew &> /dev/null; then
            brew install python3
        fi
    fi
    
    if command -v pip3 &> /dev/null; then
        print_success "pip3 установлен"
    else
        print_error "Не удалось установить pip3"
        exit 1
    fi
    
    # Проверяем curl
    if ! command -v curl &> /dev/null; then
        print_warning "curl не установлен, устанавливаю..."
        if command -v apt &> /dev/null; then
            sudo apt install -y curl
        elif command -v yum &> /dev/null; then
            sudo yum install -y curl
        elif command -v brew &> /dev/null; then
            brew install curl
        fi
    fi
    print_success "curl установлен"
}

# Установка Python пакетов
install_python_packages() {
    print_step "Установка Python пакетов..."
    
    # Проверяем и устанавливаем openai
    if python3 -c "import openai" &> /dev/null; then
        print_success "openai уже установлен"
    else
        print_info "Устанавливаю openai..."
        if pip3 install openai; then
            print_success "openai установлен"
        else
            print_error "Не удалось установить openai"
            exit 1
        fi
    fi
}

# Скачивание скрипта
download_script() {
    print_step "Скачивание AI-ассистента..."
    
    # Создаем временную директорию
    TEMP_DIR=$(mktemp -d)
    SCRIPT_PATH="$TEMP_DIR/$SCRIPT_NAME"
    
    # Скачиваем скрипт
    if curl -s -L "$GITHUB_RAW_URL" -o "$SCRIPT_PATH"; then
        print_success "Скрипт успешно скачан"
    else
        print_error "Ошибка при скачивании скрипта"
        rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Проверяем что скрипт не пустой
    if [[ ! -s "$SCRIPT_PATH" ]]; then
        print_error "Скачанный файл пуст"
        rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    echo "$SCRIPT_PATH"
}

# Установка скрипта
install_script() {
    local script_path="$1"
    
    print_step "Установка скрипта в систему..."
    
    # Делаем скрипт исполняемым
    if ! chmod +x "$script_path"; then
        print_error "Ошибка при установке прав на скрипт"
        rm -rf "$(dirname "$script_path")"
        exit 1
    fi
    
    # Копируем в системную директорию
    if ! sudo cp "$script_path" "$INSTALL_DIR/"; then
        print_error "Ошибка при копировании скрипта"
        rm -rf "$(dirname "$script_path")"
        exit 1
    fi
    
    print_success "Скрипт установлен в $INSTALL_DIR/"
    
    # Очищаем временные файлы
    rm -rf "$(dirname "$script_path")"
}

# Создание конфигурации
create_config() {
    print_step "Настройка конфигурации..."
    
    mkdir -p "$CONFIG_DIR"
    
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
        print_success "Конфиг создан: $CONFIG_FILE"
    else
        print_info "Конфиг уже существует: $CONFIG_FILE"
    fi
}

# Проверка установки
verify_installation() {
    print_step "Проверка установки..."
    
    if command -v "$SCRIPT_NAME" &> /dev/null; then
        print_success "AI-ассистент успешно установлен!"
        return 0
    else
        print_error "AI-ассистент не найден в PATH"
        return 1
    fi
}

# Показ инструкции
show_instructions() {
    echo
    echo -e "${GREEN}"
    echo "┌──────────────────────────────────────────────────┐"
    echo "│              🎉 УСТАНОВКА ЗАВЕРШЕНА!            │"
    echo "└──────────────────────────────────────────────────┘"
    echo -e "${NC}"
    
    echo -e "${CYAN}📝 ИСПОЛЬЗОВАНИЕ:${NC}"
    echo -e "  ${YELLOW}ai-terminal \"ваш вопрос\"${NC}    - Задать вопрос"
    echo -e "  ${YELLOW}ai-terminal${NC}                 - Интерактивный режим"
    echo -e "  ${YELLOW}ai-terminal --config${NC}        - Показать путь к конфигу"
    echo -e "  ${YELLOW}ai-terminal --reset${NC}         - Сбросить историю"
    echo -e "  ${YELLOW}ai-terminal --help${NC}          - Показать справку"
    echo ""
    
    echo -e "${CYAN}⚙️  НАСТРОЙКА:${NC}"
    echo -e "  ${YELLOW}1. Откройте конфиг:${NC} nano $CONFIG_FILE"
    echo -e "  ${YELLOW}2. Замените YOUR_API_KEY_HERE на ваш API ключ${NC}"
    echo -e "  ${YELLOW}3. Получите ключ на:${NC} https://cloud.io.net/"
    echo ""
    
    echo -e "${CYAN}🚀 БЫСТРЫЙ СТАРТ:${NC}"
    echo -e "  ${YELLOW}ai-terminal \"Привет! Расскажи о себе\"${NC}"
    echo ""
}

# Основная функция
main() {
    print_header
    check_permissions
    check_dependencies
    install_python_packages
    
    local script_path
    script_path=$(download_script)
    
    # Проверяем что путь корректен
    if [[ ! -f "$script_path" ]]; then
        print_error "Скачанный файл не найден по пути: $script_path"
        exit 1
    fi
    
    install_script "$script_path"
    create_config
    
    if verify_installation; then
        show_instructions
    else
        print_error "Установка завершена с ошибками"
        exit 1
    fi
}

# Обработка аргументов
case "${1:-}" in
    --help|-h)
        print_header
        echo -e "${CYAN}Использование:${NC}"
        echo "  ./install.sh          - Установка AI-ассистента"
        echo "  ./install.sh --help   - Показать эту справку"
        echo ""
        echo -e "${CYAN}Описание:${NC}"
        echo "  Установщик для AI-ассистента на основе io.net API"
        echo "  Скачивает последнюю версию с GitHub и устанавливает в систему"
        exit 0
        ;;
    *)
        main
        ;;
esac
