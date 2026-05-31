import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

logger = logging.getLogger(__name__)


class APIResponseError(Exception):
    """Исключение для ошибок ответа API."""

    pass


class TokenMissingError(Exception):
    """Исключение для отсутствующих переменных окружения."""

    pass


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = [
        ("PRACTICUM_TOKEN", PRACTICUM_TOKEN),
        ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
    ]
    missing_tokens = []
    for name, token in tokens:
        if token is None:
            missing_tokens.append(name)

    if missing_tokens:
        missing_vars = ", ".join(missing_tokens)
        logger.critical(
            f"Отсутствуют обязательные переменные окружения: {missing_vars}"
        )
        raise TokenMissingError(
            f"Отсутствуют переменные окружения: {missing_vars}"
        )
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    logger.debug(f"Начинаю отправку сообщения: {message}")
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f"Сообщение отправлено: {message}")
        return True
    except (telebot.apihelper.ApiException, requests.RequestException) as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        return False


def get_api_answer(timestamp):
    """Делает запрос к API Практикума и возвращает ответ."""
    payload = {"from_date": timestamp}
    request_params = {
        "url": ENDPOINT,
        "headers": HEADERS,
        "params": payload,
    }
    logger.debug(f"Начинаю запрос к API: {request_params}")
    try:
        response = requests.get(**request_params)
    except requests.RequestException as e:
        raise ConnectionError(f"Ошибка при запросе к API: {e}")

    if response.status_code != HTTPStatus.OK:
        raise APIResponseError(f"API вернул код {response.status_code}")

    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        received_type = type(response).__name__
        raise TypeError(
            f"Ответ API не является словарём. " f"Получен тип: {received_type}"
        )
    if "homeworks" not in response:
        raise KeyError("В ответе API отсутствует ключ homeworks")

    homeworks = response["homeworks"]

    if not isinstance(homeworks, list):
        received_type = type(homeworks).__name__
        raise TypeError(
            f"Значение homeworks не является списком. "
            f"Получен тип: {received_type}"
        )
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы и формирует сообщение."""
    if not isinstance(homework, dict):
        received_type = type(homework).__name__
        raise TypeError(
            f"homework не является словарём. " f"Получен тип: {received_type}"
        )

    try:
        homework_name = homework["homework_name"]
        status = homework["status"]
    except KeyError as e:
        raise KeyError(f"Отсутствует ключ {e} в ответе API")

    verdict = HOMEWORK_VERDICTS.get(status)
    if verdict is None:
        raise ValueError(f"Неизвестный статус: {status}")

    return f'Изменился статус проверки работы "{homework_name}". ' f"{verdict}"


def main():
    """Основная логика работы бота."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        check_tokens()
    except TokenMissingError as e:
        logger.critical(f"Ошибка при запуске бота: {e}")
        sys.exit(1)

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                success = send_message(bot, message)
                if success:
                    last_error_message = None
                    timestamp = response.get("current_date", timestamp)
            else:
                logger.debug("Новых статусов нет")
                timestamp = response.get("current_date", timestamp)
        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logger.error(message)
            if message != last_error_message:
                if send_message(bot, message):
                    last_error_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Необработанная ошибка: {e}")
        sys.exit(1)
