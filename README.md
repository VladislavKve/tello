# DJI Tello Talent - Python SDK

Полнофункциональный Python SDK для работы с дроном DJI Tello Talent, включающий мониторинг статуса и работу с видео потоком.

## 🚁 Возможности

### Мониторинг статуса дрона
- ✅ Подключение к дрону через WiFi
- 📊 Получение данных о батарее, температуре, высоте
- 📡 Мониторинг WiFi сигнала и скорости
- 🔄 Непрерывный мониторинг в реальном времени
- 💾 Экспорт данных в JSON

### Видео поток
- 📹 Получение видео с камеры дрона в реальном времени
- 🖥️ Отображение видео в окне OpenCV
- 🎥 Запись видео в файл
- 📸 Сохранение скриншотов
- 🔧 Обработка кадров с применением фильтров
- 📊 Отображение FPS и статистики
- 🎛️ Callback функции для обработки кадров

## 📋 Требования

### Системные требования
- Python 3.7+
- Windows/Linux/macOS
- WiFi подключение к дрону DJI Tello Talent

### Зависимости
```bash
pip install -r requirements.txt
```

Основные библиотеки:
- `opencv-python>=4.8.0` - для работы с видео
- `numpy>=1.24.0` - для обработки данных
- `matplotlib>=3.7.0` - для визуализации
- `pillow>=10.0.0` - для работы с изображениями

## 🚀 Быстрый старт

### 1. Подготовка дрона
1. Включите дрон DJI Tello Talent
2. Подключитесь к WiFi сети дрона (обычно `TELLO-XXXXXX`)
3. Убедитесь, что IP адрес дрона `192.168.10.1`

### 2. Мониторинг статуса
```python
from tello_status import TelloTalentStatus

# Создание экземпляра
tello = TelloTalentStatus()

# Подключение и мониторинг
if tello.connect():
    tello.start_status_monitoring()
    time.sleep(3)
    tello.print_status()
    tello.disconnect()
```

### 3. Видео поток
```python
from tello_video import TelloVideoStream

# Создание экземпляра
tello_video = TelloVideoStream()

# Подключение и запуск видео
if tello_video.connect():
    if tello_video.start_video_stream():
        # Отображение видео
        display_video_stream(tello_video)
    tello_video.disconnect()
```

## 📁 Структура проекта

```
tello/
├── tello_status.py          # Основной класс для мониторинга статуса
├── tello_video.py           # Основной класс для работы с видео
├── example_usage.py         # Примеры использования статуса
├── video_example.py         # Примеры использования видео
├── requirements.txt         # Зависимости
└── README.md               # Документация
```

## 🎯 Примеры использования

### Базовый мониторинг статуса
```python
from tello_status import TelloTalentStatus

with TelloTalentStatus() as tello:
    if tello.connect():
        tello.start_status_monitoring()
        time.sleep(3)
        
        # Получение конкретных параметров
        battery = tello.get_battery()
        temperature = tello.get_temperature()
        height = tello.get_height()
        
        print(f"🔋 Батарея: {battery}%")
        print(f"🌡️ Температура: {temperature}°C")
        print(f"📏 Высота: {height} см")
```

### Видео с обработкой
```python
from tello_video import TelloVideoStream
import cv2

def process_frame(frame):
    # Применение фильтра размытия
    blurred = cv2.GaussianBlur(frame, (15, 15), 0)
    return blurred

tello_video = TelloVideoStream()
tello_video.set_frame_callback(process_frame)

if tello_video.connect():
    if tello_video.start_video_stream():
        display_video_stream(tello_video)
    tello_video.disconnect()
```

### Запись видео
```python
from tello_video import TelloVideoStream
import cv2

tello_video = TelloVideoStream()

if tello_video.connect():
    if tello_video.start_video_stream():
        # Настройка записи
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter('tello_video.mp4', fourcc, 30.0, (960, 720))
        
        # Запись в течение 30 секунд
        start_time = time.time()
        while time.time() - start_time < 30:
            frame = tello_video.get_current_frame()
            if frame is not None:
                out.write(frame)
            time.sleep(0.03)
        
        out.release()
    tello_video.disconnect()
```

## 🎮 Управление видео

При отображении видео доступны следующие клавиши:
- `q` или `ESC` - выход из программы
- `s` - сохранить скриншот
- `r` - начать/остановить запись видео

## 📊 API Reference

### TelloTalentStatus

#### Методы подключения
- `connect()` - подключение к дрону
- `disconnect()` - отключение от дрона
- `start_status_monitoring()` - запуск мониторинга статуса
- `stop_status_monitoring()` - остановка мониторинга

#### Получение данных
- `get_status()` - получение всех данных статуса
- `get_battery()` - уровень заряда батареи
- `get_temperature()` - температура дрона
- `get_height()` - высота полета
- `get_speed()` - скорость дрона
- `get_wifi_signal()` - сила WiFi сигнала

### TelloVideoStream

#### Методы подключения
- `connect()` - подключение к дрону
- `disconnect()` - отключение от дрона
- `start_video_stream()` - запуск видео потока
- `stop_video_stream()` - остановка видео потока

#### Работа с видео
- `get_current_frame()` - получение текущего кадра
- `set_frame_callback(callback)` - установка callback для обработки кадров
- `get_fps()` - получение текущего FPS
- `get_status()` - получение статуса видео потока

## 🔧 Настройка

### Изменение IP адреса дрона
```python
# Если дрон имеет другой IP адрес
tello = TelloTalentStatus(tello_ip="192.168.1.100")
tello_video = TelloVideoStream(tello_ip="192.168.1.100")
```

### Изменение портов
```python
# Кастомные порты
tello = TelloTalentStatus(
    tello_port=8889,
    status_port=8890,
    timeout=15
)

tello_video = TelloVideoStream(
    tello_port=8889,
    video_port=11111,
    timeout=15
)
```

## 🐛 Устранение неполадок

### Проблемы с подключением
1. **Дрон не подключается**
   - Убедитесь, что дрон включен
   - Проверьте подключение к WiFi сети дрона
   - Проверьте IP адрес дрона (обычно 192.168.10.1)

2. **Видео не отображается**
   - Убедитесь, что видео поток запущен
   - Проверьте, что OpenCV установлен корректно
   - Попробуйте перезапустить дрон

3. **Низкий FPS**
   - Проверьте качество WiFi соединения
   - Уменьшите нагрузку на процессор
   - Закройте другие приложения

### Логирование
Для включения подробного логирования:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📝 Лицензия

Этот проект распространяется под лицензией MIT. См. файл LICENSE для подробностей.

## 🤝 Вклад в проект

Мы приветствуем вклад в развитие проекта! Пожалуйста:
1. Создайте форк проекта
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📞 Поддержка

Если у вас возникли вопросы или проблемы:
1. Проверьте раздел "Устранение неполадок"
2. Создайте Issue в репозитории
3. Обратитесь к документации DJI Tello

## 🔄 Обновления

### Версия 1.0.0
- ✅ Базовый мониторинг статуса дрона
- ✅ Видео поток в реальном времени
- ✅ Запись видео и скриншоты
- ✅ Обработка кадров с фильтрами
- ✅ Callback функции
- ✅ Контекстные менеджеры
- ✅ Подробная документация

---

**Создано с ❤️ для сообщества DJI Tello**