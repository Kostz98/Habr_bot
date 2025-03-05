import requests
from bs4 import BeautifulSoup
import telebot
import json
import os
import time
from datetime import datetime

# Токен вашего бота
bot = telebot.TeleBot('Тут ваш токен от тг бота')

# Путь к файлу с данными пользователей
USER_DATA_FILE = 'user_data.json'

# Глобальный флаг для отслеживания первого запуска
first_start = True


# Функция для загрузки данных пользователей из файла
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as file:
            data = json.load(file)
            # Инициализация недостающих полей
            for user_id, user_info in data.items():
                if 'registration_time' not in user_info:
                    user_info['registration_time'] = datetime.now().isoformat()
                if 'status' not in user_info:
                    user_info['status'] = 'active'
            return data
    return {}


# Функция для сохранения данных пользователей в файл
def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as file:
        json.dump(data, file, indent=4)


# Загрузка данных пользователей
user_data = load_user_data()


def get_habr_articles(page_number=1, num_articles=20, retries=3):
    url = f'https://habr.com/ru/feed/page{page_number}/'
    for _ in range(retries):
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            articles = []
            article_elements = soup.find_all('article', class_='tm-articles-list__item')[:num_articles]

            for article in article_elements:
                article_data = {}
                title_element = article.find('h2', class_='tm-title')
                if title_element:
                    article_data['title'] = title_element.find('a').text.strip()
                    article_data['link'] = 'https://habr.com' + title_element.find('a')['href']
                else:
                    article_data['title'] = 'Заголовок отсутствует'
                    article_data['link'] = ''

                author_element = article.find('span', class_='tm-user-info__user')
                if author_element:
                    article_data['author'] = author_element.find('a').text.strip()
                else:
                    article_data['author'] = 'Автор отсутствует'

                time_element = article.find('time')
                if time_element:
                    article_data['time_ago'] = time_element['datetime']
                else:
                    article_data['time_ago'] = 'Время публикации отсутствует'

                article_data['hubs'] = [hub.text.strip() for hub in
                                        article.find_all('a', class_='tm-publication-hub__link')]
                articles.append(article_data)

            return articles
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}, retrying...")
            time.sleep(2)
    return []


def get_article_data(article_url, retries=3):
    for _ in range(retries):
        try:
            response = requests.get(article_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            title = soup.find('h1').text.strip()
            pub_date = soup.find('span', class_='tm-article-datetime-published').text.strip()
            author = soup.find('a', class_='tm-user-info__username').text.strip()
            content_div = soup.find('div', class_='tm-article-presenter__body')
            content = content_div.get_text(separator='\n').strip()

            return {
                "title": title,
                "publication_date": pub_date,
                "author": author,
                "content": content
            }
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}, retrying...")
            time.sleep(2)
    return {}


def send_article(chat_id, article, index):
    message_text = f"Название: {article['title']}\n"
    message_text += "———————————————————\n"
    message_text += f"Ссылка: {article['link']}\n"
    message_text += "———————————————————\n"
    message_text += f"Автор: {article['author']}\n"
    message_text += "———————————————————\n"
    message_text += f"Время публикации: {article['time_ago']}\n"
    message_text += "———————————————————\n"
    message_text += "Хабы:\n"
    message_text += ", ".join(article['hubs']) if article['hubs'] else "Нет хабов"

    bot.send_message(chat_id, message_text)
    send_navigation_message(chat_id, index)


def send_navigation_message(chat_id, index):
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(
        telebot.types.InlineKeyboardButton("Назад", callback_data='назад'),
        telebot.types.InlineKeyboardButton("Дальше", callback_data='дальше'),
        telebot.types.InlineKeyboardButton("Открыть статью", callback_data=f"открыть_{index}")
    )
    bot.send_message(chat_id, "Хотите перейти на другую страницу?", reply_markup=keyboard)


def send_long_message(chat_id, text, current_article_index):
    max_length = 4096
    parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    for part in parts:
        bot.send_message(chat_id, part)
    send_navigation_message(chat_id, current_article_index)


def execute_start(chat_id):
    global user_data, articles
    user_id = str(chat_id)
    if user_id in user_data:
        page_number = user_data[user_id]['page_number']
        current_article_index = user_data[user_id]['current_article_index']
    else:
        page_number = 1
        current_article_index = 0
        user_data[user_id] = {
            'page_number': page_number,
            'current_article_index': current_article_index,
            'registration_time': datetime.now().isoformat(),
            'status': 'active'
        }
        save_user_data(user_data)

    articles = get_habr_articles(page_number)
    if articles:
        send_article(chat_id, articles[current_article_index], current_article_index)
    else:
        bot.send_message(chat_id, "Не удалось загрузить статьи. Попробуйте позже.")


@bot.message_handler(commands=['start'])
def send_welcome(message):
    execute_start(message.chat.id)


@bot.message_handler(commands=['account'])
def send_account_info(message):
    user_id = str(message.from_user.id)
    if user_id in user_data:
        registration_time = user_data[user_id].get('registration_time', 'Неизвестно')
        status = user_data[user_id].get('status', 'Неизвестен')
        account_info = (f"Время регистрации: {registration_time}\n"
                        f"Статус: {status}")
        bot.send_message(message.chat.id, account_info)
    else:
        bot.send_message(message.chat.id, "Информация о вашем аккаунте не найдена.")


@bot.message_handler(commands=['history_numbers'])
def send_history_numbers(message):
    user_id = str(message.from_user.id)
    if user_id in user_data:
        page_number = user_data[user_id].get('page_number', 'Неизвестно')
        article_index = user_data[user_id].get('current_article_index', 'Неизвестно')
        history_info = (f"Вы находитесь на странице: {page_number}\n"
                        f"Текущая новость: {article_index}")
        bot.send_message(message.chat.id, history_info)
    else:
        bot.send_message(message.chat.id, "Информация о вашем аккаунте не найдена.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('открыть_'))
def handle_open_article(call):
    global user_data, articles
    user_id = str(call.from_user.id)
    if user_id in user_data:
        current_article_index = user_data[user_id]['current_article_index']
    else:
        current_article_index = 0

    if call.data.startswith('открыть_'):
        index = int(call.data[len('открыть_'):])
        article_url = articles[index]['link']
        article_data = get_article_data(article_url)

        message_text = f"Название: {article_data['title']}\n"
        message_text += f"Дата публикации: {article_data['publication_date']}\n"
        message_text += f"Автор: {article_data['author']}\n"
        message_text += "———————————————————\n"
        message_text += f"Содержание:\n{article_data['content']}"

        send_long_message(call.message.chat.id, message_text, current_article_index)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    global user_data, articles, first_start
    user_id = str(call.from_user.id)
    if user_id in user_data:
        page_number = user_data[user_id]['page_number']
        current_article_index = user_data[user_id]['current_article_index']
        registration_time = user_data[user_id]['registration_time']
        status = user_data[user_id]['status']
    else:
        page_number = 1
        current_article_index = 0
        registration_time = datetime.now().isoformat()
        status = 'active'

    # Если это первый запуск после перезагрузки
    if first_start:
        execute_start(call.message.chat.id)
        first_start = False
        return

    if call.data == 'дальше':
        current_article_index += 1
        if current_article_index >= len(articles):
            page_number += 1
            current_article_index = 0
            articles = get_habr_articles(page_number)
        user_data[user_id]['page_number'] = page_number
        user_data[user_id]['current_article_index'] = current_article_index
        save_user_data(user_data)
        send_article(call.message.chat.id, articles[current_article_index], current_article_index)

    elif call.data == 'назад':
        current_article_index -= 1
        if current_article_index < 0:
            page_number -= 1
            articles = get_habr_articles(page_number)
            current_article_index = len(articles) - 1
        user_data[user_id]['page_number'] = page_number
        user_data[user_id]['current_article_index'] = current_article_index
        save_user_data(user_data)
        send_article(call.message.chat.id, articles[current_article_index], current_article_index)


bot.polling()
