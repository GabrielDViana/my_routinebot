#!/usr/bin/env python3

import json
import requests
import time
import urllib
from pathlib import Path
from dateutil import parser
import sqlalchemy
import db
from db import Task
import os
import json
import requests
from datetime import datetime


class Bot():
    def __init__(self):
        self.TOKEN = self.get_infos_file("/token_my_routinebot.txt", False)
        self.URL = "https://api.telegram.org/bot{}/".format(self.TOKEN)
        self.HELP = (
            "/new NOME\n"
            "/todo ID\n"
            "/doing ID\n"
            "/done ID\n"
            "/delete ID\n"
            "/rename ID NOME\n"
            "/dependson ID ID...\n"
            "/duplicate ID\n"
            "/priority ID PRIORITY{low, medium, high}\n"
            "/duedate ID DATE{dd/mm/aaaa}\n"
            "/list\n"
            "/help\n"
        )

    def get_infos_file(self, input_file, set_password=False):
        """
        Pega informações como token e identificações do arquivo de acordo
        com os parametros input_file e set_password
        """
        home = str(Path.home())
        with open(home + '/my_routinebot_files' + input_file) as infile:
            if set_password == True:
                lines = infile.readline()[1:]
            lines = infile.readline()
        info = ""
        for line in lines:
            info += line
        info = info.rstrip('\n')
        return info

    def make_github_issue(self, title, body=None):
        """
        Cria nova issue no repositório de acordo com a url
        """
        url = 'https://api.github.com/repos/TecProg-20181/my_routinebot/issues'
        session = requests.Session()
        session.auth = (self.get_infos_file("/username_git.txt", False),
                        self.get_infos_file("/username_git.txt", True))
        issue = {'title': title,
                 'body': body}
        r = session.post(url, json.dumps(issue))
        if r.status_code == 201:
            print ('Successfully created Issue {0:s}'.format(title))
        else:
            print ('Could not create Issue {0:s}'.format(title))
            print ('Response:', r.content)

    def get_url(self, url):
        """
        Retorna a url desejada
        """
        response = requests.get(url)
        content = response.content.decode("utf8")
        return content

    def get_json_from_url(self, url):
        """
        Retorna json a partir da url desejada
        """
        content = self.get_url(url)
        js = json.loads(content)
        return js

    def get_updates(self, offset=None):
        """
        Retorna updates do bot com timeout = 100
        """
        url = self.URL + "getUpdates?timeout=100"
        if offset:
            url += "&offset={}".format(offset)
        js = self.get_json_from_url(url)
        return js

    def send_message(self, text, chat_id, reply_markup=None):
        """
        Retorna mensagem a ser mostrada para o usuário pelo bot
        """
        text = urllib.parse.quote_plus(text)
        url = self.URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown"\
                         .format(text, chat_id)
        if reply_markup:
            url += "&reply_markup={}".format(reply_markup)
        self.get_url(url)

    def get_last_update_id(self, updates):
        """
        Pega id do último update do bot
        """
        update_ids = []
        for update in updates["result"]:
            update_ids.append(int(update["update_id"]))
        return max(update_ids)

class HandleTask(Bot):
    def __init__(self):
        Bot.__init__(self)

    def query_one(self, task_id, chat):
        """
        Realiza query de uma linha do banco de acordo com seu id
        """
        query = db.session.query(Task).filter_by(id=task_id,
                                                 chat=chat)
        task = query.one()
        return task

    def task_not_found_msg(self, task_id, chat):
        """
        Retorna mensagem em que a task não foi encontrada
        """
        self.send_message("_404_ Task {} not found x.x"\
                     .format(task_id), chat)

    def check_msg_not_exists(self, msg):
        """
        Retorna True caso a mensagem não for um dígito
        """
        if not msg.isdigit():
            return True

    def msg_no_task(self, chat):
        """
        Retorna mensagem pedindo para o usuário informar o id da task
        """
        self.send_message("You must inform the task id", chat)

    def new_task(self, command, msg, chat):
        """
        Retorna uma nova task e abre uma nova issue no repositório
        """
        msg = [i.strip() for i in msg.split(',')]
        for i in range(len(msg)):
            task = Task(chat=chat, name=''.join(msg[i]), status='TODO',
                        dependencies='', parents='', priority='')
            print('\ntask',task)
            db.session.add(task)
            db.session.commit()
            text_message = 'New task *TODO* [[{}]] {}'
            self.send_message(text_message\
                        .format(task.id, task.name), chat)
            # self.make_github_issue(task.name, 'Task of ID:[[{}]].\n\
            #                                    Name of task:{}'
            #                                    .format(task.id, task.name))

    def condition_len_msg(self, msg):
        """
        Retorna true caso o tamanho da mensagem seja maior que uma palavra
        """
        if len(msg.split(' ', 1)) > 1:
            return True

    def split_msg(self, msg, element):
        """
        Realiza o split de uma mensagem
        """
        return msg.split(' ', 1)[element]

    def msg_not_empty(self, msg):
        """
        Retorna true caso a mensagem não esteja vazia
        """
        if msg != '':
            return True

    def rename(self, command, msg, chat):
        """
        Renomeia uma task
        """
        text = ''
        if self.msg_not_empty(msg):
            if self.condition_len_msg(msg):
                text = self.split_msg(msg, 1)
            msg = self.split_msg(msg, 0)

        if self.check_msg_not_exists(msg):
            self.msg_no_task(chat)
        else:
            task_id = int(msg)
            query = db.session.query(Task).filter_by(id=task_id,
                                                     chat=chat)
            try:
                task = self.query_one(task_id, chat)
            except sqlalchemy.orm.exc.NoResultFound:
                self.task_not_found_msg(task_id, chat)
                return

            if text == '':
                text_message = ("You want to modify task {},"
                    " but you didn't provide any new text")
                self.send_message(text_message\
                              .format(task_id), chat)
                return

            old_text = task.name
            task.name = text
            db.session.commit()
            text_message = ("taks {} renamed")
            self.send_message(text_message\
                         .format(task_id, old_text, text), chat)

    def deps_text(self, task, chat, preceed=''):
        """
        Retorna texto para tasks com dependência
        """
        text = ''
        for i in range(len(task.dependencies.split(',')[:-1])):
            line = preceed
            query = db.session.query(Task)\
                                     .filter_by(id=int(task.dependencies\
                                                .split(',')[:-1][i]),\
                                                chat=chat)
            dep = query.one()

            icon = '\U0001F195'
            if dep.status == 'DOING':
                icon = '\U000023FA'
            elif dep.status == 'DONE':
                icon = '\U00002611'

            if i + 1 == len(task.dependencies.split(',')[:-1]):
                if dep.duedate:
                    line += '└── [[{}]] {} {} \U0001F4C6{}\n'.format(dep.id, icon, dep.name, dep.duedate) #
                else:
                    line += '└── [[{}]] {} {}\n'.format(dep.id, icon, dep.name)
                line += self.deps_text(dep, chat, preceed + '    ')
            else:
                if dep.duedate:
                    line += '├── [[{}]] {} {} \U0001F4C6{}\n'.format(dep.id, icon, dep.name, dep.duedate) # mais de uma dependencia
                else:
                    line += '├── [[{}]] {} {}\n'.format(dep.id, icon, dep.name) # mais de uma dependencia
                line += self.deps_text(dep, chat, preceed + '│   ')

            text += line
        return text

    def duplicate(self, command, msg, chat):
        """
        Duplica uma task
        """
        if self.check_msg_not_exists(msg):
            self.msg_no_task(chat)
        else:
            task_id = int(msg)
            query = db.session.query(Task).filter_by(id=task_id, chat=chat)
            try:
                task = self.query_one(task_id, chat)
            except sqlalchemy.orm.exc.NoResultFound:
                self.task_not_found_msg(task_id, chat)
                return


            dep_task = Task(chat=task.chat, name=task.name, status=task.status,
                         dependencies=task.dependencies, parents=task.parents,
                         priority=task.priority, duedate=task.duedate)
            db.session.add(dep_task)

            for t in task.dependencies.split(',')[:-1]:
                query_dep = db.session.query(Task).\
                                            filter_by(id=int(t),\
                                                      chat=chat)
                t = query_dep.one()
                t.parents += '{},'.format(dep_task.id)
            db.session.commit()
            text_message = 'New task *TODO* [[{}]] {}'
            self.send_message(text_message\
                        .format(dep_task.id, dep_task.name), chat)

    def delete(self, command, msg, chat):
        """
        Deleta uma task
        """
        if self.check_msg_not_exists(msg):
            self.msg_no_task(chat)
        else:
            task_id = int(msg)
            query = db.session.query(Task)\
                                     .filter_by(id=task_id, chat=chat)
            task = self.query_one(task_id, chat)

            for t in task.dependencies.split(',')[:-1]:
                query_dep = db.session.query(Task)\
                                      .filter_by(id=int(t), chat=chat)
                try:
                    t = query_dep.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    self.task_not_found_msg(task_id, chat)
                    return
                t.parents = t.parents\
                            .replace('{},'.format(task.id), '')

            if task.parents:
                for t in task.parents.split(',')[:-1]:
                    query_par = db.session.query(Task)\
                                      .filter_by(id=int(t), chat=chat)
                    try:
                        t = query_par.one()
                    except sqlalchemy.orm.exc.NoResultFound:
                        self.task_not_found_msg(task_id, chat)
                        return

                    task_dep = t.dependencies.split(',')
                    task_dep.pop()
                    if task_dep == None:
                        task_dep = ''.join(task_dep)
                    else:
                        task_dep.remove(str(task_id))
                        task_dep = ','.join(task_dep)
                        if len(task_dep) > 0:
                            task_dep = task_dep + ','

                    t.dependencies = task_dep

            db.session.delete(task)
            db.session.commit()
            text_message = 'Task [[{}]] deleted'
            self.send_message(text_message\
                         .format(task_id), chat)

    def todo(self, command, msg, chat):
        """
        Adiciona uma task para o status TODO
        """
        if not [s for s in msg if s.isdigit()]:
            self.msg_no_task(chat)
        else:
            msg = [i.strip() for i in msg.split(',')]
            for i in range(len(msg)):
                task_id = int(''.join(msg[i]))
                query = db.session.query(Task)\
                                        .filter_by(id=task_id, chat=chat)
                try:
                    task = self.query_one(task_id, chat)
                except sqlalchemy.orm.exc.NoResultFound:
                    self.task_not_found_msg(task_id, chat)
                    return
                task.status = 'TODO'
                db.session.commit()
                text_message = '*TODO* task [[{}]] {}'
                self.send_message(text_message\
                             .format(task.id, task.name), chat)

    def doing(self, command, msg, chat):
        """
        Adiciona uma task para o status DOING
        """
        if not [s for s in msg if s.isdigit()]:
            self.msg_no_task(chat)
        else:
            msg = [i.strip() for i in msg.split(',')]
            for i in range(len(msg)):
                task_id = int(''.join(msg[i]))
                query = db.session.query(Task)\
                                         .filter_by(id=task_id, chat=chat)
                try:
                    task = self.query_one(task_id, chat)
                except sqlalchemy.orm.exc.NoResultFound:
                    self.task_not_found_msg(task_id, chat)
                    return
                task.status = 'DOING'
                db.session.commit()
                text_message = '*DOING* task [[{}]] {}'
                self.send_message(text_message\
                             .format(task.id, task.name), chat)

    def done(self, command, msg, chat):
        """
        Adiciona uma task para o status DONE
        """
        if not [s for s in msg if s.isdigit()]:
            self.msg_no_task(chat)
        else:
            msg = [i.strip() for i in msg.split(',')]
            for i in range(len(msg)):
                task_id = int(''.join(msg[i]))
                query = db.session.query(Task)\
                                  .filter_by(id=task_id, chat=chat)
                try:
                    task = self.query_one(task_id, chat)
                except sqlalchemy.orm.exc.NoResultFound:
                    self.task_not_found_msg(task_id, chat)
                    return

                task.status = 'DONE'
                db.session.commit()
                text_message = '*DONE* task [[{}]] {}'
                self.send_message(text_message\
                             .format(task.id, task.name), chat)

    def task_status(self, status, chat):
        """
        Retorna a mensagem informando o status da task ao usuário
        """
        msg_user = ''

        if status == 'TODO':
            msg_user += '\n\U0001F195 *TODO*\n'
        elif status == 'DOING':
            msg_user += '\n\U0001F563 *DOING*\n'
        elif status == 'DONE':
            msg_user += '\n\U00002611 *DONE*\n'

        query = db.session.query(Task)\
                                 .filter_by(status=status, chat=chat)\
                                 .order_by(Task.id)

        for task in query.all():
            msg_user += '\u27A1[[{}]] {}\n'.format(task.id, task.name)

        return msg_user

    def task_priority(self, priority, chat):
        """
        Retorna a mensagem informando a prioridade da task ao usuário
        """
        msg_user = ''

        if priority == 'high':
            msg_user += '\U0001F198 high priority\n'
        elif priority == 'medium':
            msg_user += '\u203C medium priority\n'
        elif priority == 'low':
            msg_user += '\u2757 low priority\n'

        query = db.session.query(Task)\
                                 .filter_by(priority=priority, chat=chat)\
                                 .order_by(Task.id)

        for task in query.all():
            msg_user += '\u27A1[[{}]] {}\n'.format(task.id, task.name)

        return msg_user

    def list(self, command, msg, chat):
        """
        Lista todas tasks suas prioridades, status e duedates
        """
        msg_user = ''

        msg_user += '\U0001F4CB Task List\n'
        query = db.session.query(Task)\
                                .filter_by(parents='',\
                                           chat=chat).order_by(Task.id)
        for task in query.all():
            icon = '\U0001F195'
            if task.status == 'DOING':
                icon = '\U0001F563'
            elif task.status == 'DONE':
                icon = '\U00002611'
            elif task.priority == 'priority':
                icon = 'u"\U0001F6A8"'

            if task.duedate:
                msg_user += "[[{}]] {} {} \U0001F4C6{}\n".format(task.id,\
                                                            icon, task.name,\
                                                            task.duedate)
            else:
                msg_user += '[[{}]] {} {}\n'.format(task.id, icon, task.name)
            msg_user += self.deps_text(task, chat)

        self.send_message(msg_user, chat)
        msg_user = ''

        msg_user += '\U0001F4DD _Status_\n'
        msg_user += self.task_status('TODO', chat)
        msg_user += self.task_status('DOING', chat)
        msg_user += self.task_status('DONE', chat)


        msg_user += '\n\U0001F6A8 *PRIORITY*\n'
        msg_user += self.task_priority('high', chat)
        msg_user += self.task_priority('medium', chat)
        msg_user += self.task_priority('low', chat)

        self.send_message(msg_user, chat)

    def search_parent(self, task, target, chat):
        """
        Busca os pais de uma task utilizando recursividade
        """
        if not task.parents == '':
            parent_id = task.parents.split(',')
            parent_id.pop()

            numbers = [ int(id_pai) for id_pai in parent_id ]

            if target in numbers:
                return False
            else:
                parent = self.query_one(numbers[0], chat)
                return self.search_parent(parent, target, chat)

        return True

    def dependson(self, command, msg, chat):
        """
        Adiciona dependência a uma task
        """
        text = ''
        if self.msg_not_empty(msg):
            if self.condition_len_msg(msg):
                text = self.split_msg(msg, 1)
            msg = self.split_msg(msg, 0)

        if self.check_msg_not_exists(msg):
            self.msg_no_task(chat)
        else:
            task_id = int(msg)
            query = db.session.query(Task).filter_by(id=task_id,\
                                                     chat=chat)
            try:
                task = self.query_one(task_id, chat)
            except sqlalchemy.orm.exc.NoResultFound:
                self.task_not_found_msg(task_id, chat)
                return

            if text == '':
                for i in task.dependencies.split(',')[:-1]:
                    i = int(i)
                    q = db.session.query(Task).filter_by(id=i,\
                                                         chat=chat)
                    t = q.one()
                    t.parents = t.parents.replace('{},'\
                                                  .format(task.id), '')

                task.dependencies = ''
                self.send_message("Dependencies removed from task {}"\
                             .format(task_id), chat)
            else:
                for depid in text.split(' '):
                    if not depid.isdigit():
                        self.send_message("All dependencies ids must be"
                                      " numeric, and not {}"\
                                      .format(depid), chat)
                    else:
                        depid = int(depid)
                        query = db.session.query(Task)\
                                                 .filter_by(id=depid,\
                                                 chat=chat)
                        try:
                            taskdep = self.query_one(depid, chat)
                            list_dependencies = taskdep.dependencies\
                                                       .split(',')

                            if self.search_parent(task, taskdep.id, chat):
                                taskdep.parents += str(task.id) + ','
                            else:
                                self.send_message("Essa tarefa já é filha"
                                              " da sub tarefa", chat)
                                break
                        except sqlalchemy.orm.exc.NoResultFound:
                            self.task_not_found_msg(task_id, chat)
                            continue
                        deplist = task.dependencies.split(',')
                        if str(depid) not in deplist:
                            task.dependencies += str(depid) + ','

            db.session.commit()
            text_message = 'Task {} dependencies up to date'
            self.send_message(text_message\
                         .format(task_id), chat)

    def priority(self, command, msg, chat):
        """
        Adiciona a prioridade a uma task
        """
        text = ''
        if self.msg_not_empty(msg):
            if self.condition_len_msg(msg):
                text = self.split_msg(msg, 1)
            msg = self.split_msg(msg, 0)

        if self.check_msg_not_exists(msg):
            self.msg_no_task(chat)
        else:
            task_id = int(msg)
            query = db.session.query(Task)\
                                     .filter_by(id=task_id, chat=chat)
            try:
                task = self.query_one(task_id, chat)
            except sqlalchemy.orm.exc.NoResultFound:
                self.task_not_found_msg(task_id, chat)
                return


            if text == '':
                task.priority = ''
                self.send_message("_Cleared_ all priorities from task {}"\
                             .format(task_id), chat)
            else:
                if text.lower() not in ['high', 'medium', 'low']:
                    self.send_message("The priority *must be* one of the"
                                 " following: high, medium, low", chat)
                else:
                    task.priority = text.lower()
                    self.send_message("*Task {}* priority has priority"
                                 " *{}*".format(task_id, text.lower()),\
                                 chat)
            db.session.commit()

    def correct_date(self, text):
        """
        Retorna True caso o formato de data seja válido, False caso contrário
        """
        try:
            datetime.strptime(text, '%d/%m/%Y')
            return True
        except ValueError:
            return False


    def duedate(self, command, msg, chat):
        """
        Define a duedate de uma task
        """
        text = ''

        msg = [i.strip() for i in msg.split(',')]
        print('msg',msg)
        for i in range(len(msg)):
            if msg is not None:
                if len(msg[i].split(' ', 1)) > 1:
                    text = msg[i].split(' ')[1]
                msg_indice = msg[i].split(' ')[0]


            if not [s for s in msg_indice if s.isdigit()]:
                self.msg_no_task(chat)
            else:
                task_id = int(msg_indice)
                print('task_id',task_id)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    self.task_not_found_msg(task_id, chat)
                    return

                if text == '':
                    task.duedate = None
                    self.send_message("_Cleared_ all duedates"
                                " from task {}".format(task_id), chat)
                else:
                    if not self.correct_date(text):
                        self.send_message("The duedate *must follow* "
                                        "the pattern: dd/mm/aaaa", chat)
                    else:
                        task.duedate = datetime.strptime(text, '%d/%m/%Y')
                        self.send_message("*Task {}* duedate:"
                                " *{}*".format(task_id, text.lower()), chat)
                db.session.commit()

    def handle_updates(self, updates):
        """
        Loop em que todas funções do bot são realizadas
        """
        for update in updates["result"]:
            if 'message' in update:
                message = update['message']
            elif 'edited_message' in update:
                message = update['edited_message']
            else:
                print('Can\'t process! {}'.format(update))
                return

            command = message["text"].split(" ", 1)[0]
            msg = ''
            if len(message["text"].split(" ", 1)) > 1:
                msg = message["text"].split(" ", 1)[1].strip()

            chat = message["chat"]["id"]
            print(command, msg, chat)

            if command == '/new':
                self.new_task(command, msg, chat)

            elif command == '/rename':
                self.rename(command, msg, chat)

            elif command == '/duplicate':
                self.duplicate(command, msg, chat)

            elif command == '/delete':
                self.delete(command, msg, chat)

            elif command == '/todo':
                self.todo(command, msg, chat)

            elif command == '/doing':
                self.doing(command, msg, chat)

            elif command == '/done':
                self.done(command, msg, chat)

            elif command == '/list':
                self.list(command, msg, chat)

            elif command == '/dependson':
                self.dependson(command, msg, chat)

            elif command == '/priority':
                self.priority(command, msg, chat)

            elif command == '/duedate':
                self.duedate(command, msg, chat)

            elif command == '/start':
                self.send_message("Welcome! Here is msg_user list of things you can do."\
                             , chat)
                self.send_message(self.HELP, chat)

            elif command == '/help':
                self.send_message("Here is msg_user list of things you can do.", chat)
                self.send_message(self.HELP, chat)
            else:
                self.send_message("I'm sorry dave. I'm afraid I can't do that."\
                             , chat)



def main():
    """
    Função em que é instanciado o bot
    """
    last_update_id = None
    task = HandleTask()
    while True:
        print("Updates")
        updates = task.get_updates(last_update_id)

        if len(updates["result"]) > 0:
            last_update_id = task.get_last_update_id(updates) + 1
            task.handle_updates(updates)

        time.sleep(0.5)


if __name__ == '__main__':
    main()
