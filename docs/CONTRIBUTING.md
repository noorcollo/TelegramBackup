# 🤝 Contributing to TelegramBackup

Thank you for your interest in contributing! Here's how to get involved.

---

## 🐛 Reporting Bugs

1. Go to the [Issues](../../issues) page
2. Click **New Issue**
3. Use the title format: `[BUG] Short description`
4. Include:
   - Windows version (e.g. Windows 10 22H2)
   - Python version (`python --version`)
   - Steps to reproduce
   - What you expected vs what happened
   - Log output (from the 📋 Log tab)

---

## 💡 Suggesting Features

1. Open a [New Issue](../../issues/new)
2. Use the title format: `[FEATURE] Short description`
3. Describe what you want and why it would be useful

---

## 🔧 Submitting Code

### Setup for development

```bash
git clone https://github.com/YOUR_USERNAME/TelegramBackup.git
cd TelegramBackup
pip install -r requirements.txt
python telegram_backup_v3.py
```

### Workflow

1. Fork the repository
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Test thoroughly on Windows
5. Commit with a clear message:
   ```bash
   git commit -m "Add: description of what you added"
   git commit -m "Fix: description of what you fixed"
   ```
6. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
7. Open a **Pull Request** against the `main` branch

---

## 📐 Code Style

- Keep all logic in `telegram_backup_v3.py` (single-file architecture)
- Use descriptive variable names
- Add a comment for any non-obvious logic
- Test with both dark and light themes
- Test with and without `pystray`/`pillow` installed

---

## 🔒 Security

**Never commit:**
- Bot tokens
- Chat IDs
- Config files (`.tgbackup_*.json`)
- History files

The `.gitignore` covers all of these — double check before pushing.

---

## 📄 License

By contributing, you agree your contributions will be licensed under the MIT License.
