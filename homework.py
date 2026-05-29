import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
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

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f"Сообщение отправлено: {message}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        raise


def get_api_answer(timestamp):
    """Делает запрос к API Практикума и возвращает ответ."""
    payload = {"from_date": timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != 200:
            raise ConnectionError(f"API вернул код {response.status_code}")
    except requests.RequestException as e:
        raise ConnectionError(f"Ошибка при запросе к API: {e}")
    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError("Ответ API не является словарём")
    if "homeworks" not in response:
        raise KeyError("В ответе API отсутствует ключ homeworks")
    if not isinstance(response["homeworks"], list):
        raise TypeError("Значение homeworks не является списком")
    return response["homeworks"]


def parse_status(homework):
    """Извлекает статус домашней работы и формирует сообщение."""
    try:
        homework_name = homework["homework_name"]
        status = homework["status"]
    except KeyError as e:
        raise KeyError(f"Отсутствует ключ {e} в ответе API")
    verdict = HOMEWORK_VERDICTS.get(status)
    if verdict is None:
        raise ValueError(f"Неизвестный статус: {status}")
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical("Отсутствует обязательная переменная окружения")
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
                send_message(bot, message)
                last_error_message = None
            else:
                logger.debug("Новых статусов нет")
            timestamp = response.get("current_date", timestamp)
            time.sleep(RETRY_PERIOD)
        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logger.error(message)
            if message != last_error_message:
                try:
                    send_message(bot, message)
                    last_error_message = message
                except Exception:
                    pass
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
