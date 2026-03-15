"""
TelegramBackup — setup.py
Allows installation via: pip install .
"""

from setuptools import setup

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="telegrambackup",
    version="3.0.0",
    author="3ala",
    description="Auto-backup any folder on your PC directly to a Telegram group or channel",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/YOUR_USERNAME/TelegramBackup",
    py_modules=["telegram_backup_v3"],
    python_requires=">=3.9",
    install_requires=[
        "python-telegram-bot>=21.0",
        "watchdog>=4.0.0",
        "pystray>=0.19.0",
        "Pillow>=10.0.0",
    ],
    entry_points={
        "console_scripts": [
            "telegrambackup=telegram_backup_v3:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Utilities",
        "Topic :: Communications :: File Sharing",
        "Intended Audience :: End Users/Desktop",
        "Environment :: Win32 (MS Windows)",
    ],
    keywords="telegram backup folder upload automation windows",
    project_urls={
        "Bug Reports": "https://github.com/YOUR_USERNAME/TelegramBackup/issues",
        "Source": "https://github.com/YOUR_USERNAME/TelegramBackup",
        "Documentation": "https://github.com/YOUR_USERNAME/TelegramBackup/blob/main/docs/SETUP.md",
    },
)
