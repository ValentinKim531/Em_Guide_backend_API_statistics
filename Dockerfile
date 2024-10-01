# Указываем базовый образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями в контейнер
COPY requirements.txt .

# Устанавливаем все зависимости, указанные в файле requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё содержимое локальной директории в контейнер
COPY . .

ENV PORT=8082

# Указываем команду для запуска сервера при запуске контейнера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8084"]
