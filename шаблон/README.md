# 🚁 DJI Tello Talent Status Monitor

Python библиотека для получения статуса дрона DJI Tello Talent (RoboMaster TT).

## 📋 Описание

Этот проект предоставляет простой и удобный способ получения статуса дрона DJI Tello Talent через Python. Библиотека поддерживает:

- ✅ Подключение к дрону по WiFi
- 📡 Получение статуса в реальном времени
- 🔋 Мониторинг заряда батареи
- 🌡️ Отслеживание температуры
- 📏 Контроль высоты и скорости
- 📶 Мониторинг WiFi сигнала
- 🛡️ Обработка ошибок и таймаутов

## 🚀 Быстрый старт

### 1. Подготовка дрона

1. Включите дрон DJI Tello Talent
2. Подключитесь к WiFi сети дрона (обычно `TELLO-XXXXXX`)
3. Убедитесь, что IP адрес дрона `192.168.10.1`

### 2. Установка

```bash
# Клонирование репозитория
git clone <repository-url>
cd tello-talent-status

# Установка зависимостей (опционально)
pip install -r requirements.txt
```

### 3. Базовое использование

```python
from tello_status import TelloTalentStatus

# Создание экземпляра
tello = TelloTalentStatus()

# Подключение к дрону
if tello.connect():
    # Запуск мониторинга статуса
    tello.start_status_monitoring()
    
    # Ожидание получения данных
    time.sleep(3)
    
    # Вывод статуса
    tello.print_status()
    
    # Остановка мониторинга
    tello.stop_status_monitoring()

# Отключение
tello.disconnect()
```

### 4. Запуск примера

```bash
python tello_status.py
```

## 📚 Примеры использования

### Контекстный менеджер

```python
with TelloTalentStatus() as tello:
    if tello.connect():
        tello.start_status_monitoring()
        time.sleep(3)
        
        # Получение конкретных параметров
        battery = tello.get_battery()
        temperature = tello.get_temperature()
        height = tello.get_height()
        
        print(f"Батарея: {battery}%")
        print(f"Температура: {temperature}°C")
        print(f"Высота: {height} см")
```

### Непрерывный мониторинг

```python
tello = TelloTalentStatus()

if tello.connect():
    tello.start_status_monitoring()
    
    for i in range(10):
        time.sleep(2)
        battery = tello.get_battery()
        print(f"Батарея: {battery}%")
```

### Экспорт в JSON

```python
import json

tello = TelloTalentStatus()

if tello.connect():
    tello.start_status_monitoring()
    time.sleep(3)
    
    status = tello.get_status()
    
    with open("status.json", "w") as f:
        json.dump(status, f, indent=2)
```

## 🔧 API Reference

### TelloTalentStatus

#### Конструктор

```python
TelloTalentStatus(tello_ip="192.168.10.1", tello_port=8889, status_port=8890, timeout=10)
```

**Параметры:**
- `tello_ip` (str): IP адрес дрона
- `tello_port` (int): Порт для команд
- `status_port` (int): Порт для получения статуса
- `timeout` (int): Таймаут подключения в секундах

#### Методы

##### `connect() -> bool`
Подключение к дрону.

**Возвращает:** `True` если подключение успешно

##### `start_status_monitoring()`
Запуск мониторинга статуса дрона.

##### `stop_status_monitoring()`
Остановка мониторинга статуса.

##### `get_status() -> Dict[str, Any]`
Получение текущего статуса дрона.

**Возвращает:** Словарь с данными статуса

##### `get_battery() -> Optional[int]`
Получение уровня заряда батареи.

**Возвращает:** Уровень заряда в процентах или `None`

##### `get_temperature() -> Optional[float]`
Получение температуры дрона.

**Возвращает:** Температура в градусах или `None`

##### `get_height() -> Optional[int]`
Получение высоты дрона.

**Возвращает:** Высота в сантиметрах или `None`

##### `get_speed() -> Optional[float]`
Получение скорости дрона.

**Возвращает:** Скорость в см/с или `None`

##### `get_wifi_signal() -> Optional[int]`
Получение силы WiFi сигнала.

**Возвращает:** Сила сигнала или `None`

##### `print_status()`
Вывод статуса дрона в консоль.

##### `disconnect()`
Отключение от дрона.

## 📊 Параметры статуса

Дрон отправляет следующие параметры статуса:

| Параметр | Описание | Единицы |
|----------|----------|---------|
| `bat` | Заряд батареи | % |
| `temph` | Температура | °C |
| `h` | Высота | см |
| `speed` | Скорость | см/с |
| `wifi` | WiFi сигнал | dBm |
| `pitch` | Наклон вперед/назад | градусы |
| `roll` | Наклон влево/вправо | градусы |
| `yaw` | Поворот | градусы |
| `agx` | Ускорение по X | м/с² |
| `agy` | Ускорение по Y | м/с² |
| `agz` | Ускорение по Z | м/с² |

## 🛠️ Настройка

### Изменение IP адреса

Если дрон имеет другой IP адрес:

```python
tello = TelloTalentStatus(tello_ip="192.168.1.100")
```

### Изменение портов

```python
tello = TelloTalentStatus(tello_port=8889, status_port=8890)
```

### Изменение таймаута

```python
tello = TelloTalentStatus(timeout=5)
```

## 🐛 Устранение неполадок

### Проблема: Не удается подключиться к дрону

**Решения:**
1. Убедитесь, что дрон включен
2. Проверьте подключение к WiFi сети дрона
3. Проверьте IP адрес дрона (обычно `192.168.10.1`)
4. Убедитесь, что порты 8889 и 8890 не заблокированы файрволом

### Проблема: Статус не получается

**Решения:**
1. Убедитесь, что мониторинг запущен (`start_status_monitoring()`)
2. Подождите несколько секунд для получения первых данных
3. Проверьте, что дрон находится в режиме полета или готовности

### Проблема: Медленное получение данных

**Решения:**
1. Уменьшите таймаут сокета
2. Проверьте качество WiFi соединения
3. Убедитесь, что нет других приложений, использующих порты дрона

## 📝 Логирование

Библиотека использует стандартный модуль `logging` Python:

```python
import logging

# Включение отладочных сообщений
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Добавьте тесты
5. Создайте Pull Request

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. См. файл `LICENSE` для подробностей.

## 🙏 Благодарности

- DJI за создание отличного образовательного дрона
- Сообществу разработчиков за вдохновение и поддержку

## 📞 Поддержка

Если у вас есть вопросы или проблемы:

1. Проверьте раздел "Устранение неполадок"
2. Создайте Issue в репозитории
3. Обратитесь к документации DJI Tello Talent

---

**Примечание:** Этот проект не является официальным продуктом DJI и создан сообществом для образовательных целей.
