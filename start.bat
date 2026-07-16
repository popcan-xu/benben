@echo off
echo 正在启动 Django 开发服务器...
echo 访问地址：http://127.0.0.1:8000
echo 局域网访问：本机IP:8000
echo.
:: 跳转到 Django 项目目录（如果bat文件和manage.py在同一文件夹，这行可以保留）
cd /d "%~dp0"
:: 启动 Django 服务（0.0.0.0 允许局域网访问）
python manage.py runserver 0.0.0.0:8000
:: 程序崩溃时保持窗口打开，方便看错误
pause