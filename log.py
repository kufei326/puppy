import logging
from logging.handlers import RotatingFileHandler

def writeLog(name, log_file):
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # 检查是否已经添加了处理器，如果没有才添加
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger