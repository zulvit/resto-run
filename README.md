# Restaurant Report Bot

Бот для обработки CSV-отчётов по ресторанам.

## Описание

- Принимает CSV с колонками «Название сделки», «Компания», «Количество», «Сумма», «Товар».
- Возвращает CSV с итогами и суммами: без скидки, скидка 10%, со скидкой.
- Логирует работу в консоль.

## Деплой

### Переменные окружения / секреты

- `TELEGRAM_BOT_TOKEN` — токен бота.
- Для продакшна рекомендуется использовать Docker secrets:
  - Поместите токен в файл `/run/secrets/telegram_token`.
  - Контейнер автоматически его подхватит.

### Сборка Docker-образа

```bash
docker build -t restaurant-report-bot:latest .
```

### Запуск контейнера

С передачей токена через env **(не рекомендуется к использованию на боевом сервере)**:
```bash
docker run -d --name restaurant-report-bot -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" restaurant-report-bot:latest
```

С использованием Docker secrets:

```bash
docker run -d --name restaurant-report-bot \
  --secret source=telegram_token,target=telegram_token \
  restaurant-report-bot:latest
```

### Логи

- Логи идут в stdout.  
- Уровень логирования можно задавать переменной окружения `LOG_LEVEL` (`INFO` по умолчанию).

## Обновления

Смотрите файл `CHANGELOG.md`.