import sys
import threading
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel, QObject, pyqtSignal, QTimer
import sqlite3
import requests


# Глобальная переменная для хранения последних загруженных постов
latest_posts_data = None


class Communicator(QObject):
    update_progress_signal = pyqtSignal(int)  # Новый сигнал для обновления прогресса
    update_ui_signal = pyqtSignal(bool)

communicator = Communicator()


def initialize_posts_database():
    connection = sqlite3.connect('user_posts.db')
    cursor = connection.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_posts (
        post_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        post_title TEXT,
        post_body TEXT
    )
    ''')

    connection.commit()
    connection.close()


def retrieve_posts_from_api():
    api_url = 'https://jsonplaceholder.typicode.com/posts'
    response = requests.get(api_url)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching data:", response.status_code)
        return []


def store_posts_in_database(posts):
    connection = sqlite3.connect('user_posts.db')
    cursor = connection.cursor()
    cursor.execute('DELETE FROM user_posts')

    for post in posts:
        cursor.execute('''
        INSERT INTO user_posts (post_id, user_id, post_title, post_body)
        VALUES (?, ?, ?, ?)
        ''', (post['id'], post['userId'], post['title'], post['body']))

    connection.commit()
    connection.close()


def fetch_all_posts():
    connection = sqlite3.connect('user_posts.db')
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM user_posts')
    all_posts = cursor.fetchall()
    connection.close()
    return all_posts


def insert_post(post):
    connection = sqlite3.connect('user_posts.db')
    cursor = connection.cursor()
    cursor.execute('''
    INSERT INTO user_posts (user_id, post_title, post_body)
    VALUES (?, ?, ?)
    ''', (post["user_id"], post["post_title"], post["post_body"]))
    connection.commit()
    connection.close()


def delete_post(post_id):
    connection = sqlite3.connect('user_posts.db')
    cursor = connection.cursor()
    cursor.execute('DELETE FROM user_posts WHERE post_id = ?', (post_id,))
    connection.commit()
    connection.close()


initialize_posts_database()


class PostsModel(QAbstractTableModel):
    def __init__(self, data):
        super(PostsModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.DisplayRole:
            value = self._data[index.row()][index.column()]
            return str(value)

    def rowCount(self, index):
        return len(self._data)

    def columnCount(self, index):
        return len(self._data[0])

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            headers = ["ID", "User ID", "Title", "Body"]
            return headers[section]


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.initializeUI()

    def initializeUI(self):
        self.setMinimumSize(800, 600)
        self.setWindowTitle("Posts Manager")

        self.createMenu()
        self.createWidgets()
        self.show()

        communicator.update_progress_signal.connect(self.progress_update)
        communicator.update_ui_signal.connect(self.update_table_view)

        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer_timeout)
        self.timer.start(10000)  # Запускаем таймер каждые 10 секунд

    def createMenu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def createWidgets(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.post_table = QTableView()
        self.post_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.post_table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search by title...")
        self.search_field.textChanged.connect(self.filter_table)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_table)

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.open_add_dialog)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_record)

        self.download_button = QPushButton("Download Data")
        self.download_button.clicked.connect(self.on_download_click)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)  # Диапазон от 0 до 100%

        main_vbox = QVBoxLayout()
        main_vbox.addWidget(self.search_field)
        main_vbox.addWidget(self.post_table)
        main_hbox = QHBoxLayout()
        main_hbox.addStretch()
        main_hbox.addWidget(self.refresh_button)
        main_hbox.addWidget(self.add_button)
        main_hbox.addWidget(self.delete_button)
        main_hbox.addWidget(self.download_button)
        main_vbox.addLayout(main_hbox)
        main_vbox.addWidget(self.progress_bar)

        self.central_widget.setLayout(main_vbox)

        self.refresh_table()

    def refresh_table(self):
        # Данные из бд
        all_posts = fetch_all_posts()
        self.data = [[post[0], post[1], post[2], post[3]] for post in all_posts]

        self.model = PostsModel(self.data)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.post_table.setModel(self.proxy_model)

    def filter_table(self, text):
        self.proxy_model.setFilterWildcard(f"*{text}*")

    def open_add_dialog(self):
        dialog = AddPostDialog(self)
        if dialog.exec_():
            new_post = {
                "user_id": int(dialog.user_id_edit.text()),
                "post_title": dialog.title_edit.text(),
                "post_body": dialog.body_edit.toPlainText()
            }
            insert_post(new_post)
            self.refresh_table()

    def delete_record(self):
        selected_row = self.post_table.selectionModel().currentIndex().row()
        if selected_row >= 0:
            id_to_delete = self.data[selected_row][0]
            delete_post(id_to_delete)
            self.refresh_table()

    def on_download_click(self):
        threading.Thread(target=self.download_posts).start()

    def download_posts(self):
        try:
            communicator.update_progress_signal.emit(0)  # Начальное значение прогресса
            posts_data = retrieve_posts_from_api()
            communicator.update_progress_signal.emit(50)  # Прогресс на полпути
            store_posts_in_database(posts_data)
            communicator.update_progress_signal.emit(100)  # Завершение процесса
            communicator.update_ui_signal.emit(True)

            # Сбрасываем прогрессбар через 10 секунд
            QTimer.singleShot(10000, self.reset_progress)
        except Exception as e:
            print(f"Error during downloading or storing posts: {e}")

    def update_table_view(self, success):
        if success:
            self.refresh_table()

    def on_timer_timeout(self):
        threading.Thread(target=self.check_for_updates).start()

    def check_for_updates(self):
        global latest_posts_data

        latest_posts = retrieve_posts_from_api()
        if latest_posts != latest_posts_data:
            store_posts_in_database(latest_posts)
            latest_posts_data = latest_posts
            communicator.update_ui_signal.emit(True)

    def progress_update(self, value):
        self.progress_bar.setValue(value)

    def reset_progress(self):
        """Сброс прогресса через 10 секунд."""
        self.progress_bar.setValue(0)


class AddPostDialog(QDialog):
    def __init__(self, parent):
        super(AddPostDialog, self).__init__(parent)

        self.setWindowTitle("Add New Post")

        self.user_id_edit = QLineEdit()
        self.title_edit = QLineEdit()
        self.body_edit = QTextEdit()

        form_layout = QFormLayout()
        form_layout.addRow("User ID", self.user_id_edit)
        form_layout.addRow("Title", self.title_edit)
        form_layout.addRow("Body", self.body_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addWidget(button_box)

        self.setLayout(main_layout)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
