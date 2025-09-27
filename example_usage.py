#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Примеры использования TelloTalentStatus
Различные способы получения статуса дрона DJI Tello Talent
"""

from tello_status import TelloTalentStatus
import time
import json


def example_basic_usage():
    """
    Базовый пример использования
    """
    print("🚁 Пример 1: Базовое использование")
    print("-" * 40)
    
    # Создание экземпляра
    tello = TelloTalentStatus()
    
    try:
        # Подключение
        if tello.connect():
            # Запуск мониторинга
            tello.start_status_monitoring()
            
            # Ожидание получения данных
            time.sleep(3)
            
            # Получение и вывод статуса
            tello.print_status()
            
            # Остановка мониторинга
            tello.stop_status_monitoring()
            
    finally:
        tello.disconnect()


def example_context_manager():
    """
    Пример использования с контекстным менеджером
    """
    print("\n🚁 Пример 2: Использование с контекстным менеджером")
    print("-" * 40)
    
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


def example_continuous_monitoring():
    """
    Пример непрерывного мониторинга
    """
    print("\n🚁 Пример 3: Непрерывный мониторинг")
    print("-" * 40)
    
    tello = TelloTalentStatus()
    
    try:
        if tello.connect():
            tello.start_status_monitoring()
            
            print("📡 Непрерывный мониторинг (10 секунд)...")
            
            for i in range(5):
                time.sleep(2)
                status = tello.get_status()
                
                if status:
                    battery = tello.get_battery()
                    print(f"⏱️ {i+1}/5 - Батарея: {battery}%")
                else:
                    print(f"⏱️ {i+1}/5 - Данные не получены")
            
    finally:
        tello.disconnect()


def example_json_export():
    """
    Пример экспорта статуса в JSON
    """
    print("\n🚁 Пример 4: Экспорт в JSON")
    print("-" * 40)
    
    tello = TelloTalentStatus()
    
    try:
        if tello.connect():
            tello.start_status_monitoring()
            time.sleep(3)
            
            # Получение статуса
            status = tello.get_status()
            
            if status:
                # Добавление метаданных
                status_with_meta = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "drone_model": "DJI Tello Talent",
                    "status": status
                }
                
                # Сохранение в файл
                with open("tello_status.json", "w", encoding="utf-8") as f:
                    json.dump(status_with_meta, f, indent=2, ensure_ascii=False)
                
                print("💾 Статус сохранен в tello_status.json")
                print("📄 Содержимое:")
                print(json.dumps(status_with_meta, indent=2, ensure_ascii=False))
            else:
                print("❌ Не удалось получить статус")
                
    finally:
        tello.disconnect()


def example_custom_ip():
    """
    Пример использования с кастомным IP адресом
    """
    print("\n🚁 Пример 5: Кастомный IP адрес")
    print("-" * 40)
    
    # Если дрон имеет другой IP адрес
    custom_ip = "192.168.1.100"  # Замените на нужный IP
    
    tello = TelloTalentStatus(tello_ip=custom_ip)
    
    try:
        if tello.connect():
            print(f"✅ Подключен к дрону по адресу {custom_ip}")
            tello.start_status_monitoring()
            time.sleep(3)
            tello.print_status()
        else:
            print(f"❌ Не удалось подключиться к {custom_ip}")
            
    finally:
        tello.disconnect()


def example_error_handling():
    """
    Пример обработки ошибок
    """
    print("\n🚁 Пример 6: Обработка ошибок")
    print("-" * 40)
    
    tello = TelloTalentStatus()
    
    try:
        # Попытка подключения с коротким таймаутом
        tello.timeout = 2
        tello.connect()
        
        if tello.is_connected:
            tello.start_status_monitoring()
            time.sleep(2)
            
            # Проверка получения данных
            status = tello.get_status()
            if status:
                print("✅ Статус получен успешно")
            else:
                print("⚠️ Статус не получен, но подключение активно")
        else:
            print("❌ Подключение не удалось")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        tello.disconnect()


def main():
    """
    Запуск всех примеров
    """
    print("🚁 Примеры использования TelloTalentStatus")
    print("=" * 60)
    
    examples = [
        example_basic_usage,
        example_context_manager,
        example_continuous_monitoring,
        example_json_export,
        example_custom_ip,
        example_error_handling
    ]
    
    for i, example in enumerate(examples, 1):
        try:
            example()
        except Exception as e:
            print(f"❌ Ошибка в примере {i}: {e}")
        
        print("\n" + "=" * 60)
        input("Нажмите Enter для продолжения...")


if __name__ == "__main__":
    main()
