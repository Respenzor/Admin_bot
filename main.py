import logging
import telebot
import hashlib
import datetime
import Levenshtein
import sqlite3
import threading
import time
import requests
from telebot import types
import re

BOT = telebot.TeleBot('6318331939:AAH0RitUJ2IvDouOCQpWMUouRhbRpj_moLU')
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)
spam_counter = {}
predict_spam = []
warnings_counter = {}
users = BOT.get_updates()
users_rule = {}


def update_users(user_id, chat_id):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    users_list = dict(cur.execute("SELECT id, name FROM users_name").fetchall())
    user_info = BOT.get_chat_member(chat_id, user_id)
    if users_list:
        for key in users_list:
            if key == user_id:
                if users_list[key] == user_info.user.username:
                    break
                else:
                    cur.execute("UPDATE users_name SET name = user_info.user.username WHERE id = ?", (key,))
                    conn.commit()


def similarity_percentage(text1, text2):
    distance = Levenshtein.distance(text1.upper(), text2.upper())
    max_length = max(len(text1), len(text2))
    similarity = 100 * (1 - distance / max_length)
    return similarity


def clear_spam_counter():
    global spam_counter
    global warnings_counter
    spam_counter = {}
    warnings_counter = {}


def timer_function():
    while True:
        threading.Timer(300, clear_spam_counter).start()
        time.sleep(300)


def check_rule(chat_id, user_id, users_rule):
    if users_rule[user_id] == 0:
        return False
    else:
        BOT.restrict_chat_member(chat_id, user_id, until_date=datetime.datetime.now() + datetime.timedelta(seconds=40))
        users_rule.pop(user_id)
        return True


def block_user(id, chat_id, message):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    block_counter = dict(cur.execute("SELECT user_id, block_count FROM block_users").fetchall())
    if block_counter:
        for key in block_counter:
            if str(key) == str(id):
                if block_counter[key] == 4:
                    try:
                        BOT.kick_chat_member(chat_id, id)
                        BOT.send_message(chat_id, f'Пользователь {message.from_user.username} был забанен в этой группе.')
                        return
                    except Exception as e:
                        print(e)
                        if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                            BOT.send_message(chat_id, f'Не удалось забанить пользователя, причина: '
                                                      f'Пользователь является администратором данного чата')
                            return
                else:
                    cur.execute("UPDATE block_users SET block_count = block_count + 1 WHERE user_id = ?", (id,))
                    conn.commit()
                    time_block = time.time() + 3600 * block_counter[key]
                    try:
                        BOT.restrict_chat_member(chat_id, id, until_date=time_block)
                        if block_counter[key] == 1:
                            BOT.send_message(chat_id, f'Пользователь {message.from_user.username} '
                                                      f'был заблокирован на 1 час')
                        else:
                            BOT.send_message(chat_id, f'Пользователь {message.from_user.username} '
                                                      f'был заблокирован на {block_counter[key]} часа')
                        return
                    except Exception as e:
                        print(e)
                        if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                            BOT.send_message(chat_id, f'Не удалось забанить пользователя, причина: '
                                                      f'Пользователь является администратором данного чата')
                            return
                    return

    cur.execute("INSERT INTO block_users (user_id, block_count) VALUES (?, ?)", (id, 1), )
    conn.commit()
    block = dict(cur.execute("SELECT user_id, block_count FROM block_users").fetchall())
    for key in block:
        if str(key) == str(id):
            try:
                time_block = time.time() + 3600
                BOT.restrict_chat_member(chat_id, id, until_date=time_block)
                BOT.send_message(chat_id, f'Пользователь {message.from_user.username} был забанен в этой группе.')
            except Exception as e:
                print(e)
                if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                    BOT.send_message(chat_id, f'Не удалось забанить пользователя, причина: '
                                              f'Пользователь является администратором данного чата')


def link_check(url):
    api_key = '81b56835-8599-41a4-a70f-e6e8eb5dc953'
    api_url = 'https://sba.yandex.net/v4/threatMatches:find'
    headers = {'Content-Type': 'application/json'}
    payload = {"client": {"clientId": "{matarak2020}", "clientVersion": "{1.1.1}"},
               "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING"], "platformTypes": ["WINDOWS"],
                              "threatEntryTypes": ["URL"], "threatEntries": [{"url": url}]}}
    response = requests.post(api_url + '?key=' + api_key, json=payload, headers=headers)
    if response.status_code == 200:
        print(response.json())
    else:
        print({"error": "Failed to check link safety."})


@BOT.message_handler(commands=['mute'])
def main(message):
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        if replied_user.username:
            chat_id = message.chat.id
            user_id = message.reply_to_message.from_user.id
            mute_time = re.search(r'\d+', message.text)
            if mute_time:
                time = int(mute_time.group())
                try:
                    BOT.restrict_chat_member(chat_id, user_id, until_date=datetime.datetime.now() + datetime.timedelta(hours=time))
                    if time == 1:
                        BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                  f'был заблокирован на 1 час')
                    else:
                        if time < 5:
                            BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                      f'был заблокирован на {time} часа')
                        elif time >= 5:
                            BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                      f'был заблокирован на {time} часов')
                    return
                except Exception as e:
                    print(e)
                    if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                        BOT.send_message(chat_id, f'Не удалось заблокировать пользователя, причина: '
                                                  f'Пользователь является администратором данного чата')
                        return
            else:
                try:
                    BOT.restrict_chat_member(chat_id, user_id, until_date=datetime.datetime.now() + datetime.timedelta(hours=2))
                    BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                              f'был заблокирован на 2 часа')
                    return
                except Exception as e:
                    print(e)
                    if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                        BOT.send_message(chat_id, f'Не удалось заблокировать пользователя, причина: '
                                                  f'Пользователь является администратором данного чата')
                        return


@BOT.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    if message.chat.type == 'private':
        conn = sqlite3.connect('users_info')
        cur = conn.cursor()
        rules = dict(cur.execute("SELECT id, rule FROM rules").fetchall())
        users_rule[message.from_user.id] = 1
        BOT.send_message(chat_id, 'Здравствуйте, сейчас я ознакомлю вас с правилами чата')
        time.sleep(3)
        for i in range(1, 9):
            rule = rules[i]
            #numb = str(i) + '.'
            #BOT.send_message(chat_id, numb + ' ' + rule)
            BOT.send_message(chat_id, rule)
            time.sleep(3)
        BOT.send_message(chat_id, 'Спасибо за ознакомление с правилами группы! Теперь вы можете общаться в ней.')


@BOT.message_handler(content_types=['photo', 'text'])
def check(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    update_users(user_id, chat_id)
    user_info = BOT.get_chat_member(chat_id, user_id)
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    check_user = dict(cur.execute("SELECT id, name FROM users_name").fetchall())
    if check_user:
        if str(user_id) in check_user.keys():
            pass
        else:
            cur.execute("INSERT INTO users_name (id, name) VALUES (?, ?)", (user_id, user_info.user.username), )
            conn.commit()
    else:
        cur.execute("INSERT INTO users_name (id, name) VALUES (?, ?)", (user_id, user_info.user.username), )
        conn.commit()
    found_similar = False

    if message.content_type in ['photo']:
        file_data = BOT.download_file(BOT.get_file(message.photo[-1].file_id).file_path)
        file_hash = hashlib.sha256(file_data).hexdigest()
        if (user_id, file_hash) in spam_counter:
            spam_counter[(user_id, file_hash)] += 1
            if spam_counter[(user_id, file_hash)] == 3 or spam_counter[(user_id, file_hash)] == 5:
                if warnings_counter == 3:
                    block_user(user_id, chat_id, message)
                if user_id in warnings_counter:
                    warnings_counter[user_id] += 1
                    if warnings_counter[user_id] == 3:
                        block_user(user_id, chat_id, message)
                else:
                    warnings_counter[user_id] = 1
                BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                          f'если вы продолжите спамить, то будете заблокированы')
        else:
            spam_counter[(user_id, file_hash)] = 1

    elif message.content_type == 'text':
        text = message.text
        if '/' in text:
            link_check(text)
        for key in spam_counter.keys():
            if similarity_percentage(text, key[1]) > 30:
                spam_counter[key] += 1
                found_similar = True
                if spam_counter[key] == 8:
                    block_user(user_id, chat_id, message)
                    break
                elif spam_counter[key] == 3 or spam_counter[key] == 5:
                    if user_id in warnings_counter:
                        warnings_counter[user_id] += 1
                        if warnings_counter[user_id] == 3:
                            block_user(user_id, chat_id, message)
                            break
                        else:
                            BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                                     f'если вы продолжите спамить, то будете заблокированы')
                    else:
                        warnings_counter[user_id] = 1
                        if warnings_counter[user_id] == 3:
                            block_user(user_id, chat_id, message)
                            break
                        BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                                  f'если вы продолжите спамить, то будете заблокированы')
                    break
        if not found_similar:
            spam_counter[(user_id, text)] = 1


@BOT.message_handler(func=lambda message: True, content_types=['new_chat_members'])
def new_chat_member(message):
    chat_id = message.chat.id
    new_members = message.new_chat_members
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text='Ознакомиться с правилами', url='https://t.me/Respenzor_Admin_bot'))
    for member in new_members:
        bot_info = BOT.get_me()
        if member.username != bot_info.username:
            BOT.reply_to(message, f"Добро пожаловать в группу, @{member.username}! "
                                  f"Для получения возможности отправлять сообщения ознакомься с правилами!", reply_markup=markup)
            user_id = member.id
            BOT.restrict_chat_member(chat_id, user_id)
            users_rule[user_id] = 0
            running = True
            while running:
                if check_rule(chat_id, user_id, users_rule):
                   break


threading.Thread(target=timer_function, daemon=True).start()
BOT.polling(none_stop=True)
