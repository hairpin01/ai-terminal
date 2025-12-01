# ai-terminal
Нейросеть прям в терминале!

## install
```
curl https://raw.githubusercontent.com/hairpin01/ai-terminal/refs/heads/main/install.sh | bash
```
> [!TIP]
> или wget `https://raw.githubusercontent.com/hairpin01/ai-terminal/refs/heads/main/install.sh`
## run
`chmod +x install.sh`
потом
`./install`
### edit cfg
макс токинов в ответе `max_tokens` 
обязательно поставь в `api_key` свой ключик с io.net

> [!WARNING]
> для ai-terminal-gemini надо самому выставить config по пути `~/.config/ai-terminal.conf`
```
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
```
