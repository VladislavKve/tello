#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DJI Tello Talent Async Status Monitor
Асинхронная версия для максимальной производительности
"""

import asyncio
import socket
import time
import json
from typing import Dict, Optional, Any, Callable, List
import logging
from collections import deque
import struct

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelloAsyncStatus:
    """
    Асинхронная версия класса для получения статуса дрона DJI Tello Talent
    Максимальная производительность с использованием asyncio
    """
    
    def __init__(self, tello_ip: str = "192.168.10.1", tello_port: int = 8889, 
                 status_port: int = 8890, buffer_size: int = 1000):
        """
        Инициализация асинхронного подключения к дрону
        
        Args:
            tello_ip: IP адрес дрона
            tello_port: Порт для команд
            status_port: Порт для получения статуса
            buffer_size: Размер буфера для хранения последних статусов
        """
        self.tello_ip = tello_ip
        self.tello_port = tello_port
        self.status_port = status_port
        self.buffer_size = buffer_size
        
        # Сокеты
        self.command_socket = None
        self.status_socket = None
        
        # Статус дрона с буферизацией
        self.status_buffer = deque(maxlen=buffer_size)
        self.latest_status = {}
        self.is_connected = False
        self.is_receiving_status = False
        
        # Статистика производительности
        self.stats = {
            'packets_received': 0,
            'packets_per_second': 0.0,
            'last_update_time': time.time(),
            'parse_time_avg': 0.0,
            'total_packets': 0
        }
        
        # Callback функции
        self.status_callbacks: List[Callable[[Dict], None]] = []
        self.error_callbacks: List[Callable[[Exception], None]] = []
        
        # События для управления
        self.stop_event = asyncio.Event()

    def add_status_callback(self, callback: Callable[[Dict], None]):
        """Добавление callback функции для обработки новых статусов"""
        self.status_callbacks.append(callback)

    def add_error_callback(self, callback: Callable[[Exception], None]):
        """Добавление callback функции для обработки ошибок"""
        self.error_callbacks.append(callback)

    async def connect(self) -> bool:
        """
        Асинхронное подключение к дрону
        """
        try:
            # Создание сокетов
            self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.status_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Привязка сокета статуса
            self.status_socket.bind(('', self.status_port))
            self.status_socket.setblocking(False)
            
            # Отправка команды для инициализации
            self.command_socket.sendto(b'command', (self.tello_ip, self.tello_port))
            
            # Ожидание ответа
            self.command_socket.settimeout(1.0)
            response, _ = self.command_socket.recvfrom(1024)
            
            if response.decode('utf-8').strip() == 'ok':
                self.is_connected = True
                logger.info("✅ Асинхронное подключение к дрону установлено")
                return True
            else:
                logger.error("❌ Ошибка подключения к дрону")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            for callback in self.error_callbacks:
                try:
                    callback(e)
                except:
                    pass
            return False

    async def start_status_monitoring(self):
        """
        Запуск асинхронного мониторинга статуса дрона
        """
        if not self.is_connected:
            logger.error("❌ Сначала подключитесь к дрону")
            return
            
        self.is_receiving_status = True
        self.stop_event.clear()
        
        # Сброс статистики
        self.stats = {
            'packets_received': 0,
            'packets_per_second': 0.0,
            'last_update_time': time.time(),
            'parse_time_avg': 0.0,
            'total_packets': 0
        }
        
        logger.info("🚀 Запущен асинхронный мониторинг статуса дрона")

    async def stop_status_monitoring(self):
        """
        Остановка мониторинга статуса
        """
        self.stop_event.set()
        self.is_receiving_status = False
        logger.info("⏹️ Асинхронный мониторинг статуса остановлен")

    async def _async_status_receiver(self):
        """
        Асинхронный получатель статуса дрона
        """
        parse_times = deque(maxlen=100)
        
        while not self.stop_event.is_set():
            try:
                # Асинхронное чтение данных
                loop = asyncio.get_event_loop()
                data, _ = await loop.sock_recv(self.status_socket, 1024)
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
                        self.stats['total_packets'] += 1
                        
                        # Асинхронный вызов callback функций
                        for callback in self.status_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(parsed_status)
                                else:
                                    callback(parsed_status)
                            except Exception as e:
                                logger.error(f"❌ Ошибка в callback: {e}")
                        
                        # Обновление статистики производительности
                        current_time = time.time()
                        time_diff = current_time - self.stats['last_update_time']
                        
                        if time_diff >= 1.0:
                            self.stats['packets_per_second'] = self.stats['packets_received'] / time_diff
                            self.stats['parse_time_avg'] = sum(parse_times) / len(parse_times) if parse_times else 0
                            self.stats['last_update_time'] = current_time
                            self.stats['packets_received'] = 0
                
                # Небольшая задержка для предотвращения перегрузки CPU
                await asyncio.sleep(0.001)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка получения статуса: {e}")
                for callback in self.error_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(e)
                        else:
                            callback(e)
                    except:
                        pass
                await asyncio.sleep(0.01)

    def _fast_parse_status(self, status_string: str) -> Optional[Dict[str, Any]]:
        """
        Быстрый парсинг строки статуса дрона
        """
        try:
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
            logger.error(f"❌ Ошибка парсинга статуса: {e}")
            return None

    def get_latest_status(self) -> Dict[str, Any]:
        """Получение последнего статуса дрона"""
        return self.latest_status.copy()

    def get_status_buffer(self) -> list:
        """Получение буфера последних статусов"""
        return list(self.status_buffer)

    def get_performance_stats(self) -> Dict[str, Any]:
        """Получение статистики производительности"""
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

    def print_async_status(self):
        """
        Вывод асинхронного статуса дрона в консоль
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
        
        print(f"\n⚡ АСИНХРОННЫЙ СТАТУС | 📡 {stats['packets_per_second']:.1f} пак/с | 📦 {stats['total_packets']} всего")
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

    async def disconnect(self):
        """
        Асинхронное отключение от дрона
        """
        await self.stop_status_monitoring()
        
        if self.command_socket:
            self.command_socket.close()
            self.command_socket = None
            
        if self.status_socket:
            self.status_socket.close()
            self.status_socket = None
            
        self.is_connected = False
        logger.info("🔌 Асинхронное отключение от дрона")

    async def __aenter__(self):
        """Поддержка асинхронного контекстного менеджера"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое отключение при выходе из асинхронного контекста"""
        await self.disconnect()


async def main():
    """
    Пример использования асинхронного класса TelloAsyncStatus
    """
    print("🚁 Запуск АСИНХРОННОГО мониторинга DJI Tello Talent")
    print("="*60)
    
    # Асинхронные callback функции
    async def on_status_update(status):
        """Асинхронный callback для обработки новых статусов"""
        battery = status.get('bat', 'N/A')
        height = status.get('h', 'N/A')
        print(f"📡 Новый статус: Батарея {battery}%, Высота {height}см")
    
    def on_error(error):
        """Callback для обработки ошибок"""
        print(f"❌ Ошибка: {error}")
    
    # Создание экземпляра асинхронного класса
    tello = TelloAsyncStatus()
    
    # Добавление callback функций
    tello.add_status_callback(on_status_update)
    tello.add_error_callback(on_error)
    
    try:
        # Подключение к дрону
        if not await tello.connect():
            print("❌ Не удалось подключиться к дрону")
            return
        
        # Запуск асинхронного мониторинга статуса
        await tello.start_status_monitoring()
        
        # Запуск асинхронного получателя статуса
        status_task = asyncio.create_task(tello._async_status_receiver())
        
        print("⚡ Асинхронный мониторинг запущен. Нажмите Ctrl+C для остановки")
        
        # Основной цикл с быстрым обновлением
        try:
            while True:
                await asyncio.sleep(0.2)  # Обновление каждые 0.2 секунды
                tello.print_async_status()
        except KeyboardInterrupt:
            print("\n⏹️ Остановка асинхронного мониторинга...")
        
        # Отмена задачи получения статуса
        status_task.cancel()
        try:
            await status_task
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await tello.disconnect()
        print("✅ Асинхронная программа завершена")


if __name__ == "__main__":
    asyncio.run(main())
