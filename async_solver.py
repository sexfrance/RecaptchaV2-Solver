from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
import io
import time
import aiohttp
import speech_recognition as sr
from pydub import AudioSegment
from patchright.async_api import async_playwright, Page, TimeoutError
from logmagix import Logger, Loader
import asyncio
from concurrent.futures import ThreadPoolExecutor

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

class AsyncAudioProcessor:
    """Handles audio processing and speech recognition asynchronously"""
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
        """Download and process audio file"""
        audio_content = await self._download_audio(audio_url)
        audio_bytes = await self._convert_to_wav(audio_content)
        return await self._convert_audio_to_text(audio_bytes)

    async def _download_audio(self, audio_url: str) -> bytes:
        """Download audio file from URL"""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        async with self._session.get(audio_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download audio file. Status code: {response.status}")
            return await response.read()

    async def _convert_to_wav(self, audio_content: bytes) -> io.BytesIO:
        """Convert MP3 audio to WAV format"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._convert_to_wav_sync,
            audio_content
        )

    def _convert_to_wav_sync(self, audio_content: bytes) -> io.BytesIO:
        """Synchronous version of WAV conversion"""
        audio_bytes = io.BytesIO(audio_content)
        audio = AudioSegment.from_mp3(audio_bytes)
        audio = audio.set_frame_rate(16000).set_channels(1)
        wav_bytes = io.BytesIO()
        audio.export(wav_bytes, format="wav", parameters=["-q:a", "0"])
        wav_bytes.seek(0)
        return wav_bytes

    async def _convert_audio_to_text(self, wav_bytes: io.BytesIO) -> str:
        """Convert audio to text using speech recognition"""
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None,
                self._convert_audio_to_text_sync,
                wav_bytes
            )
            return text
        except Exception as e:
            try:
                Loader.stop()
            except:
                pass
            raise e

    def _convert_audio_to_text_sync(self, wav_bytes: io.BytesIO) -> str:
        """Synchronous version of speech recognition"""
        with sr.AudioFile(wav_bytes) as source:
            audio = self.recognizer.record(source)
            try:
                text = str(self.recognizer.recognize_google(audio))
                if self.debug:
                    self.log.debug(f"Raw recognized text: {text}")
                cleaned_text = ''.join(c.lower() for c in text if c.isalnum() or c.isspace())
                if self.debug:
                    self.log.debug(f"Cleaned text: {cleaned_text}")
                if not cleaned_text:
                    raise sr.UnknownValueError("Empty audio response")
                return cleaned_text.strip()
            except sr.UnknownValueError:
                raise Exception("Could not understand audio")
            except sr.RequestError:
                raise Exception("Could not request results from speech recognition service")
            except Exception as e:
                if self.debug:
                    self.log.debug(f"Error type: {type(e)}")
                self.log.failure(f"Error message: {str(e)}")
                raise Exception(f"Unexpected error in audio conversion: {str(e)}")

class AsyncReCaptchaSolver:
    """Main class for solving reCAPTCHA challenges asynchronously"""
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
        self.audio_processor = AsyncAudioProcessor(debug)

    @classmethod
    async def solve_recaptcha(cls, url: str, proxy: Optional[Dict] = None, debug: bool = False, site_key: Optional[str] = None, headless: bool = True, wait: int = None, check_score: bool = False) -> str:
        """Class method to solve reCAPTCHA from URL or using a site key"""
        if check_score and not site_key:
            raise ValueError("Score checking requires a site key to be provided")
        
        loader = Loader(desc="Solving reCAPTCHA...", timeout=0.05)
        loader.start()
        start_time = time.time()

        browser_config = BrowserConfig()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless, args=browser_config.CHROME_ARGS)
            context_options = browser_config.CONTEXT_OPTIONS.copy()
            if proxy:
                context_options["proxy"] = proxy
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="commit")
                if site_key:
                    await page.set_content(cls.HTML_TEMPLATE.format(sitekey=site_key))
                solver = cls(page, debug)
                token = await solver._solve()
                end_time = time.time()
                loader.stop()

                if debug and check_score:
                    Logger().debug(f"Checking score...")

                if check_score:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.post('https://2captcha.com/api/v1/captcha-demo/recaptcha-enterprise/verify', 
                                json={
                                    'siteKey': site_key,
                                    'token': token,
                                }) as response:
                                result = await response.json()
                                if debug:
                                    Logger().debug(f"Got response for score: {result} {response.status}")
                                score = result.get("riskAnalysis", {}).get("score")
                    except Exception as e:
                        Logger().failure(f"Failed to check score: {e}")
                        score = "Unknown"
                
                if debug and check_score:
                    Logger().debug(f"Got score: {score}")

                Logger().message(
                    "reCAPTCHA",
                    f"Successfully solved captcha {token[:60]}..." if not check_score else f"Successfully solved captcha {token[:60]}... and score is {score}",
                    start=start_time,
                    end=end_time
                )
                return token
            except Exception as e:
                loader.stop()
                if "rate limit" in str(e).lower():
                    if proxy:
                        raise Exception("Rate limit reached, consider using or changing your proxy. Please use a different proxy.")
                    else:
                        raise Exception("Rate limit reached, consider using or changing your proxy.")
                raise e
            finally:
                if wait:
                    await asyncio.sleep(wait)
                await context.close()
                await browser.close()

    async def _solve(self) -> str:
        """Internal method to solve the reCAPTCHA"""
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
            try:
                Loader.stop()
            except:
                pass
            raise Exception(f"Failed to solve reCAPTCHA: {str(e)}")

    async def _handle_initial_iframe(self) -> Optional[Page]:
        """Handle the initial reCAPTCHA iframe"""
        iframe = await self.page.wait_for_selector(
            "iframe[src*='google.com/recaptcha/api2/anchor'], iframe[src*='google.com/recaptcha/enterprise/anchor']",
            strict=True
        )
        iframe = await iframe.content_frame()
        checkbox = await iframe.wait_for_selector("#recaptcha-anchor", state="visible", strict=True)
        await checkbox.click()
        return iframe

    async def _handle_challenge_iframe(self) -> Optional[Page]:
        """Handle the challenge iframe"""
        has_proxy = bool(getattr(self.page, 'proxy', None))
        challenge_iframe = await self.page.wait_for_selector(
            "iframe[src*='google.com/recaptcha/api2/bframe'], iframe[src*='google.com/recaptcha/enterprise/bframe']",
            timeout=10000 if has_proxy else 3000,
            strict=True
        )
        return await challenge_iframe.content_frame()

    async def _get_audio_challenge(self, challenge_iframe: Page) -> str:
        """Get audio challenge URL"""
        has_proxy = bool(getattr(self.page, 'proxy', None))
        try:
            audio_button = await challenge_iframe.wait_for_selector(
                "#recaptcha-audio-button",
                state="visible",
                timeout=5000 if has_proxy else 2000,
                strict=True
            )
            await audio_button.click()
        except TimeoutError:
            try:
                Loader.stop()
            except:
                pass
            if await self._check_rate_limit(challenge_iframe):
                if hasattr(self.page, 'proxy'):
                    raise Exception("Rate limit reached, consider using or changing your proxy. Please use a different proxy.")
                raise Exception("Rate limit reached, consider using or changing your proxy.")

        try:
            download_button = await challenge_iframe.wait_for_selector(
                ".rc-audiochallenge-tdownload-link", 
                state="visible", 
                timeout=12000 if has_proxy else 5000
            )
            audio_url = await download_button.get_attribute("href")
            if not audio_url:
                try:
                    Loader.stop()
                except:
                    pass
                raise Exception("Could not get audio URL")
            return audio_url
        except TimeoutError:
            try:
                Loader.stop()
            except:
                pass
            if await self._check_rate_limit(challenge_iframe):
                if hasattr(self.page, 'proxy'):
                    raise Exception("Rate limit reached, consider using or changing your proxy. Please use a different proxy.")
                raise Exception("Rate limit reached, consider using or changing your proxy.")
            raise

    async def _submit_audio_solution(self, challenge_iframe: Page, audio_text: str) -> None:
        """Submit the audio challenge solution"""
        response_input = await challenge_iframe.wait_for_selector("#audio-response", state="visible")
        await response_input.fill(audio_text)
        verify_button = await challenge_iframe.wait_for_selector("#recaptcha-verify-button", state="visible")
        await verify_button.click()

    async def _check_rate_limit(self, frame: Page) -> bool:
        """Check if rate limit has been reached"""
        try:
            rate_limit_element = frame.locator(".rc-doscaptcha-header")
            rate_limit_message = await rate_limit_element.text_content()
            return "Try again later" in rate_limit_message
        except:
            return False

    async def _get_token(self) -> str:
        """Get the reCAPTCHA token using multiple methods"""
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
                    if self.debug:
                        self.log.debug(f"Found token using {method.__name__}: {token}")
                    return str(token)
            except Exception as e:
                if self.debug:
                    self.log.debug(f"Error in {method.__name__}: {str(e)}")

        raise Exception("Could not retrieve reCAPTCHA token")

    async def _get_response_token(self) -> Optional[str]:
        """Get token from g-recaptcha-response"""
        return await self.page.evaluate('''() => {
            const response = document.getElementById('g-recaptcha-response');
            return response ? response.value : null;
        }''')

    async def _get_bframe_token(self) -> Optional[str]:
        """Get token from bframe"""
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
        """Get token from frames"""
        for frame in self.page.frames:
            try:
                token = await frame.evaluate('document.getElementById("recaptcha-token").value')
                if token:
                    return token
            except:
                continue
        return None

    async def _get_enterprise_token(self) -> Optional[str]:
        """Get token from enterprise recaptcha"""
        return await self.page.evaluate('''() => {
            const response = document.querySelector('[name="recaptcha-token"]');
            return response ? response.value : null;
        }''')

if __name__ == "__main__":
    async def main():
        try:
            token = await AsyncReCaptchaSolver.solve_recaptcha(
                "https://2captcha.com/demo/recaptcha-v2-enterprise",
                headless=False,
                debug=True,
                check_score=True,
                site_key="6LfB5B8UAAAAAJgXZxP_d-9KzXaqFzYGpXzJ2sFP"
            )
            print(token)
        except Exception as e:
            Logger().failure(f"Failed to solve reCAPTCHA: {e}")

    asyncio.run(main())
