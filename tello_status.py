#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DJI Tello Talent Status Monitor
Получение статуса дрона DJI Tello Talent через Python
"""

import socket
import threading
import time
import json
from typing import Dict, Optional, Any
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelloTalentStatus:
    """
    Класс для получения статуса дрона DJI Tello Talent
    """
    
    def __init__(self, tello_ip: str = "192.168.10.1", tello_port: int = 8889, 
                 status_port: int = 8890, timeout: int = 10):
        """
        Инициализация подключения к дрону
        
        Args:
            tello_ip: IP адрес дрона (по умолчанию 192.168.10.1)
            tello_port: Порт для команд (по умолчанию 8889)
            status_port: Порт для получения статуса (по умолчанию 8890)
            timeout: Таймаут подключения в секундах
        """
        self.tello_ip = tello_ip
        self.tello_port = tello_port
        self.status_port = status_port
        self.timeout = timeout
        
        # Сокеты
        self.command_socket = None
        self.status_socket = None
        
        # Статус дрона
        self.status_data = {}
        self.is_connected = False
        self.is_receiving_status = False
        
        # Поток для получения статуса
        self.status_thread = None
        self.stop_status_thread = False

    def connect(self) -> bool:
        """
        Подключение к дрону
        
        Returns:
            bool: True если подключение успешно
        """
        try:
            # Создание сокета для команд
            self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.command_socket.settimeout(self.timeout)
            
            # Создание сокета для получения статуса
            self.status_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.status_socket.bind(('', self.status_port))
            self.status_socket.settimeout(1.0)  # Короткий таймаут для неблокирующего чтения
            
            # Отправка команды для инициализации
            self.command_socket.sendto(b'command', (self.tello_ip, self.tello_port))
            response, _ = self.command_socket.recvfrom(1024)
            
            if response.decode('utf-8').strip() == 'ok':
                self.is_connected = True
                logger.info("✅ Успешно подключен к дрону")
                return True
            else:
                logger.error("❌ Ошибка подключения к дрону")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False

    def start_status_monitoring(self):
        """
        Запуск мониторинга статуса дрона
        """
        if not self.is_connected:
            logger.error("❌ Сначала подключитесь к дрону")
            return
            
        self.is_receiving_status = True
        self.stop_status_thread = False
        
        # Запуск потока для получения статуса
        self.status_thread = threading.Thread(target=self._status_receiver, daemon=True)
        self.status_thread.start()
        
        logger.info("📡 Запущен мониторинг статуса дрона")

    def stop_status_monitoring(self):
        """
        Остановка мониторинга статуса
        """
        self.stop_status_thread = True
        self.is_receiving_status = False
        
        if self.status_thread and self.status_thread.is_alive():
            self.status_thread.join(timeout=2)
            
        logger.info("⏹️ Мониторинг статуса остановлен")

    def _status_receiver(self):
        """
        Поток для получения статуса дрона
        """
        while not self.stop_status_thread:
            try:
                data, _ = self.status_socket.recvfrom(1024)
                status_string = data.decode('utf-8').strip()
                
                if status_string:
                    self._parse_status(status_string)
                    
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка получения статуса: {e}")
                time.sleep(0.1)

    def _parse_status(self, status_string: str):
        """
        Парсинг строки статуса дрона
        
        Args:
            status_string: Строка статуса от дрона
        """
        try:
            # Разделение строки на пары ключ-значение
            pairs = status_string.split(';')
            
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Попытка преобразования числовых значений
                    try:
                        if '.' in value:
                            self.status_data[key] = float(value)
                        else:
                            self.status_data[key] = int(value)
                    except ValueError:
                        self.status_data[key] = value
                        
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга статуса: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Получение текущего статуса дрона
        
        Returns:
            Dict: Словарь с данными статуса
        """
        return self.status_data.copy()

    def get_battery(self) -> Optional[int]:
        """
        Получение уровня заряда батареи
        
        Returns:
            int: Уровень заряда в процентах или None
        """
        return self.status_data.get('bat', None)

    def get_temperature(self) -> Optional[float]:
        """
        Получение температуры дрона
        
        Returns:
            float: Температура в градусах или None
        """
        return self.status_data.get('temph', None)

    def get_height(self) -> Optional[int]:
        """
        Получение высоты дрона
        
        Returns:
            int: Высота в сантиметрах или None
        """
        return self.status_data.get('h', None)

    def get_speed(self) -> Optional[float]:
        """
        Получение скорости дрона
        
        Returns:
            float: Скорость в см/с или None
        """
        return self.status_data.get('speed', None)

    def get_wifi_signal(self) -> Optional[int]:
        """
        Получение силы WiFi сигнала
        
        Returns:
            int: Сила сигнала или None
        """
        return self.status_data.get('wifi', None)

    def print_status(self):
        """
        Вывод статуса дрона в консоль
        """
        if not self.status_data:
            print("📊 Статус дрона: Нет данных")
            return
            
        print("\n" + "="*50)
        print("📊 СТАТУС ДРОНА DJI TELLO TALENT")
        print("="*50)
        
        # Основные параметры
        battery = self.get_battery()
        if battery is not None:
            battery_icon = "🔋" if battery > 20 else "⚠️"
            print(f"{battery_icon} Заряд батареи: {battery}%")
        
        temperature = self.get_temperature()
        if temperature is not None:
            temp_icon = "🌡️"
            print(f"{temp_icon} Температура: {temperature}°C")
        
        height = self.get_height()
        if height is not None:
            print(f"📏 Высота: {height} см")
        
        speed = self.get_speed()
        if speed is not None:
            print(f"🚀 Скорость: {speed} см/с")
        
        wifi = self.get_wifi_signal()
        if wifi is not None:
            wifi_icon = "📶" if wifi > -70 else "📵"
            print(f"{wifi_icon} WiFi сигнал: {wifi} dBm")
        
        # Все остальные параметры
        print("\n📋 Все параметры:")
        for key, value in self.status_data.items():
            print(f"   {key}: {value}")
        
        print("="*50)

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
        logger.info("🔌 Отключен от дрона")

    def __enter__(self):
        """Поддержка контекстного менеджера"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое отключение при выходе из контекста"""
        self.disconnect()


def main():
    """
    Пример использования класса TelloTalentStatus
    """
    print("🚁 Запуск мониторинга DJI Tello Talent")
    print("="*50)
    
    # Создание экземпляра класса
    tello = TelloTalentStatus()
    
    try:
        # Подключение к дрону
        if not tello.connect():
            print("❌ Не удалось подключиться к дрону")
            print("💡 Убедитесь, что:")
            print("   - Дрон включен")
            print("   - Подключены к WiFi сети дрона")
            print("   - IP адрес дрона правильный (192.168.10.1)")
            return
        
        # Запуск мониторинга статуса
        tello.start_status_monitoring()
        
        print("📡 Мониторинг статуса запущен. Нажмите Ctrl+C для остановки")
        
        # Основной цикл
        while True:
            time.sleep(2)
            tello.print_status()
            
    except KeyboardInterrupt:
        print("\n⏹️ Остановка мониторинга...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        tello.disconnect()
        print("✅ Программа завершена")


if __name__ == "__main__":
    main()
