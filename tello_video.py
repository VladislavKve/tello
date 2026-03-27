#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DJI Tello Talent Video Stream
Получение и отображение видео с камеры дрона DJI Tello Talent
"""

import cv2
import socket
import threading
import time
import numpy as np
from typing import Optional, Tuple, Callable
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelloVideoStream:
    """
    Класс для получения и отображения видео с камеры дрона DJI Tello Talent
    """
    
    def __init__(self, tello_ip: str = "192.168.10.1", tello_port: int = 8889, 
                 video_port: int = 11111, timeout: int = 10):
        """
        Инициализация подключения к дрону для видео
        
        Args:
            tello_ip: IP адрес дрона (по умолчанию 192.168.10.1)
            tello_port: Порт для команд (по умолчанию 8889)
            video_port: Порт для видео потока (по умолчанию 11111)
            timeout: Таймаут подключения в секундах
        """
        self.tello_ip = tello_ip
        self.tello_port = tello_port
        self.video_port = video_port
        self.timeout = timeout
        
        # Сокеты
        self.command_socket = None
        self.video_socket = None
        
        # Состояние
        self.is_connected = False
        self.is_streaming = False
        self.is_recording = False
        
        # Потоки
        self.video_thread = None
        self.stop_video_thread = False
        
        # Видео данные
        self.current_frame = None
        self.frame_lock = threading.Lock()
        
        # Callback функции
        self.frame_callback = None
        self.error_callback = None
        
        # Статистика
        self.frame_count = 0
        self.fps = 0
        self.last_fps_time = time.time()

    def connect(self) -> bool:
        """
        Подключение к дрону
        
        Returns:
            bool: True если подключение успешно
        """
        try:
            self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.command_socket.settimeout(self.timeout)
            
            self.command_socket.sendto(b'command', (self.tello_ip, self.tello_port))
            try:
                response, _ = self.command_socket.recvfrom(1024)
                if response.decode('utf-8').strip() == 'ok':
                    self.is_connected = True
                    logger.info("✅ Успешно подключен к дрону для видео")
                    return True
            except socket.timeout:
                logger.warning("⏳ Команда 'command' не получила ответ, проверяю статус-стрим...")
                status_check = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                status_check.bind(('', 8890))
                status_check.settimeout(3.0)
                try:
                    data, _ = status_check.recvfrom(1024)
                    if data:
                        self.is_connected = True
                        logger.info("✅ Дрон уже в SDK-режиме (статус-стрим активен)")
                        return True
                except socket.timeout:
                    pass
                finally:
                    status_check.close()
            
            logger.error("❌ Ошибка подключения к дрону")
            return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False

    def start_video_stream(self):
        """
        Запуск видео потока
        """
        if not self.is_connected:
            logger.error("❌ Сначала подключитесь к дрону")
            return False
            
        try:
            self.command_socket.sendto(b'streamon', (self.tello_ip, self.tello_port))
            try:
                response, _ = self.command_socket.recvfrom(1024)
                resp_text = response.decode('utf-8').strip()
                if resp_text != 'ok':
                    logger.error(f"❌ Ошибка запуска видео потока: {resp_text}")
                    return False
            except socket.timeout:
                logger.warning("⏳ 'streamon' без ответа, пробую принять видео напрямую...")

            self.is_streaming = True
            self.stop_video_thread = False
            
            self.video_thread = threading.Thread(target=self._video_receiver, daemon=True)
            self.video_thread.start()
            
            logger.info("📹 Видео поток запущен")
            return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска видео потока: {e}")
            return False

    def stop_video_stream(self):
        """
        Остановка видео потока
        """
        try:
            if self.is_streaming:
                # Остановка видео потока
                self.command_socket.sendto(b'streamoff', (self.tello_ip, self.tello_port))
                response, _ = self.command_socket.recvfrom(1024)
                
                if response.decode('utf-8').strip() == 'ok':
                    logger.info("⏹️ Видео поток остановлен")
                
            self.stop_video_thread = True
            self.is_streaming = False
            
            if self.video_thread and self.video_thread.is_alive():
                self.video_thread.join(timeout=2)
                
        except Exception as e:
            logger.error(f"❌ Ошибка остановки видео потока: {e}")

    def _video_receiver(self):
        """
        Поток для получения видео данных (H264 через OpenCV/ffmpeg)
        """
        cap = cv2.VideoCapture(
            f'udp://@0.0.0.0:{self.video_port}?overrun_nonfatal=1&fflags=nobuffer',
            cv2.CAP_FFMPEG
        )
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while not self.stop_video_thread:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            with self.frame_lock:
                self.current_frame = frame.copy()

            self.frame_count += 1
            current_time = time.time()
            if current_time - self.last_fps_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_fps_time = current_time

            if self.frame_callback:
                try:
                    self.frame_callback(frame)
                except Exception as e:
                    logger.error(f"❌ Ошибка в callback функции: {e}")

        cap.release()

    def get_current_frame(self) -> Optional[np.ndarray]:
        """
        Получение текущего кадра
        
        Returns:
            np.ndarray: Текущий кадр или None
        """
        with self.frame_lock:
            return self.current_frame.copy() if self.current_frame is not None else None

    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """
        Установка callback функции для обработки кадров
        
        Args:
            callback: Функция для обработки кадров
        """
        self.frame_callback = callback

    def set_error_callback(self, callback: Callable[[str], None]):
        """
        Установка callback функции для обработки ошибок
        
        Args:
            callback: Функция для обработки ошибок
        """
        self.error_callback = callback

    def get_fps(self) -> int:
        """
        Получение текущего FPS
        
        Returns:
            int: Текущий FPS
        """
        return self.fps

    def get_status(self) -> dict:
        """
        Получение статуса видео потока
        
        Returns:
            dict: Словарь со статусом
        """
        return {
            'is_connected': self.is_connected,
            'is_streaming': self.is_streaming,
            'is_recording': self.is_recording,
            'fps': self.fps,
            'frame_count': self.frame_count
        }

    def disconnect(self):
        """
        Отключение от дрона
        """
        self.stop_video_stream()
        
        if self.command_socket:
            self.command_socket.close()
            self.command_socket = None
            
        self.is_connected = False
        logger.info("🔌 Отключен от дрона")

    def __enter__(self):
        """Поддержка контекстного менеджера"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое отключение при выходе из контекста"""
        self.disconnect()


def display_video_stream(tello_video: TelloVideoStream, window_name: str = "DJI Tello Video"):
    """
    Отображение видео потока в окне OpenCV
    
    Args:
        tello_video: Экземпляр TelloVideoStream
        window_name: Имя окна для отображения
    """
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    
    try:
        while True:
            frame = tello_video.get_current_frame()
            
            if frame is not None:
                # Добавление информации о FPS
                fps = tello_video.get_fps()
                cv2.putText(frame, f"FPS: {fps}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # Добавление информации о статусе
                status = tello_video.get_status()
                cv2.putText(frame, f"Streaming: {'ON' if status['is_streaming'] else 'OFF'}", 
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                cv2.imshow(window_name, frame)
            
            # Проверка нажатия клавиш
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 'q' или ESC
                break
            elif key == ord('s'):  # 's' для сохранения скриншота
                if frame is not None:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"tello_screenshot_{timestamp}.jpg"
                    cv2.imwrite(filename, frame)
                    print(f"📸 Скриншот сохранен: {filename}")
            elif key == ord('r'):  # 'r' для записи видео
                if not tello_video.is_recording:
                    start_recording(tello_video)
                else:
                    stop_recording(tello_video)
                    
    except KeyboardInterrupt:
        print("\n⏹️ Остановка отображения видео...")
    finally:
        cv2.destroyAllWindows()


def start_recording(tello_video: TelloVideoStream, filename: str = None):
    """
    Начало записи видео
    
    Args:
        tello_video: Экземпляр TelloVideoStream
        filename: Имя файла для записи
    """
    if filename is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"tello_video_{timestamp}.mp4"
    
    # Здесь можно добавить логику записи видео
    # Для этого потребуется VideoWriter из OpenCV
    tello_video.is_recording = True
    logger.info(f"🎥 Начата запись видео: {filename}")


def stop_recording(tello_video: TelloVideoStream):
    """
    Остановка записи видео
    
    Args:
        tello_video: Экземпляр TelloVideoStream
    """
    tello_video.is_recording = False
    logger.info("⏹️ Запись видео остановлена")


def main():
    """
    Основная функция для демонстрации работы с видео
    """
    print("🚁 Запуск видео потока DJI Tello Talent")
    print("="*50)
    print("Управление:")
    print("  q или ESC - выход")
    print("  s - сохранить скриншот")
    print("  r - начать/остановить запись")
    print("="*50)
    
    # Создание экземпляра класса
    tello_video = TelloVideoStream()
    
    try:
        # Подключение к дрону
        if not tello_video.connect():
            print("❌ Не удалось подключиться к дрону")
            print("💡 Убедитесь, что:")
            print("   - Дрон включен")
            print("   - Подключены к WiFi сети дрона")
            print("   - IP адрес дрона правильный (192.168.10.1)")
            return
        
        # Запуск видео потока
        if not tello_video.start_video_stream():
            print("❌ Не удалось запустить видео поток")
            return
        
        print("📹 Видео поток запущен. Ожидание кадров...")
        time.sleep(2)  # Ожидание получения первых кадров
        
        # Отображение видео
        display_video_stream(tello_video)
        
    except KeyboardInterrupt:
        print("\n⏹️ Остановка программы...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        tello_video.disconnect()
        print("✅ Программа завершена")


if __name__ == "__main__":
    main()
