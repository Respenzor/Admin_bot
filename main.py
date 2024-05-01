import logging
import telebot
import hashlib
import datetime
import Levenshtein
import sqlite3
import threading
import time
from telebot import types
import re


#Регистрация бота
BOT = telebot.TeleBot('6318331939:AAH0RitUJ2IvDouOCQpWMUouRhbRpj_moLU')
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

#Различные константы для отслеживания происходящего во время работы (флаги)
spam_counter = {}
predict_spam = []
warnings_counter = {}
users = BOT.get_updates()
users_rule = {}
rules_changes = {}
short_messages = {}


def update_users(user_id, chat_id): #Функция, отвечающая за запись новых пользователей в бд и проверку обновлений информации по старым
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    users_list = cur.execute("SELECT id, name, rules_check, admin, chat_id FROM users").fetchall()
    user_info = BOT.get_chat_member(chat_id, user_id)
    user_name = user_info.user.username
    admins = BOT.get_chat_administrators(chat_id)
    admin_ids = [admin.user.id for admin in admins]
    if user_id not in admin_ids:
        user_admin = 0
    else:
        user_admin = 1
    if users_list:
        for elem in users_list:
            if str(user_id) == str(elem[0]):
                if str(user_name) != str(elem[1]):
                    try:
                        cur.execute("UPDATE users SET name = ? WHERE id = ?",
                                    (user_name, user_id,))
                        conn.commit()
                    except Exception as e:
                        print(e)
                elif user_admin != elem[3]:
                    try:
                        cur.execute("UPDATE admin SET name = ? WHERE id = ?",
                                    (user_admin, user_id,))
                        conn.commit()
                    except Exception as e:
                        print(e)
                elif elem[4] is None:
                    try:
                        cur.execute("UPDATE users SET chat_id = ? WHERE id = ?",
                                    (chat_id, user_id,))
                        conn.commit()
                    except Exception as e:
                        print(e)
    else:
        cur.execute("INSERT INTO users (id, name, rules_check, admin) VALUES (?, ?, ?, ?)",
                    (user_id, user_name, 1, user_admin), )
        conn.commit()


def similarity_percentage(text1, text2): #Функция, отвечающая за сравнение текстов на подобие (сравнивает похожесть текстов по алгоритму Левенштейна)
    distance = Levenshtein.distance(text1.upper(), text2.upper())
    max_length = max(len(text1), len(text2))
    similarity = 100 * (1 - distance / max_length)
    return similarity


def clear_spam_counter(): #Функция - очиститель, необходимая для удаления старых неактуальных данных
    global spam_counter
    global warnings_counter
    global short_messages
    spam_counter = {}
    warnings_counter = {}
    short_messages = {}


def timer_function(): #Функция, запускающая clear_spam_counter раз в 5 минут
    while True:
        threading.Timer(300, clear_spam_counter).start()
        time.sleep(300)


def clear_update(): #Ещё 1 функция - очиститель
    global rules_changes
    rules_changes = {}


def check_rule(chat_id, user_id, users_rule, username): #Функция, необходимая дл проверки ознакомления пользователя с правилами группы
    if users_rule[user_id] == 0:
        return False
    else:
        BOT.restrict_chat_member(chat_id, user_id, until_date=datetime.datetime.now() + datetime.timedelta(seconds=40))
        users_rule.pop(user_id)
        conn = sqlite3.connect('users_info')
        cur = conn.cursor()
        cur.execute("INSERT INTO users (id, name, rules_check, admin, chat_id) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, 1, 0, chat_id), )
        conn.commit()

        return True


def block_user(user_id, chat_id, message): #Функция, отвечающая за блокировку пользователя за спам
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    block_counter = dict(cur.execute("SELECT user_id, block_count FROM block_users").fetchall())
    admins_names = cur.execute("SELECT name FROM users WHERE admin = 1").fetchall()
    admins_list = ''
    for admin in admins_names:
        admins_list += f'@{admin[0]} '
    if block_counter:
        for key in block_counter:
            if str(key) == str(user_id):
                if block_counter[key] == 4:
                    try:
                        BOT.kick_chat_member(chat_id, user_id)
                        BOT.send_message(chat_id, f'Пользователь {message.from_user.username} '
                                                  f'был забанен в этой группе. Оспорить блокировку можно у администраторов'
                                                  f'этого канала {admins_list}')
                        return
                    except Exception as e:
                        if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                            BOT.send_message(chat_id, f'Не удалось забанить пользователя, причина: '
                                                      f'Пользователь является администратором данного чата')
                            return
                else:
                    cur.execute("UPDATE block_users SET block_count = block_count + 1 WHERE user_id = ?", (user_id,))
                    conn.commit()
                    time_block = time.time() + 3600 * block_counter[key]
                    try:
                        BOT.restrict_chat_member(chat_id, user_id, until_date=time_block)
                        if block_counter[key] == 1:
                            BOT.send_message(chat_id, f'Пользователь {message.from_user.username} '
                                                    f'был заблокирован на 1 час. Оспорить блокировку можно у администраторов'
                                                    f'этого канала {admins_list}')
                        else:
                            BOT.send_message(chat_id, f'Пользователь {message.from_user.username} '
                                                      f'был заблокирован на {block_counter[key]} часа. Оспорить блокировку '
                                                      f'можно у администраторов этого канала {admins_list}')
                        return
                    except Exception as e:
                        if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                            BOT.send_message(chat_id, f'Не удалось забанить пользователя, причина: '
                                                      f'Пользователь является администратором данного чата')
                            return
                    return

    cur.execute("INSERT INTO block_users (user_id, block_count) VALUES (?, ?)", (user_id, 1), )
    conn.commit()
    block = dict(cur.execute("SELECT user_id, block_count FROM block_users").fetchall())
    for key in block:
        if str(key) == str(user_id):
            try:
                time_block = time.time() + 3600
                BOT.restrict_chat_member(chat_id, user_id, until_date=time_block)
                BOT.send_message(chat_id, f'Пользователь {message.from_user.username} был забанен в этой группе.'
                                          f'Оспорить блокировку можно у администраторов этого канала {admins_list}')
            except Exception as e:
                if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                    BOT.send_message(chat_id, f'Не удалось забанить пользователя, причина: '
                                              f'Пользователь является администратором данного чата')


@BOT.message_handler(commands=['mute']) #Команда, позволяющая администратору заглушать пользователей на любое время
def mute(message):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    user_id = message.from_user.id
    chat_id = message.chat.id
    admins_names = cur.execute("SELECT name FROM users WHERE admin = 1").fetchall()
    admins_list = ''
    for admin in admins_names:
        admins_list += f'@{admin[0]} '
    admins = BOT.get_chat_administrators(chat_id)
    admin_ids = [admin.user.id for admin in admins]
    if user_id in admin_ids:
        if message.reply_to_message:
            replied_user = message.reply_to_message.from_user
            replied_user_id = message.reply_to_message.from_user.id
            if replied_user.username:
                mute_time = re.search(r'\d+', message.text)
                if mute_time:
                    time = int(mute_time.group())
                    try:
                        BOT.restrict_chat_member(chat_id, replied_user_id, until_date=datetime.datetime.now() + datetime.timedelta(hours=time))
                        if time == 1:
                            BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                      f'был заблокирован на 1 час. Оспорить блокировку можно у администраторов'
                                                  f'этого канала {admins_list}')
                        else:
                            if time < 5:
                                BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                          f'был заблокирован на {time} часа. Оспорить блокировку можно у администраторов'
                                                  f'этого канала {admins_list}')
                            elif time >= 5:
                                BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                          f'был заблокирован на {time} часов. Оспорить блокировку можно у администраторов'
                                                  f'этого канала {admins_list}')
                        return
                    except Exception as e:
                        if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                            BOT.send_message(chat_id, f'Не удалось заблокировать пользователя, причина: '
                                                      f'Пользователь является администратором данного чата')
                            return
                else:
                    try:
                        BOT.restrict_chat_member(chat_id, replied_user_id, until_date=datetime.datetime.now() + datetime.timedelta(hours=2))
                        BOT.send_message(chat_id, f'Пользователь @{replied_user.username} '
                                                  f'был заблокирован на 2 часа. Оспорить блокировку можно у администраторов'
                                                  f'этого канала {admins_list}')
                        return
                    except Exception as e:
                        if 'admin' in str(e).lower() or 'owner' in str(e).lower():
                            BOT.send_message(chat_id, f'Не удалось заблокировать пользователя, причина: '
                                                      f'Пользователь является администратором данного чата')
                            return
    else:
        BOT.send_message(chat_id, 'У вас нет прав для использования этой команды. '
                                  'При повторных запросах вы будете заблокированы за спам командами')


@BOT.message_handler(commands=['unmute']) #Команда, отменяющая действие команды mute
def unmute(message):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    user_id = message.from_user.id
    chat_id = message.chat.id
    admins_names = cur.execute("SELECT name FROM users WHERE admin = 1").fetchall()
    admins_list = ''
    for admin in admins_names:
        admins_list += f'@{admin[0]} '
    admins = BOT.get_chat_administrators(chat_id)
    admin_ids = [admin.user.id for admin in admins]
    if user_id in admin_ids:
        if message.reply_to_message:
            replied_user = message.reply_to_message.from_user
            replied_user_id = message.reply_to_message.from_user.id
            if replied_user.username:
                try:
                    BOT.restrict_chat_member(chat_id, replied_user_id, until_date=datetime.datetime.now() + datetime.timedelta(seconds=30))
                    BOT.send_message(chat_id, f'Пользователь @{replied_user.username} был разблокирован')
                except Exception as e:
                    BOT.send_message(chat_id, f'Пользователь @{replied_user.username} не заблокирован')


@BOT.message_handler(commands=['start']) #Команда, знакомящая пользователя с правилами чата
def start(message):
    chat_id = message.chat.id
    if message.chat.type == 'private':
        conn = sqlite3.connect('users_info')
        cur = conn.cursor()
        rules = dict(cur.execute("SELECT id, rule FROM rules").fetchall())
        users_rule[message.from_user.id] = 1
        BOT.send_message(chat_id, 'Здравствуйте, сейчас я ознакомлю вас с правилами чата')
        time.sleep(3)
        for i in range(1, len(rules.keys()) + 1):
            rule = rules[i]
            BOT.send_message(chat_id, rule)
            time.sleep(3)
        BOT.send_message(chat_id, 'Спасибо за ознакомление с правилами группы! Теперь вы можете общаться в ней.')
        cur.execute("UPDATE users SET rules_check = 1 WHERE id = ?", (message.from_user.id,))
        conn.commit()


@BOT.message_handler(commands=['rules']) #Команда, позволяющая администратору изменить правила чата
def updates_rules(message):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    admins_names = cur.execute("SELECT name FROM users WHERE admin = 1").fetchall()
    chat_id = message.chat.id
    if message.chat.type == 'private':
        if message.from_user.username in admins_names:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton(text='Удалить праило', callback_data='delite'))
            markup.row(types.InlineKeyboardButton(text='Добавить праило', callback_data='add'))
            BOT.send_message(chat_id, 'Что вы хотите сделать?', reply_markup=markup)
        else:
            BOT.send_message(chat_id, 'У вас нет прав для использования этой команды')


@BOT.message_handler(commands=['block']) #Команда, позволяющая администратору добавить слово в "Блек лист" чата
def updates_rules(message):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    admins_names = cur.execute("SELECT name FROM users WHERE admin = 1").fetchall()
    chat_id = message.chat.id
    if message.chat.type == 'private':
        if message.from_user.username in admins_names:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton(text='Добавить запрещенное слово', callback_data='add_block'))
            BOT.send_message(chat_id, 'Что вы хотите сделать?', reply_markup=markup)
        else:
            BOT.send_message(chat_id, 'У вас нет прав для использования этой команды')


@BOT.callback_query_handler(func=lambda callback: True) #Обработчик нажатия кнопок
def change(callback):
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    rules = dict(cur.execute("SELECT id, rule FROM rules").fetchall())
    if callback.data == 'delite':
        for i in range(1, len(rules.keys()) + 1):
            rule = rules[i]
            BOT.send_message(callback.message.chat.id, rule)
        BOT.send_message(callback.message.chat.id, 'Введите номер правила, которое хотите удалить')
        rules_changes['del'] = callback.message.chat.id
    if callback.data == 'add':
        for i in range(1, len(rules.keys()) + 1):
            rule = rules[i]
            BOT.send_message(callback.message.chat.id, rule)
        BOT.send_message(callback.message.chat.id, 'Введите новое правило')
        rules_changes['add'] = callback.message.chat.id
    if callback.data == 'add_block':
        BOT.send_message(callback.message.chat.id, 'Введите запрещенное слово')
        rules_changes['add_block'] = callback.message.chat.id


@BOT.message_handler(content_types=['photo', 'text', 'video', 'audio', 'animation', 'voice']) #Обработчик, отвечающий за проверку сообщений на спам
def check(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    conn = sqlite3.connect('users_info')
    cur = conn.cursor()
    rules = dict(cur.execute("SELECT id, rule FROM rules").fetchall())
    found_similar = False

    #Проверка обновления правил чата администратором и сообщение о их изменении всем участникам чата
    if rules_changes:
        if 'del' in rules_changes.keys():
            if int(message.text):
                if int(message.text) in rules.keys():
                    cur.execute("DELETE FROM rules WHERE id = ?",
                                (message.text,),)
                    BOT.send_message(rules_changes['del'], 'Правило удалено')
                    conn.commit()
                else:
                    BOT.send_message(rules_changes['del'], 'Правила с таким номером нет')
            else:
                BOT.send_message(rules_changes['del'], 'Введите номер правила')
        if 'add' in rules_changes:
            cur.execute("INSERT INTO rules (id, rule, updatings) VALUES (?, ?, ?)",
                        (len(rules.keys()) + 1, message.text, 1), )
            BOT.send_message(rules_changes['add'], 'Правило добавлено')
            conn.commit()
        if 'add_block' in rules_changes:
            cur.execute("INSERT INTO block_words (word, autor_id, autor_name) VALUES (?, ?, ?)",
                        (message.text, message.from_user.id, message.from_user.username))
            BOT.send_message(rules_changes['add_block'], 'Слово добавлено')
            conn.commit()
    rules_up = cur.execute("SELECT rule, updatings FROM rules").fetchall()
    chanel = cur.execute("SELECT chat_id FROM users").fetchall()
    ch_id = chanel[0][0]
    for rule in rules_up:
        if rule[1] == 1:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(text='Ознакомиться',
                                                  url='https://t.me/Respenzor_Admin_bot'))
            BOT.send_message(ch_id, "Правила группы были обновлены. Просим к ознакомлению", reply_markup=markup)
            clear_update()
            cur.execute("UPDATE rules SET updatings = ? WHERE id = ?",
                        (0, len(rules.keys()) + 1,))
            conn.commit()

    if message.chat.type != 'private':
        update_users(user_id, chat_id)

        if message.content_type == 'photo': #Обработка спама фото
            file_data = BOT.download_file(BOT.get_file(message.photo[-1].file_id).file_path)
            file_hash = hashlib.sha256(file_data).hexdigest()
            if (user_id, file_hash) in spam_counter:
                spam_counter[(user_id, file_hash)] += 1
                if spam_counter[(user_id, file_hash)] == 3 or spam_counter[(user_id, file_hash)] == 5:
                    if warnings_counter == 3:
                        block_user(user_id, chat_id, message)
                        return
                    if user_id in warnings_counter:
                        warnings_counter[user_id] += 1
                        if warnings_counter[user_id] == 3:
                            block_user(user_id, chat_id, message)
                            return
                    else:
                        warnings_counter[user_id] = 1
                    BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                              f'если вы продолжите спамить, то будете заблокированы')
            else:
                spam_counter[(user_id, file_hash)] = 1

        elif message.content_type == 'text': #Обработка спама текстом и смайликами
            text = message.text
            block = cur.execute('SELECT word FROM block_words').fetchall()
            for word in block:
                if str(word)[2:-3].lower() in text.lower():
                    BOT.delete_message(chat_id, message.id)
            if len(text) < 5:
                if user_id in short_messages.keys():
                    short_messages[user_id] += 1
                    if short_messages[user_id] == 5:
                        BOT.send_message(chat_id, "Пожалуйста, излагайте свои мысли понятней."
                                                  "Старайтесь собирать их в 1 сообщение для того, чтобы вас было легче понять ")
                    elif short_messages[user_id] == 10:
                        conn = sqlite3.connect('users_info')
                        cur = conn.cursor()
                        admins_names = cur.execute("SELECT name FROM users WHERE admin = 1").fetchall()
                        admins_list = ''
                        for admin in admins_names:
                            admins_list += f'@{admin[0]} '
                        BOT.restrict_chat_member(chat_id, user_id, until_date=datetime.datetime.now() + datetime.timedelta(minutes=30))
                        BOT.send_message(chat_id, f"Пользователь @{message.from_user.username} был заблокирован"
                                                  f" за спам бессмыслицей. Оспорить блокировку можно у администраторов "
                                                  f"этого канала {admins_list}")
                else:
                    short_messages[user_id] = 1
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

        elif message.content_type == 'animation': #Обработка спама gif
            file_name = message.document.file_name
            if (user_id, file_name) in spam_counter:
                spam_counter[(user_id, file_name)] += 1
                if spam_counter[(user_id, file_name)] == 3 or spam_counter[(user_id, file_name)] == 5:
                    if warnings_counter == 3:
                        block_user(user_id, chat_id, message)
                        return
                    if user_id in warnings_counter:
                        warnings_counter[user_id] += 1
                        if warnings_counter[user_id] == 3:
                            block_user(user_id, chat_id, message)
                            return
                    else:
                        warnings_counter[user_id] = 1
                    BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                              f'если вы продолжите спамить, то будете заблокированы')
            else:
                spam_counter[(user_id, file_name)] = 1

        elif message.content_type == 'video': #Обработка спама видео
            file_size = message.video.file_size
            if (user_id, file_size) in spam_counter:
                spam_counter[(user_id, file_size)] += 1
                if spam_counter[(user_id, file_size)] == 3 or spam_counter[(user_id, file_size)] == 5:
                    if warnings_counter == 3:
                        block_user(user_id, chat_id, message)
                        return
                    if user_id in warnings_counter:
                        warnings_counter[user_id] += 1
                        if warnings_counter[user_id] == 3:
                            block_user(user_id, chat_id, message)
                            return
                    else:
                        warnings_counter[user_id] = 1
                    BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                              f'если вы продолжите спамить, то будете заблокированы')
            else:
                spam_counter[(user_id, file_size)] = 1

        elif message.content_type == 'audio': #Обработка спама аудио
            file_size = message.audio.file_size
            if (user_id, file_size) in spam_counter:
                spam_counter[(user_id, file_size)] += 1
                if spam_counter[(user_id, file_size)] == 3 or spam_counter[(user_id, file_size)] == 5:
                    if warnings_counter == 3:
                        block_user(user_id, chat_id, message)
                        return
                    if user_id in warnings_counter:
                        warnings_counter[user_id] += 1
                        if warnings_counter[user_id] == 3:
                            block_user(user_id, chat_id, message)
                            return
                    else:
                        warnings_counter[user_id] = 1
                    BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                              f'если вы продолжите спамить, то будете заблокированы')
            else:
                spam_counter[(user_id, file_size)] = 1

        elif message.content_type == 'voice': #Обработка спама голосовыми сообщениями
            file_size = message.voice.file_size
            if file_size < 180000:
                if (user_id, 'Voice_spam') in spam_counter:
                    spam_counter[(user_id, 'Voice_spam')] += 1
                    if spam_counter[(user_id, 'Voice_spam')] == 3 or spam_counter[(user_id, 'Voice_spam')] == 5:
                        if warnings_counter == 3:
                            block_user(user_id, chat_id, message)
                            return
                        if user_id in warnings_counter:
                            warnings_counter[user_id] += 1
                            if warnings_counter[user_id] == 3:
                                block_user(user_id, chat_id, message)
                                return
                        else:
                            warnings_counter[user_id] = 1
                        BOT.send_message(chat_id, f'Внимание, {message.from_user.first_name}, '
                                                  f'Старайтесь излагать мысли целостными сообщениями,'
                                                  f' иначе вы будете заблокированы')
                    elif spam_counter[(user_id, 'Voice_spam')] == 7:
                        block_user(user_id, chat_id, message)
                        return
                else:
                    spam_counter[(user_id, 'Voice_spam')] = 1


@BOT.message_handler(func=lambda message: True, content_types=['new_chat_members']) #Обработчик присоединения новых пользователей
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
                if check_rule(chat_id, user_id, users_rule, member.username):
                   break


threading.Thread(target=timer_function, daemon=True).start()
BOT.polling(none_stop=True)
