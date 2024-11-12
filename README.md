<div align="center">
 
  <h2 align="center">RecaptchaV2 - Solver</h2>
  <p align="center">
A Python-based solution for solving Google's reCAPTCHA v2 challenges efficiently (8-12 seconds solve time). The script supports both synchronous and asynchronous operations, with API endpoints for easy integration. Uses audio challenge method with speech recognition for reliable solving.
    <br />
    <br />
    <a href="https://discord.cyberious.xyz">💬 Discord</a>
    ·
    <a href="https://github.com/sexfrance/RecaptchaV2-Solver#-changelog">📜 ChangeLog</a>
    ·
    <a href="https://github.com/sexfrance/RecaptchaV2-Solver/issues">⚠️ Report Bug</a>
    ·
    <a href="https://github.com/sexfrance/RecaptchaV2-Solver/issues">💡 Request Feature</a>
  </p>
</div>

### ⚙️ Installation

- Requires: `Python 3.8+`
- Make a python virtual environment: `python3 -m venv venv`
- Source the environment: `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (macOS, Linux)
- Install the requirements: `pip install -r requirements.txt`
- Install chrominium: `patchright install chromium` / `python -m patchright install chromium`

---

### 🔥 Features

- **Multiple Operation Modes**: Supports synchronous, asynchronous, and API-based solving
- **Audio Challenge Solving**: Uses speech recognition to solve audio challenges automatically
- **Proxy Support**: Built-in proxy support for avoiding rate limits
- **Concurrent Solving**: Batch processing capability for multiple CAPTCHAs
- **Debug Logging**: Comprehensive debug logs for troubleshooting
- **Rate Limit Detection**: Automatically detects and handles rate limiting
- **Enterprise Support**: Handles both standard and enterprise reCAPTCHA
- **Token Retrieval**: Multiple methods for reliable token extraction
- **Error Handling**: Robust error handling with detailed feedback

---

### 📝 Usage

#### API Usage

```python
curl -X POST http://localhost:8080/solve \
 -H "Content-Type: application/json" \
 -d '{
"url": "https://example.com",
"site_key": "your_site_key",
"proxy": {
"server": "proxy_address",
"username": "proxy_user",
"password": "proxy_pass"
}
}'
```

#### Async Usage

```python
async def main():
token = await AsyncReCaptchaSolver.solve_recaptcha(
url="https://example.com",
site_key="your_site_key",
proxy={
"server": "proxy_address",
"username": "proxy_user",
"password": "proxy_pass"
}
)
print(token)

asyncio.run(main())
```

#### Sync Usage

```python
token = ReCaptchaSolver.solve_recaptcha(
url="https://example.com",
site_key="your_site_key",
proxy={
"server": "proxy_address",
"username": "proxy_user",
"password": "proxy_pass"
}
)
print(token)
```

---

### 📹 Preview

![Preview](https://i.imgur.com/fHZwjNl.gif)

---

### ❗ Disclaimers

- I am not responsible for anything that may happen, such as API Blocking, IP ban, etc.
- This was a quick project that was made for fun and personal use if you want to see further updates, star the repo & create an "issue" [here](https://github.com/sexfrance/RecaptchaV2-Solver/issues/)

---

### 📜 ChangeLog

```diff
v0.0.1 ⋮ 11/12/2024
! Initial release
```

---

<p align="center">
  <img src="https://img.shields.io/github/license/sexfrance/RecaptchaV2-Solver.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/stars/sexfrance/RecaptchaV2-Solver.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/languages/top/sexfrance/RecaptchaV2-Solver.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=python"/>
</p>
