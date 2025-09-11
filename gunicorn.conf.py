# Gunicorn config file
# See https://docs.gunicorn.org/en/stable/settings.html

# Server socket
bind = "0.0.0.0:10000"  # Render 会自动替换这个端口
workers = 4  # 根据 Render 实例的 CPU 核心数调整
worker_class = "gevent" # 使用 gevent 以获得更好的并发性能

# Logging
accesslog = "-" # 将访问日志输出到 stdout
errorlog = "-"  # 将错误日志输出到 stdout
loglevel = "info"

# Timeout
timeout = 120 # 增加超时时间以应对长时间的AI生成