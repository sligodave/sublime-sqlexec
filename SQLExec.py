
import tempfile
import os
import subprocess
import threading
import datetime

import sublime
import sublime_plugin


connection = None
history = ['']
threads = []
start_times = []


class Connection:
    def __init__(self, options):
        self.settings = sublime.load_settings(options.type + ".sqlexec").get('sql_exec')
        self.command = sublime.load_settings(
            "SQLExec.sublime-settings").get('sql_exec.commands')[options.type]
        self.options = options

    def _buildCommand(self, options):
        args = self.settings['args'].format(options=self.options)
        command = '%s %s %s' % (self.command, ' '.join(options), args)
        return command

    def _getCommand(self, options, queries):
        command = self._buildCommand(options)
        self.tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sql')
        for query in self.settings['before']:
            self.tmp.write(query + "\n")
        for query in queries:
            self.tmp.write(query)
        self.tmp.close()

        cmd = '%s < "%s"' % (command, self.tmp.name)

        return Command(cmd)

    def execute(self, queries):
        command = self._getCommand(self.settings['options'], queries)
        self.show(command)

    def desc(self):
        query = self.settings['queries']['desc']['query']
        command = self._getCommand(self.settings['queries']['desc']['options'], query)

        tables = []
        for result in command.run().splitlines():
            try:
                tables.append(result.split('|')[1].strip())
            except IndexError:
                pass
        return tables

    def descTable(self, tableName):
        query = self.settings['queries']['desc table']['query'] % tableName
        command = self._getCommand(self.settings['queries']['desc table']['options'], query)
        self.show(command)

    def showTableRecords(self, tableName):
        query = self.settings['queries']['show records']['query'] % tableName
        command = self._getCommand(self.settings['queries']['show records']['options'], query)
        self.show(command)

    def show(self, command):
        def _show():
            command.show()
            os.unlink(self.tmp.name)
            thread = threading.current_thread()
            if thread in threads:
                i = threads.index(thread)
                del start_times[i]
                del threads[i]
        thread = threading.Thread(target=_show, daemon=False)
        thread.command = command
        thread.query = open(self.tmp.name).read()[:301]
        threads.append(thread)
        start_times.append(datetime.datetime.now())
        thread.start()


class Command:
    def __init__(self, text):
        self.text = text

    def _display(self, text):
        panelName = 'SQLExec.result'
        if not sublime.load_settings("SQLExec.sublime-settings").get('show_result_on_window'):
            panel = sublime.active_window().create_output_panel(panelName)
            sublime.active_window().run_command("show_panel", {"panel": "output." + panelName})
        else:
            panel = sublime.active_window().new_file()
            panel.set_scratch(True)

        panel.set_read_only(False)
        panel.set_syntax_file('Packages/SQL/SQL.tmLanguage')
        panel.run_command('append', {'characters': text})
        panel.set_read_only(True)

    def run(self):
        start_time = datetime.datetime.now()
        sublime.status_message(' SQLExec: running SQL command')

        pipe = subprocess.Popen(
            self.text, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
        )
        results, errors = pipe.communicate()

        errors = errors.replace(b'Warning: Using a password on the command '
                                b'line interface can be insecure.\n', b'')

        elapsed = str(datetime.datetime.now() - start_time).encode('utf-8')
        elapsed = elapsed if elapsed.find(b'.') == -1 else elapsed[:elapsed.find(b'.')]
        elapsed = b'Elapsed: ' + elapsed + b'\n'

        if not results and not errors:
            results = b'Empty set returned\n'
        if errors:
            errors += b'\n'

        sublime.status_message(' SQLExec: finished SQL command')
        text = elapsed + errors + results
        return text

    def show(self):
        text = self.run()
        self._display(text.decode('utf-8', 'replace').replace('\r', ''))


class Selection:
    def __init__(self, view):
        self.view = view

    def getQueries(self):
        text = []
        if self.view.sel():
            for region in self.view.sel():
                if region.empty():
                    text.append(self.view.substr(self.view.line(region)))
                else:
                    text.append(self.view.substr(region))
        return text


class Options:
    def __init__(self, name):
        self.name = name
        connections = sublime.load_settings("SQLExec.sublime-settings").get('connections')
        self.type = connections[self.name]['type']
        self.host = connections[self.name]['host']
        self.port = connections[self.name]['port']
        self.username = connections[self.name]['username']
        self.password = connections[self.name]['password']
        self.database = connections[self.name]['database']
        if 'service' in connections[self.name]:
            self.service = connections[self.name]['service']

    def __str__(self):
        return self.name

    @staticmethod
    def list():
        names = []
        connections = sublime.load_settings("SQLExec.sublime-settings").get('connections')
        for connection in connections:
            names.append(connection)
        names.sort()
        return names


def sqlChangeConnection(index):
    global connection
    names = Options.list()
    options = Options(names[index])
    connection = Connection(options)
    sublime.status_message(' SQLExec: switched to %s' % names[index])


def showTableRecords(index):
    global connection
    if index > -1:
        if connection is not None:
            tables = connection.desc()
            connection.showTableRecords(tables[index])
        else:
            sublime.error_message('No active connection')


def descTable(index):
    global connection
    if index > -1:
        if connection is not None:
            tables = connection.desc()
            connection.descTable(tables[index])
        else:
            sublime.error_message('No active connection')


def executeHistoryQuery(index):
    global history
    if index > -1:
        executeQuery(history[index])


def executeQuery(query):
    global connection
    global history
    history.append(query)
    if connection is not None:
        connection.execute(query)


class sqlHistory(sublime_plugin.WindowCommand):
    global history

    def run(self):
        sublime.active_window().show_quick_panel(history, executeHistoryQuery)


class sqlDesc(sublime_plugin.WindowCommand):

    def run(self):
        global connection
        if connection is not None:
            tables = connection.desc()
            sublime.active_window().show_quick_panel(tables, descTable)
        else:
            sublime.error_message('No active connection')


class sqlShowRecords(sublime_plugin.WindowCommand):
    def run(self):
        global connection
        if connection is not None:
            tables = connection.desc()
            sublime.active_window().show_quick_panel(tables, showTableRecords)
        else:
            sublime.error_message('No active connection')


class sqlQuery(sublime_plugin.WindowCommand):
    def run(self):
        global connection
        global history
        if connection is not None:
            window = sublime.active_window()
            window.show_input_panel('Enter query', history[-1], executeQuery, None, None)
        else:
            sublime.error_message('No active connection')


class sqlExecute(sublime_plugin.WindowCommand):
    def run(self):
        global connection
        if connection is not None:
            selection = Selection(self.window.active_view())
            connection.execute(selection.getQueries())
        else:
            sublime.error_message('No active connection')


class sqlListConnection(sublime_plugin.WindowCommand):
    def run(self):
        sublime.active_window().show_quick_panel(Options.list(), sqlChangeConnection)


class sqlListThreadsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not threads:
            sublime.message_dialog('No running queries.')
        else:
            text = ''
            hr = '-' * 64
            for i, thread in enumerate(threads):
                st = start_times[i]
                rt = str(datetime.datetime.now() - st)
                rt = rt if rt.find('.') == -1 else rt[:rt.find('.')]
                st = st.strftime('%Y-%m-%d %H:%M:%S')
                text += 'Running Query %d (Started: %s, Elapsed: %s)\n%s\n' % (i + 1, st, rt, hr)
                text += thread.query[:300]
                text += '...' if len(thread.query) > 300 else ''
                text += '\n%s\n' % (hr)
            panel_name = 'running_queries'
            panel = sublime.active_window().create_output_panel(panel_name)
            panel.run_command('append', {'characters': text})
            sublime.active_window().run_command("show_panel", {"panel": "output." + panel_name})
