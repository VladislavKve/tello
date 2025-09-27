#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Примеры использования TelloVideoStream
Различные способы работы с видео потоком дрона DJI Tello Talent
"""

from tello_video import TelloVideoStream, display_video_stream, start_recording, stop_recording
import cv2
import time
import numpy as np
import threading


def example_basic_video():
    """
    Базовый пример отображения видео
    """
    print("🚁 Пример 1: Базовое отображение видео")
    print("-" * 40)
    
    tello_video = TelloVideoStream()
    
    try:
        if tello_video.connect():
            if tello_video.start_video_stream():
                print("📹 Видео поток запущен")
                time.sleep(2)
                
                # Отображение видео в течение 10 секунд
                start_time = time.time()
                while time.time() - start_time < 10:
                    frame = tello_video.get_current_frame()
                    if frame is not None:
                        cv2.imshow("DJI Tello Video", frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                    time.sleep(0.03)  # ~30 FPS
                
                cv2.destroyAllWindows()
            else:
                print("❌ Не удалось запустить видео поток")
        else:
            print("❌ Не удалось подключиться к дрону")
            
    finally:
        tello_video.disconnect()


def example_video_with_processing():
    """
    Пример обработки видео с применением фильтров
    """
    print("\n🚁 Пример 2: Обработка видео с фильтрами")
    print("-" * 40)
    
    def process_frame(frame):
        """Обработка кадра с применением фильтров"""
        # Конвертация в оттенки серого
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Применение размытия
        blurred = cv2.GaussianBlur(gray, (15, 15), 0)
        
        # Обнаружение краев
        edges = cv2.Canny(blurred, 50, 150)
        
        # Объединение оригинального кадра с краями
        edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        processed = cv2.addWeighted(frame, 0.7, edges_colored, 0.3, 0)
        
        return processed
    
    tello_video = TelloVideoStream()
    
    try:
        if tello_video.connect():
            if tello_video.start_video_stream():
                print("📹 Видео поток с обработкой запущен")
                
                start_time = time.time()
                while time.time() - start_time < 15:
                    frame = tello_video.get_current_frame()
                    if frame is not None:
                        # Обработка кадра
                        processed_frame = process_frame(frame)
                        
                        # Добавление информации
                        fps = tello_video.get_fps()
                        cv2.putText(processed_frame, f"FPS: {fps}", (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.putText(processed_frame, "Edge Detection", (10, 70), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                        
                        cv2.imshow("DJI Tello - Processed Video", processed_frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                    time.sleep(0.03)
                
                cv2.destroyAllWindows()
            else:
                print("❌ Не удалось запустить видео поток")
        else:
            print("❌ Не удалось подключиться к дрону")
            
    finally:
        tello_video.disconnect()


def example_video_recording():
    """
    Пример записи видео
    """
    print("\n🚁 Пример 3: Запись видео")
    print("-" * 40)
    
    tello_video = TelloVideoStream()
    
    try:
        if tello_video.connect():
            if tello_video.start_video_stream():
                print("📹 Видео поток запущен")
                time.sleep(2)
                
                # Начало записи
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"tello_recording_{timestamp}.mp4"
                
                # Настройка VideoWriter
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = None
                
                print(f"🎥 Начата запись: {filename}")
                recording = False
                
                start_time = time.time()
                while time.time() - start_time < 20:
                    frame = tello_video.get_current_frame()
                    if frame is not None:
                        # Инициализация VideoWriter при первом кадре
                        if out is None:
                            height, width = frame.shape[:2]
                            out = cv2.VideoWriter(filename, fourcc, 30.0, (width, height))
                        
                        # Запись кадра
                        if recording:
                            out.write(frame)
                        
                        # Добавление индикатора записи
                        if recording:
                            cv2.putText(frame, "REC", (10, 30), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                            cv2.circle(frame, (50, 50), 10, (0, 0, 255), -1)
                        
                        cv2.imshow("DJI Tello - Recording", frame)
                        
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q'):
                            break
                        elif key == ord('r'):
                            recording = not recording
                            print(f"🎥 Запись: {'ВКЛ' if recording else 'ВЫКЛ'}")
                    
                    time.sleep(0.03)
                
                # Завершение записи
                if out is not None:
                    out.release()
                    print(f"💾 Видео сохранено: {filename}")
                
                cv2.destroyAllWindows()
            else:
                print("❌ Не удалось запустить видео поток")
        else:
            print("❌ Не удалось подключиться к дрону")
            
    finally:
        tello_video.disconnect()


def example_callback_processing():
    """
    Пример использования callback функций
    """
    print("\n🚁 Пример 4: Обработка через callback")
    print("-" * 40)
    
    frame_count = 0
    last_save_time = time.time()
    
    def frame_callback(frame):
        """Callback функция для обработки каждого кадра"""
        nonlocal frame_count, last_save_time
        frame_count += 1
        
        # Сохранение каждого 30-го кадра
        if frame_count % 30 == 0:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"tello_frame_{frame_count}_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            print(f"📸 Сохранен кадр: {filename}")
        
        # Сохранение кадра каждые 5 секунд
        current_time = time.time()
        if current_time - last_save_time >= 5:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"tello_interval_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            print(f"📸 Интервальный кадр: {filename}")
            last_save_time = current_time
    
    def error_callback(error_msg):
        """Callback функция для обработки ошибок"""
        print(f"❌ Ошибка: {error_msg}")
    
    tello_video = TelloVideoStream()
    tello_video.set_frame_callback(frame_callback)
    tello_video.set_error_callback(error_callback)
    
    try:
        if tello_video.connect():
            if tello_video.start_video_stream():
                print("📹 Видео поток с callback запущен")
                print("💡 Кадры будут автоматически сохраняться")
                
                start_time = time.time()
                while time.time() - start_time < 15:
                    frame = tello_video.get_current_frame()
                    if frame is not None:
                        # Добавление счетчика кадров
                        cv2.putText(frame, f"Frames: {frame_count}", (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        
                        cv2.imshow("DJI Tello - Callback Processing", frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                    time.sleep(0.03)
                
                cv2.destroyAllWindows()
            else:
                print("❌ Не удалось запустить видео поток")
        else:
            print("❌ Не удалось подключиться к дрону")
            
    finally:
        tello_video.disconnect()


def example_multi_window():
    """
    Пример отображения видео в нескольких окнах с разной обработкой
    """
    print("\n🚁 Пример 5: Множественные окна")
    print("-" * 40)
    
    tello_video = TelloVideoStream()
    
    try:
        if tello_video.connect():
            if tello_video.start_video_stream():
                print("📹 Видео поток в множественных окнах запущен")
                
                start_time = time.time()
                while time.time() - start_time < 20:
                    frame = tello_video.get_current_frame()
                    if frame is not None:
                        # Оригинальное видео
                        cv2.imshow("Original", frame)
                        
                        # Оттенки серого
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        gray_colored = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                        cv2.imshow("Grayscale", gray_colored)
                        
                        # Размытое изображение
                        blurred = cv2.GaussianBlur(frame, (21, 21), 0)
                        cv2.imshow("Blurred", blurred)
                        
                        # Обнаружение краев
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        edges = cv2.Canny(gray, 50, 150)
                        edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
                        cv2.imshow("Edges", edges_colored)
                        
                        # Проверка нажатия клавиш
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q'):
                            break
                    
                    time.sleep(0.03)
                
                cv2.destroyAllWindows()
            else:
                print("❌ Не удалось запустить видео поток")
        else:
            print("❌ Не удалось подключиться к дрону")
            
    finally:
        tello_video.disconnect()


def example_context_manager():
    """
    Пример использования с контекстным менеджером
    """
    print("\n🚁 Пример 6: Контекстный менеджер")
    print("-" * 40)
    
    with TelloVideoStream() as tello_video:
        if tello_video.connect():
            if tello_video.start_video_stream():
                print("📹 Видео поток через контекстный менеджер")
                
                start_time = time.time()
                while time.time() - start_time < 10:
                    frame = tello_video.get_current_frame()
                    if frame is not None:
                        # Добавление информации о статусе
                        status = tello_video.get_status()
                        cv2.putText(frame, f"Connected: {status['is_connected']}", 
                                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(frame, f"Streaming: {status['is_streaming']}", 
                                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(frame, f"FPS: {status['fps']}", 
                                   (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        cv2.imshow("DJI Tello - Context Manager", frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                    time.sleep(0.03)
                
                cv2.destroyAllWindows()
            else:
                print("❌ Не удалось запустить видео поток")
        else:
            print("❌ Не удалось подключиться к дрону")


def main():
    """
    Запуск всех примеров
    """
    print("🚁 Примеры использования TelloVideoStream")
    print("=" * 60)
    
    examples = [
        ("Базовое отображение видео", example_basic_video),
        ("Обработка видео с фильтрами", example_video_with_processing),
        ("Запись видео", example_video_recording),
        ("Обработка через callback", example_callback_processing),
        ("Множественные окна", example_multi_window),
        ("Контекстный менеджер", example_context_manager)
    ]
    
    for i, (name, example_func) in enumerate(examples, 1):
        print(f"\n{'='*60}")
        print(f"Пример {i}: {name}")
        print("="*60)
        
        try:
            example_func()
        except Exception as e:
            print(f"❌ Ошибка в примере {i}: {e}")
        
        if i < len(examples):
            input("\nНажмите Enter для продолжения к следующему примеру...")


if __name__ == "__main__":
    main()
