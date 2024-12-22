from dataclasses import dataclass, field
from typing import Optional, Dict, List, Union, Tuple
import asyncio
import aiohttp
import io
import time
import speech_recognition as sr
from pydub import AudioSegment
from patchright.async_api import async_playwright, Page, TimeoutError
from quart import Quart, request, jsonify
from logmagix import Logger, Loader
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
import requests

app = Quart(__name__)
log = Logger()

@dataclass
class APIConfig:
    """Configuration for API settings"""
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    DEBUG: bool = False
    MAX_CONCURRENT: int = 10
    TIMEOUT: int = 120  # 2 minutes timeout

@dataclass
class BrowserConfig:
    """Configuration for browser launch arguments"""
    CHROME_ARGS: List[str] = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-web-security",
        "--disable-images",
    ])
    CONTEXT_OPTIONS: Dict = field(default_factory=lambda: {
        "locale": "en-US",
        "java_script_enabled": True,
        "bypass_csp": True,
        "viewport": {"width": 1280, "height": 800},
        "device_scale_factor": 1,
        "is_mobile": False,
        "offline": False,
        "ignore_https_errors": True,
        "service_workers": "block"
    })

    @classmethod
    def get_chrome_args(cls) -> List[str]:
        return cls.CHROME_ARGS

    @classmethod
    def get_context_options(cls) -> Dict:
        return cls.CONTEXT_OPTIONS.copy()

class AudioProcessor:
    """Handles audio processing and speech recognition"""
    def __init__(self, debug: bool = False):
        self.recognizer = sr.Recognizer()
        self.debug = debug
        self.log = Logger()
        self._session = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def process_audio(self, audio_url: str) -> str:
        """Process audio from URL to text"""
        audio_content = await self._download_audio(audio_url)
        audio_bytes = await self._convert_to_wav(audio_content)
        return await self._convert_audio_to_text(audio_bytes)

    async def _download_audio(self, audio_url: str) -> bytes:
        """Download audio file"""
        if not self._session:
            self._session = aiohttp.ClientSession()
        async with self._session.get(audio_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download audio. Status: {response.status}")
            return await response.read()

    async def _convert_to_wav(self, audio_content: bytes) -> io.BytesIO:
        """Convert MP3 to WAV"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._convert_to_wav_sync, audio_content)

    def _convert_to_wav_sync(self, audio_content: bytes) -> io.BytesIO:
        """Synchronous WAV conversion"""
        audio_bytes = io.BytesIO(audio_content)
        audio = AudioSegment.from_mp3(audio_bytes)
        audio = audio.set_frame_rate(16000).set_channels(1)
        wav_bytes = io.BytesIO()
        audio.export(wav_bytes, format="wav", parameters=["-q:a", "0"])
        wav_bytes.seek(0)
        return wav_bytes

    async def _convert_audio_to_text(self, wav_bytes: io.BytesIO) -> str:
        """Convert audio to text"""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._convert_audio_to_text_sync, wav_bytes)
        except Exception as e:
            raise Exception(f"Audio conversion error: {str(e)}")

    def _convert_audio_to_text_sync(self, wav_bytes: io.BytesIO) -> str:
        """Synchronous speech recognition"""
        with sr.AudioFile(wav_bytes) as source:
            audio = self.recognizer.record(source)
            try:
                text = str(self.recognizer.recognize_google(audio))
                cleaned_text = ''.join(c.lower() for c in text if c.isalnum() or c.isspace())
                if not cleaned_text:
                    raise Exception("Empty audio response")
                return cleaned_text.strip()
            except Exception as e:
                raise Exception(f"Speech recognition error: {str(e)}")

class ReCaptchaSolver:
    """Handles reCAPTCHA solving"""
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
        <head>
            <script src="https://www.google.com/recaptcha/api.js" async defer></script>
        </head>
        <body>
            <div class="g-recaptcha" data-sitekey="{sitekey}"></div>
        </body>
    </html>
    """

    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug
        self.log = Logger()
        has_proxy = bool(getattr(page, 'proxy', None))
        self.page.set_default_timeout(20000 if has_proxy else 8000)
        self.audio_processor = AudioProcessor(debug)

    async def solve(self) -> str:
        """Solve reCAPTCHA challenge"""
        try:
            iframe = await self._handle_initial_iframe()
            challenge_iframe = await self._handle_challenge_iframe()
            if not challenge_iframe:
                return await self._get_token()
            
            audio_url = await self._get_audio_challenge(challenge_iframe)
            async with self.audio_processor as processor:
                audio_text = await processor.process_audio(audio_url)
            await self._submit_audio_solution(challenge_iframe, audio_text)
            return await self._get_token()
        except Exception as e:
            raise Exception(f"Solving error: {str(e)}")

    async def _handle_initial_iframe(self) -> Optional[Page]:
        """Handle initial iframe"""
        iframe = await self.page.wait_for_selector(
            "iframe[src*='google.com/recaptcha/api2/anchor'], iframe[src*='google.com/recaptcha/enterprise/anchor']",
            strict=True
        )
        iframe = await iframe.content_frame()
        checkbox = await iframe.wait_for_selector("#recaptcha-anchor", state="visible", strict=True)
        await checkbox.click()
        return iframe

    async def _handle_challenge_iframe(self) -> Optional[Page]:
        """Handle challenge iframe"""
        challenge_iframe = await self.page.wait_for_selector(
            "iframe[src*='google.com/recaptcha/api2/bframe'], iframe[src*='google.com/recaptcha/enterprise/bframe']",
            timeout=3000,
            strict=True
        )
        return await challenge_iframe.content_frame()

    async def _get_audio_challenge(self, frame: Page) -> str:
        """Get audio challenge URL"""
        try:
            audio_button = await frame.wait_for_selector("#recaptcha-audio-button", state="visible", timeout=2000)
            await audio_button.click()
            
            download_button = await frame.wait_for_selector(".rc-audiochallenge-tdownload-link", state="visible", timeout=5000)
            audio_url = await download_button.get_attribute("href")
            if not audio_url:
                raise Exception("No audio URL found")
            return audio_url
        except Exception as e:
            if await self._check_rate_limit(frame):
                raise Exception("Rate limit reached")
            raise Exception(f"Audio challenge error: {str(e)}")

    async def _submit_audio_solution(self, frame: Page, solution: str) -> None:
        """Submit audio solution"""
        response_input = await frame.wait_for_selector("#audio-response", state="visible")
        await response_input.fill(solution)
        verify_button = await frame.wait_for_selector("#recaptcha-verify-button", state="visible")
        await verify_button.click()

    async def _check_rate_limit(self, frame: Page) -> bool:
        """Check for rate limiting"""
        try:
            rate_limit_element = frame.locator(".rc-doscaptcha-header")
            rate_limit_message = await rate_limit_element.text_content()
            return "Try again later" in rate_limit_message
        except:
            return False

    async def _get_token(self) -> str:
        """Get reCAPTCHA token"""
        token_methods = [
            self._get_response_token,
            self._get_bframe_token,
            self._get_frame_token,
            self._get_enterprise_token
        ]

        for method in token_methods:
            try:
                token = await method()
                if token:
                    return str(token)
            except Exception as e:
                if self.debug:
                    self.log.debug(f"Token method {method.__name__} failed: {str(e)}")
                continue

        raise Exception("Could not retrieve token")

    async def _get_response_token(self) -> Optional[str]:
        return await self.page.evaluate('''() => {
            const response = document.getElementById('g-recaptcha-response');
            return response ? response.value : null;
        }''')

    async def _get_bframe_token(self) -> Optional[str]:
        return await self.page.evaluate('''() => {
            for (const frame of window.frames) {
                try {
                    const token = frame.document.getElementById('recaptcha-token');
                    if (token) return token.value;
                } catch (e) {}
            }
            return null;
        }''')

    async def _get_frame_token(self) -> Optional[str]:
        for frame in self.page.frames:
            try:
                token = await frame.evaluate('document.getElementById("recaptcha-token").value')
                if token:
                    return token
            except:
                continue
        return None

    async def _get_enterprise_token(self) -> Optional[str]:
        return await self.page.evaluate('''() => {
            const response = document.querySelector('[name="recaptcha-token"]');
            return response ? response.value : null;
        }''')

class APIHandler:
    """Handles API requests"""
    def __init__(self, max_concurrent: int = 10):
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self.log = Logger()

    async def solve_captcha(self, data: Dict) -> Dict[str, Union[bool, str, None]]:
        """Solve single reCAPTCHA using thread pool"""
        try:
            future = self.executor.submit(
                self._sync_solve_captcha,
                data
            )
            result = await asyncio.get_event_loop().run_in_executor(
                None, future.result, APIConfig.TIMEOUT
            )
            return result
        except Exception as e:
            self.log.failure(f"Solving failed: {str(e)}")
            return {
                "errorId": 1,
                "errorCode": "ERROR_SOLVING",
                "errorDescription": str(e)
            }

    def _sync_solve_captcha(self, data: Dict) -> Dict:
        """Synchronous captcha solving method for thread pool"""
        loader = None
        try:
            loader = Loader(desc="Solving reCAPTCHA...", timeout=0.05)
            loader.start()
            start_time = time.time()

            browser_config = BrowserConfig()
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=data.get('headless', True),
                    args=browser_config.CHROME_ARGS
                )
                
                context_options = browser_config.CONTEXT_OPTIONS.copy()
                if data.get('proxy'):
                    context_options["proxy"] = data['proxy']
                
                context = browser.new_context(**context_options)
                page = context.new_page()
                
                try:
                    page.goto(data['websiteURL'], wait_until="commit")
                    if data.get('websiteKey'):
                        page.set_content(ReCaptchaSolver.HTML_TEMPLATE.format(
                            sitekey=data['websiteKey']
                        ))
                    
                    solver = ReCaptchaSolver(page, data.get('debug', False))
                    token = solver.solve()
                    
                    if loader:
                        loader.stop()
                    
                    result = {
                        "errorId": 0,
                        "status": "ready",
                        "solution": {
                            "gRecaptchaResponse": token
                        }
                    }

                    # Check score if requested
                    if data.get('checkScore', False):
                        try:
                            response = requests.post('https://2captcha.com/api/v1/captcha-demo/recaptcha-enterprise/verify', 
                                json={
                                    'siteKey': data['websiteKey'],
                                    'token': token,
                                })
                            score = response.json().get("riskAnalysis", {}).get("score")
                            result["solution"]["score"] = score
                            
                            if data.get('debug', False):
                                Logger().debug(f"Got score: {score}")
                        except Exception as e:
                            Logger().failure(f"Failed to check score: {e}")
                            result["solution"]["score"] = "Unknown"

                    return result

                except Exception as e:
                    if loader:
                        loader.stop()
                    if "rate limit" in str(e).lower():
                        error_msg = "Rate limit reached, consider using or changing your proxy."
                        if data.get('proxy'):
                            error_msg += " Please use a different proxy."
                        return {
                            "errorId": 1,
                            "errorCode": "ERROR_RATE_LIMIT",
                            "errorDescription": error_msg
                        }
                    return {
                        "errorId": 1,
                        "errorCode": "ERROR_SOLVING",
                        "errorDescription": str(e)
                    }
                finally:
                    if data.get('wait'):
                        time.sleep(data.get('wait'))
                    context.close()
                    browser.close()
        except Exception as e:
            if loader:
                loader.stop()
            return {
                "errorId": 1,
                "errorCode": "ERROR_SOLVING",
                "errorDescription": str(e)
            }

# Initialize API handler
api_handler = APIHandler(APIConfig.MAX_CONCURRENT)

@app.route('/createTask', methods=['POST'])
async def create_task():
    """Create and solve reCAPTCHA task"""
    try:
        data = await request.get_json()
        task = data.get('task', {})
        
        # Add default values
        task.setdefault('headless', True)
        task.setdefault('debug', False)
        task.setdefault('checkScore', False)
        task.setdefault('wait', None)
        
        if not task.get('websiteURL') or not task.get('websiteKey'):
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_PARAMETER",
                "errorDescription": "Missing required fields: websiteURL and websiteKey"
            }), 400

        if task.get('checkScore') and not task.get('websiteKey'):
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_PARAMETER",
                "errorDescription": "Score checking requires a websiteKey"
            }), 400

        result = await api_handler.solve_captcha(task)
        return jsonify(result)

    except Exception as e:
        log.failure(f"API Error: {str(e)}")
        return jsonify({
            "errorId": 1,
            "errorCode": "ERROR_UNKNOWN",
            "errorDescription": f"API Error: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run(
        host=APIConfig.HOST,
        port=APIConfig.PORT,
        debug=APIConfig.DEBUG
    )
