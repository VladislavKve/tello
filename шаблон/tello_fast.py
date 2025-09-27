#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DJI Tello Talent Fast Status Monitor
Быстрая версия для получения статуса дрона с минимальными задержками
"""

import socket
import threading
import time
import json
from typing import Dict, Optional, Any, Callable
import logging
from collections import deque
import struct

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelloFastStatus:
    """
    Быстрая версия класса для получения статуса дрона DJI Tello Talent
    Оптимизирована для минимальных задержек и максимальной производительности
    """
    
    def __init__(self, tello_ip: str = "192.168.10.1", tello_port: int = 8889, 
                 status_port: int = 8890, timeout: float = 0.1, buffer_size: int = 100):
        """
        Инициализация быстрого подключения к дрону
        
        Args:
            tello_ip: IP адрес дрона
            tello_port: Порт для команд
            status_port: Порт для получения статуса
            timeout: Минимальный таймаут для сокетов (в секундах)
            buffer_size: Размер буфера для хранения последних статусов
        """
        self.tello_ip = tello_ip
        self.tello_port = tello_port
        self.status_port = status_port
        self.timeout = timeout
        self.buffer_size = buffer_size
        
        # Сокеты
        self.command_socket = None
        self.status_socket = None
        
        # Статус дрона с буферизацией
        self.status_buffer = deque(maxlen=buffer_size)
        self.latest_status = {}
        self.is_connected = False
        self.is_receiving_status = False
        
        # Поток для получения статуса
        self.status_thread = None
        self.stop_status_thread = False
        
        # Статистика производительности
        self.stats = {
            'packets_received': 0,
            'packets_per_second': 0.0,
            'last_update_time': time.time(),
            'parse_time_avg': 0.0
        }
        
        # Callback функции
        self.status_callbacks = []
        self.error_callbacks = []

    def add_status_callback(self, callback: Callable[[Dict], None]):
        """
        Добавление callback функции для обработки новых статусов
        
        Args:
            callback: Функция, которая будет вызываться при получении нового статуса
        """
        self.status_callbacks.append(callback)

    def add_error_callback(self, callback: Callable[[Exception], None]):
        """
        Добавление callback функции для обработки ошибок
        
        Args:
            callback: Функция, которая будет вызываться при ошибках
        """
        self.error_callbacks.append(callback)

    def connect(self) -> bool:
        """
        Быстрое подключение к дрону с минимальными таймаутами
        """
        try:
            # Создание сокета для команд с минимальным таймаутом
            self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.command_socket.settimeout(self.timeout)
            
            # Создание сокета для получения статуса с минимальным таймаутом
            self.status_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.status_socket.bind(('', self.status_port))
            self.status_socket.settimeout(0.01)  # Очень короткий таймаут для неблокирующего чтения
            
            # Отправка команды для инициализации
            self.command_socket.sendto(b'command', (self.tello_ip, self.tello_port))
            response, _ = self.command_socket.recvfrom(1024)
            
            if response.decode('utf-8').strip() == 'ok':
                self.is_connected = True
                logger.info("✅ Быстрое подключение к дрону установлено")
                return True
            else:
                logger.error("❌ Ошибка подключения к дрону")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            for callback in self.error_callbacks:
                callback(e)
            return False

    def start_status_monitoring(self):
        """
        Запуск быстрого мониторинга статуса дрона
        """
        if not self.is_connected:
            logger.error("❌ Сначала подключитесь к дрону")
            return
            
        self.is_receiving_status = True
        self.stop_status_thread = False
        
        # Сброс статистики
        self.stats = {
            'packets_received': 0,
            'packets_per_second': 0.0,
            'last_update_time': time.time(),
            'parse_time_avg': 0.0
        }
        
        # Запуск потока для получения статуса
        self.status_thread = threading.Thread(target=self._fast_status_receiver, daemon=True)
        self.status_thread.start()
        
        logger.info("🚀 Запущен быстрый мониторинг статуса дрона")

    def stop_status_monitoring(self):
        """
        Остановка мониторинга статуса
        """
        self.stop_status_thread = True
        self.is_receiving_status = False
        
        if self.status_thread and self.status_thread.is_alive():
            self.status_thread.join(timeout=1)
            
        logger.info("⏹️ Быстрый мониторинг статуса остановлен")

    def _fast_status_receiver(self):
        """
        Оптимизированный поток для быстрого получения статуса дрона
        """
        parse_times = deque(maxlen=100)  # Буфер для времени парсинга
        
        while not self.stop_status_thread:
            try:
                data, _ = self.status_socket.recvfrom(1024)
                status_string = data.decode('utf-8').strip()
                
                if status_string:
                    # Измерение времени парсинга
                    parse_start = time.time()
                    parsed_status = self._fast_parse_status(status_string)
                    parse_time = time.time() - parse_start
                    
                    parse_times.append(parse_time)
                    
                    if parsed_status:
                        # Обновление буфера и статистики
                        self.status_buffer.append(parsed_status)
                        self.latest_status = parsed_status
                        self.stats['packets_received'] += 1
                        
                        # Вызов callback функций
                        for callback in self.status_callbacks:
                            try:
                                callback(parsed_status)
                            except Exception as e:
                                logger.error(f"❌ Ошибка в callback: {e}")
                        
                        # Обновление статистики производительности
                        current_time = time.time()
                        time_diff = current_time - self.stats['last_update_time']
                        
                        if time_diff >= 1.0:  # Обновляем статистику каждую секунду
                            self.stats['packets_per_second'] = self.stats['packets_received'] / time_diff
                            self.stats['parse_time_avg'] = sum(parse_times) / len(parse_times) if parse_times else 0
                            self.stats['last_update_time'] = current_time
                            self.stats['packets_received'] = 0
                    
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка получения статуса: {e}")
                for callback in self.error_callbacks:
                    callback(e)
                time.sleep(0.001)  # Минимальная задержка при ошибке

    def _fast_parse_status(self, status_string: str) -> Optional[Dict[str, Any]]:
        """
        Оптимизированный парсинг строки статуса дрона
        
        Args:
            status_string: Строка статуса от дрона
            
        Returns:
            Dict: Словарь с данными статуса или None
        """
        try:
            # Быстрый парсинг без лишних операций
            result = {}
            pairs = status_string.split(';')
            
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Быстрое преобразование типов
                    if value.replace('.', '').replace('-', '').isdigit():
                        if '.' in value:
                            result[key] = float(value)
                        else:
                            result[key] = int(value)
                    else:
                        result[key] = value
            
            return result
                        
        except Exception as e:
            logger.error(f"❌ Ошибка быстрого парсинга статуса: {e}")
            return None

    def get_latest_status(self) -> Dict[str, Any]:
        """
        Получение последнего статуса дрона
        
        Returns:
            Dict: Словарь с последними данными статуса
        """
        return self.latest_status.copy()

    def get_status_buffer(self) -> list:
        """
        Получение буфера последних статусов
        
        Returns:
            list: Список последних статусов
        """
        return list(self.status_buffer)

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Получение статистики производительности
        
        Returns:
            Dict: Статистика производительности
        """
        return self.stats.copy()

    def get_battery(self) -> Optional[int]:
        """Получение уровня заряда батареи"""
        return self.latest_status.get('bat', None)

    def get_temperature(self) -> Optional[float]:
        """Получение температуры дрона"""
        return self.latest_status.get('temph', None)

    def get_height(self) -> Optional[int]:
        """Получение высоты дрона"""
        return self.latest_status.get('h', None)

    def get_speed(self) -> Optional[float]:
        """Получение скорости дрона"""
        return self.latest_status.get('speed', None)

    def get_wifi_signal(self) -> Optional[int]:
        """Получение силы WiFi сигнала"""
        return self.latest_status.get('wifi', None)

    def print_fast_status(self):
        """
        Быстрый вывод статуса дрона в консоль
        """
        if not self.latest_status:
            print("📊 Статус дрона: Нет данных")
            return
            
        # Основные параметры
        battery = self.get_battery()
        temperature = self.get_temperature()
        height = self.get_height()
        speed = self.get_speed()
        wifi = self.get_wifi_signal()
        
        # Статистика производительности
        stats = self.get_performance_stats()
        
        print(f"\n🚀 БЫСТРЫЙ СТАТУС | 📡 {stats['packets_per_second']:.1f} пак/с | ⚡ {stats['parse_time_avg']*1000:.2f}мс парсинг")
        print("-" * 80)
        
        if battery is not None:
            battery_icon = "🔋" if battery > 20 else "⚠️"
            print(f"{battery_icon} Батарея: {battery}%")
        
        if temperature is not None:
            temp_icon = "🌡️"
            print(f"{temp_icon} Температура: {temperature}°C")
        
        if height is not None:
            print(f"📏 Высота: {height} см")
        
        if speed is not None:
            print(f"🚀 Скорость: {speed} см/с")
        
        if wifi is not None:
            wifi_icon = "📶" if wifi > -70 else "📵"
            print(f"{wifi_icon} WiFi: {wifi} dBm")

    def print_detailed_status(self):
        """
        Подробный вывод статуса с буфером
        """
        if not self.latest_status:
            print("📊 Статус дрона: Нет данных")
            return
            
        stats = self.get_performance_stats()
        
        print("\n" + "="*80)
        print("🚀 ДЕТАЛЬНЫЙ БЫСТРЫЙ СТАТУС DJI TELLO TALENT")
        print("="*80)
        
        # Основные параметры
        self.print_fast_status()
        
        # Статистика производительности
        print(f"\n📊 ПРОИЗВОДИТЕЛЬНОСТЬ:")
        print(f"   📡 Пакетов в секунду: {stats['packets_per_second']:.1f}")
        print(f"   ⚡ Среднее время парсинга: {stats['parse_time_avg']*1000:.2f} мс")
        print(f"   📦 Размер буфера: {len(self.status_buffer)}/{self.buffer_size}")
        
        # Все параметры
        print(f"\n📋 ВСЕ ПАРАМЕТРЫ:")
        for key, value in self.latest_status.items():
            print(f"   {key}: {value}")
        
        print("="*80)

    def disconnect(self):
        """
        Отключение от дрона
        """
        self.stop_status_monitoring()
        
        if self.command_socket:
            self.command_socket.close()
            self.command_socket = None
            
        if self.status_socket:
            self.status_socket.close()
            self.status_socket = None
            
        self.is_connected = False
        logger.info("🔌 Быстрое отключение от дрона")

    def __enter__(self):
        """Поддержка контекстного менеджера"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое отключение при выходе из контекста"""
        self.disconnect()


def main():
    """
    Пример использования быстрого класса TelloFastStatus
    """
    print("🚁 Запуск БЫСТРОГО мониторинга DJI Tello Talent")
    print("="*60)
    
    # Callback функции
    def on_status_update(status):
        """Callback для обработки новых статусов"""
        battery = status.get('bat', 'N/A')
        height = status.get('h', 'N/A')
        print(f"📡 Новый статус: Батарея {battery}%, Высота {height}см")
    
    def on_error(error):
        """Callback для обработки ошибок"""
        print(f"❌ Ошибка: {error}")
    
    # Создание экземпляра быстрого класса
    tello = TelloFastStatus(timeout=0.05)  # Очень короткий таймаут
    
    # Добавление callback функций
    tello.add_status_callback(on_status_update)
    tello.add_error_callback(on_error)
    
    try:
        # Подключение к дрону
        if not tello.connect():
            print("❌ Не удалось подключиться к дрону")
            return
        
        # Запуск быстрого мониторинга статуса
        tello.start_status_monitoring()
        
        print("🚀 Быстрый мониторинг запущен. Нажмите Ctrl+C для остановки")
        
        # Основной цикл с быстрым обновлением
        while True:
            time.sleep(0.5)  # Обновление каждые 0.5 секунды
            tello.print_fast_status()
            
    except KeyboardInterrupt:
        print("\n⏹️ Остановка быстрого мониторинга...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        tello.disconnect()
        print("✅ Быстрая программа завершена")


if __name__ == "__main__":
    main()
