import os
import logging

def configure_logging():
    # We get the level of logistics from the environment variable or use INFO by default
    log_level_name = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Преобразуем строковое представление уровня логирования в константу logging
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)
    
    # Настраиваем логирование один раз
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Возвращаем настроенный уровень логирования для информации
    return log_level

# Инициализируем логирование при импорте модуля
log_level = configure_logging()