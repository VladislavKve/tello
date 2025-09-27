#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сравнение производительности различных версий Tello Status Monitor
"""

import time
import asyncio
from tello_status import TelloTalentStatus
from tello_fast import TelloFastStatus
from tello_async import TelloAsyncStatus


def test_standard_version():
    """
    Тестирование стандартной версии
    """
    print("🐌 Тестирование СТАНДАРТНОЙ версии...")
    
    tello = TelloTalentStatus()
    
    try:
        if tello.connect():
            tello.start_status_monitoring()
            
            start_time = time.time()
            status_count = 0
            
            # Тестирование в течение 10 секунд
            while time.time() - start_time < 10:
                time.sleep(1)
                status = tello.get_status()
                if status:
                    status_count += 1
            
            elapsed_time = time.time() - start_time
            packets_per_second = status_count / elapsed_time
            
            print(f"   📊 Получено статусов: {status_count}")
            print(f"   ⏱️ Время: {elapsed_time:.1f} сек")
            print(f"   📡 Скорость: {packets_per_second:.1f} пак/с")
            
            tello.stop_status_monitoring()
            return packets_per_second
        else:
            print("   ❌ Не удалось подключиться")
            return 0
            
    finally:
        tello.disconnect()


def test_fast_version():
    """
    Тестирование быстрой версии
    """
    print("\n🚀 Тестирование БЫСТРОЙ версии...")
    
    tello = TelloFastStatus(timeout=0.05)
    
    try:
        if tello.connect():
            tello.start_status_monitoring()
            
            start_time = time.time()
            
            # Тестирование в течение 10 секунд
            while time.time() - start_time < 10:
                time.sleep(1)
                stats = tello.get_performance_stats()
                if stats['packets_per_second'] > 0:
                    break
            
            elapsed_time = time.time() - start_time
            final_stats = tello.get_performance_stats()
            
            print(f"   📊 Пакетов получено: {final_stats['total_packets']}")
            print(f"   ⏱️ Время: {elapsed_time:.1f} сек")
            print(f"   📡 Скорость: {final_stats['packets_per_second']:.1f} пак/с")
            print(f"   ⚡ Время парсинга: {final_stats['parse_time_avg']*1000:.2f} мс")
            
            tello.stop_status_monitoring()
            return final_stats['packets_per_second']
        else:
            print("   ❌ Не удалось подключиться")
            return 0
            
    finally:
        tello.disconnect()


async def test_async_version():
    """
    Тестирование асинхронной версии
    """
    print("\n⚡ Тестирование АСИНХРОННОЙ версии...")
    
    tello = TelloAsyncStatus()
    
    try:
        if await tello.connect():
            await tello.start_status_monitoring()
            
            # Запуск асинхронного получателя статуса
            status_task = asyncio.create_task(tello._async_status_receiver())
            
            start_time = time.time()
            
            # Тестирование в течение 10 секунд
            while time.time() - start_time < 10:
                await asyncio.sleep(1)
                stats = tello.get_performance_stats()
                if stats['packets_per_second'] > 0:
                    break
            
            elapsed_time = time.time() - start_time
            final_stats = tello.get_performance_stats()
            
            print(f"   📊 Пакетов получено: {final_stats['total_packets']}")
            print(f"   ⏱️ Время: {elapsed_time:.1f} сек")
            print(f"   📡 Скорость: {final_stats['packets_per_second']:.1f} пак/с")
            print(f"   ⚡ Время парсинга: {final_stats['parse_time_avg']*1000:.2f} мс")
            
            # Отмена задачи
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass
            
            await tello.stop_status_monitoring()
            return final_stats['packets_per_second']
        else:
            print("   ❌ Не удалось подключиться")
            return 0
            
    finally:
        await tello.disconnect()


def main():
    """
    Основная функция сравнения производительности
    """
    print("🏁 СРАВНЕНИЕ ПРОИЗВОДИТЕЛЬНОСТИ TELLO STATUS MONITOR")
    print("="*70)
    print("Тестирование в течение 10 секунд для каждой версии...")
    print("="*70)
    
    results = {}
    
    # Тестирование стандартной версии
    try:
        results['standard'] = test_standard_version()
    except Exception as e:
        print(f"❌ Ошибка в стандартной версии: {e}")
        results['standard'] = 0
    
    # Тестирование быстрой версии
    try:
        results['fast'] = test_fast_version()
    except Exception as e:
        print(f"❌ Ошибка в быстрой версии: {e}")
        results['fast'] = 0
    
    # Тестирование асинхронной версии
    try:
        results['async'] = asyncio.run(test_async_version())
    except Exception as e:
        print(f"❌ Ошибка в асинхронной версии: {e}")
        results['async'] = 0
    
    # Вывод результатов сравнения
    print("\n" + "="*70)
    print("📊 РЕЗУЛЬТАТЫ СРАВНЕНИЯ")
    print("="*70)
    
    if results['standard'] > 0:
        print(f"🐌 Стандартная версия: {results['standard']:.1f} пак/с")
    
    if results['fast'] > 0:
        print(f"🚀 Быстрая версия: {results['fast']:.1f} пак/с")
        if results['standard'] > 0:
            speedup = results['fast'] / results['standard']
            print(f"   📈 Ускорение: {speedup:.1f}x")
    
    if results['async'] > 0:
        print(f"⚡ Асинхронная версия: {results['async']:.1f} пак/с")
        if results['standard'] > 0:
            speedup = results['async'] / results['standard']
            print(f"   📈 Ускорение: {speedup:.1f}x")
    
    # Определение лучшей версии
    best_version = max(results, key=results.get)
    best_speed = results[best_version]
    
    print(f"\n🏆 ЛУЧШАЯ ВЕРСИЯ: {best_version.upper()}")
    print(f"   📡 Максимальная скорость: {best_speed:.1f} пак/с")
    
    # Рекомендации
    print(f"\n💡 РЕКОМЕНДАЦИИ:")
    if best_speed > 10:
        print("   ✅ Отличная производительность! Дрон работает стабильно.")
    elif best_speed > 5:
        print("   ⚠️ Хорошая производительность, но есть место для улучшения.")
    else:
        print("   ❌ Низкая производительность. Проверьте WiFi соединение.")
    
    print("="*70)


if __name__ == "__main__":
    main()
